"""Record selected training utterances forwarded from a USB serial capture."""
import argparse
from contextlib import closing
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DB = Path(__file__).resolve().with_name("board_receipts.sqlite3")
SOURCE = "usb_serial_capture"
MAX_BYTES = 32_768


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != {"source", "case", "events"}:
        raise ValueError("invalid record")
    if payload["source"] != SOURCE or not isinstance(payload["case"], str) or not 1 <= len(payload["case"]) <= 80:
        raise ValueError("invalid source or case")
    if not isinstance(payload["events"], list) or not 1 <= len(payload["events"]) <= 80:
        raise ValueError("invalid events")
    for event in payload["events"]:
        if not isinstance(event, dict) or set(event) != {"time", "direction", "text"}:
            raise ValueError("invalid event")
        if event["direction"] not in ("recognized", "device_reply"):
            raise ValueError("invalid direction")
        if not isinstance(event["time"], str) or not 1 <= len(event["time"]) <= 30:
            raise ValueError("invalid timestamp")
        if not isinstance(event["text"], str) or not 1 <= len(event["text"]) <= 350:
            raise ValueError("invalid text")


class Receiver(BaseHTTPRequestHandler):
    def send_json(self, status, result):
        body = encode(result)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/board-receipts":
            self.send_json(404, {"error": "route not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= MAX_BYTES:
                raise ValueError("invalid body size")
            payload = json.loads(self.rfile.read(size))
            validate(payload)
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
            return
        body = encode(payload)
        receipt = sha256(body).hexdigest()
        with closing(sqlite3.connect(DB)) as db, db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO receipts VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                (receipt, body),
            ).rowcount
        self.send_json(201 if inserted else 200,
                       {"receipt": receipt, "events": len(payload["events"]), "new": bool(inserted)})

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            self.send_json(200, {"service": "xiaosheng-board-receipts"})
            return
        prefix = "/api/board-receipts/"
        if not path.startswith(prefix) or len(path) != len(prefix) + 64:
            self.send_json(404, {"error": "route not found"})
            return
        receipt = path[len(prefix):]
        with closing(sqlite3.connect(DB)) as db:
            row = db.execute("SELECT payload, received_at FROM receipts WHERE id=?", (receipt,)).fetchone()
        if row is None:
            self.send_json(404, {"error": "receipt not found"})
            return
        self.send_json(200, {"receipt": receipt, "received_at": row[1], "record": json.loads(row[0])})


def verify_upload(url, capture):
    body = encode(json.loads(capture.read_text(encoding="utf-8-sig")))
    req = Request(url + "/api/board-receipts", data=body,
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=5) as first:
        receipt = json.load(first)
    with urlopen(req, timeout=5) as retry:
        repeated = json.load(retry)
        assert retry.status == 200 and not repeated["new"]
    with urlopen(url + "/api/board-receipts/" + receipt["receipt"], timeout=5) as response:
        stored = json.load(response)
    assert stored["receipt"] == receipt["receipt"] == sha256(body).hexdigest()
    assert encode(stored["record"]) == body
    assert receipt["events"] == len(stored["record"]["events"])
    print(json.dumps({**receipt, "received_at": stored["received_at"], "review_matches": True,
                      "retry_was_deduplicated": True}, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8091)
    p.add_argument("--verify-upload", type=Path)
    args = p.parse_args()
    address = f"http://127.0.0.1:{args.port}"
    if args.verify_upload:
        verify_upload(address, args.verify_upload)
    else:
        with closing(sqlite3.connect(DB)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, payload BLOB NOT NULL, received_at TEXT NOT NULL)")
        ThreadingHTTPServer(("127.0.0.1", args.port), Receiver).serve_forever()
