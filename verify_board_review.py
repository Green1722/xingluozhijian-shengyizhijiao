"""Regression checks for reading and attributing board receipt evidence."""
from hashlib import sha256
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from board_receipts import encode
from board_review import read_review

record = {"source": "usb_serial_capture", "case": "合成回归", "events": [
    {"direction": "device_reply", "text": "您没有问患者姓名，应该核对住院号。", "time": "2026-01-01T00:00:00Z"},
    {"direction": "recognized", "text": "我还没核对住院号。", "time": "2026-01-01T00:00:01Z"},
    {"direction": "recognized", "text": "我是负责您的护士，方便问您的姓名吗？", "time": "2026-01-01T00:00:02Z"},
    {"direction": "recognized", "text": "不用担心，有不舒服告诉我。", "time": "2026-01-01T00:00:03Z"},
]}
payload = encode(record)
receipt = sha256(payload).hexdigest()
with TemporaryDirectory() as folder:
    database = Path(folder) / "receipts.sqlite3"
    assert read_review(database, receipt)[0] == 503
    assert not database.exists()
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE receipts (id TEXT PRIMARY KEY, payload BLOB NOT NULL, received_at TEXT NOT NULL)")
        db.execute("INSERT INTO receipts VALUES (?, ?, ?)", (receipt, payload, "2026-01-01T00:01:00Z"))
    db.close()
    status, result = read_review(database, receipt)
    assert status == 200 and result["events"] == record["events"]
    assert result["source"] == "usb_serial_capture"
    actual = {item["id"]: item["events"] for item in result["items"]}
    assert actual == {"introduction": [3], "identity": [3], "purpose": [], "reassurance": [4]}, actual
    assert read_review(database, "0" * 64)[0] == 404
    assert read_review(database, "bad")[0] == 400
print("Verified read-only receipt retrieval, event references, excluded replies and negations, missing and invalid receipts")
