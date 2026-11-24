import json
import os
import sqlite3
import uuid
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from board_review import read_review
from patient import PROFILES, respond

ROOT = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("TRAINING_DB", ROOT / "training.sqlite3"))


def initialize():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DATABASE)) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, scenario TEXT NOT NULL, ended INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS turns (
            session_id TEXT NOT NULL, event_id TEXT NOT NULL, utterance TEXT NOT NULL,
            reply TEXT NOT NULL, marker TEXT, PRIMARY KEY (session_id, event_id)
        );
        """)


class Handler(BaseHTTPRequestHandler):
    def send(self, code, result, content_type="application/json"):
        body = result if isinstance(result, bytes) else json.dumps(result, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self.send(200, (ROOT / "index.html").read_bytes(), "text/html")
        elif self.path == "/healthz":
            self.send(200, {"service": "xiaosheng-training"})
        elif self.path.startswith("/api/board-review/"):
            receipt = self.path.removeprefix("/api/board-review/")
            code, review = read_review(os.environ.get("BOARD_RECEIPT_DB"), receipt)
            self.send(code, review)
        else:
            self.send(404, {"error": "unknown route"})

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 1 <= size <= 4096:
                raise ValueError("invalid request length")
            request = json.loads(self.rfile.read(size))
            if not isinstance(request, dict):
                raise ValueError("invalid request")
            with closing(sqlite3.connect(DATABASE)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                code, result = self.dispatch(db, request)
        except (ValueError, TypeError) as exc:
            code, result = 400, {"error": str(exc)}
        self.send(code, result)

    def dispatch(self, db, request):
        if self.path == "/api/sessions":
            scenario = request.get("scenario")
            if not isinstance(scenario, str) or scenario not in PROFILES:
                return 400, {"error": "unknown scenario"}
            session_id = uuid.uuid4().hex
            db.execute("INSERT INTO sessions(id, scenario) VALUES (?, ?)", (session_id, scenario))
            return 201, {"id": session_id}
        if self.path not in ("/api/turns", "/api/finish", "/api/review"):
            return 404, {"error": "unknown route"}
        session_id = request.get("session_id")
        if not isinstance(session_id, str):
            return 400, {"error": "missing session_id"}
        session = db.execute("SELECT scenario, ended FROM sessions WHERE id=?", (session_id,)).fetchone()
        if session is None:
            return 404, {"error": "session not found"}
        scenario, ended = session
        if self.path in ("/api/finish", "/api/review"):
            if self.path == "/api/review" and not ended:
                return 409, {"error": "session still active"}
            if not ended:
                db.execute("UPDATE sessions SET ended=1 WHERE id=?", (session_id,))
            rows = db.execute(
                "SELECT marker, utterance, reply FROM turns WHERE session_id=? ORDER BY rowid",
                (session_id,),
            )
            turns = [{"marker": marker, "utterance": line, "reply": reply} for marker, line, reply in rows]
            return 200, {"scenario": scenario, "turns": turns,
                         "evidence": [turn for turn in turns if turn["marker"] is not None]}
        event_id, utterance = request.get("event_id"), request.get("utterance")
        if not isinstance(event_id, str) or not 1 <= len(event_id) <= 64:
            return 400, {"error": "invalid event_id"}
        if not isinstance(utterance, str) or not 1 <= len(utterance.strip()) <= 300:
            return 400, {"error": "invalid utterance"}
        utterance = utterance.strip()
        existing = db.execute(
            "SELECT utterance, reply, marker FROM turns WHERE session_id=? AND event_id=?",
            (session_id, event_id),
        ).fetchone()
        if existing:
            if existing[0] != utterance:
                return 409, {"error": "event_id already used"}
            return 200, {"reply": existing[1], "marker": existing[2]}
        if ended:
            return 409, {"error": "session already ended"}
        reported = False
        for (line,) in db.execute(
            "SELECT utterance FROM turns WHERE session_id=? ORDER BY rowid", (session_id,)
        ):
            _, _, reported = respond(scenario, line, reported)
        marker, reply, _ = respond(scenario, utterance, reported)
        db.execute("INSERT INTO turns VALUES (?, ?, ?, ?, ?)", (session_id, event_id, utterance, reply, marker))
        return 200, {"reply": reply, "marker": marker}


if __name__ == "__main__":
    initialize()
    ThreadingHTTPServer(
        (os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8080"))), Handler
    ).serve_forever()
