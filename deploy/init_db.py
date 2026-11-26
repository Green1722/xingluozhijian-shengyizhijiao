"""Create or upgrade the two SQLite databases used by the local deployment.

The web training service writes ``training.sqlite3`` and the board receipt
service writes ``board_receipts.sqlite3``.  Both live next to this checkout so
the default paths in ``app.py`` and ``board_receipts.py`` keep working.  Running
this script repeatedly is safe: tables use ``IF NOT EXISTS`` and seeded rows use
``INSERT OR IGNORE``.
"""
import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent.parent
TRAINING_DB = ROOT / "training.sqlite3"
RECEIPT_DB = ROOT / "board_receipts.sqlite3"
SAMPLE = ROOT / "samples" / "board-capture.json"

TRAINING_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, scenario TEXT NOT NULL, ended INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS turns (
    session_id TEXT NOT NULL, event_id TEXT NOT NULL, utterance TEXT NOT NULL,
    reply TEXT NOT NULL, marker TEXT, PRIMARY KEY (session_id, event_id)
);
"""

RECEIPT_SCHEMA = """
CREATE TABLE IF NOT EXISTS receipts (
    id TEXT PRIMARY KEY, payload BLOB NOT NULL, received_at TEXT NOT NULL
);
"""


def init_training(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(TRAINING_SCHEMA)
        tables = sorted(row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        sessions = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        turns = db.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
    return tables, sessions, turns


def init_receipts(path, seed):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reuse the service's encoder and validator so stored bytes match receipts.
    sys.path.insert(0, str(ROOT))
    from board_receipts import encode, validate

    receipt = None
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(RECEIPT_SCHEMA)
        if seed and SAMPLE.exists():
            payload = encode(json.loads(SAMPLE.read_text(encoding="utf-8-sig")))
            validate(json.loads(payload))
            receipt = sha256(payload).hexdigest()
            db.execute(
                "INSERT OR IGNORE INTO receipts VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                (receipt, payload),
            )
        total = db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    return total, receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-db", type=Path, default=TRAINING_DB)
    parser.add_argument("--receipt-db", type=Path, default=RECEIPT_DB)
    parser.add_argument("--seed-sample", dest="seed_sample", action="store_true",
                        help="import samples/board-capture.json as one fictional receipt")
    parser.add_argument("--no-seed-sample", dest="seed_sample", action="store_false")
    parser.set_defaults(seed_sample=True)
    args = parser.parse_args()

    tables, sessions, turns = init_training(args.training_db)
    print(f"training db  {args.training_db}")
    print(f"  tables     {', '.join(tables)}")
    print(f"  rows       sessions={sessions} turns={turns}")

    total, receipt = init_receipts(args.receipt_db, args.seed_sample)
    print(f"receipt db   {args.receipt_db}")
    print(f"  tables     receipts")
    print(f"  rows       receipts={total}")
    if receipt:
        print(f"  sample receipt {receipt}")


if __name__ == "__main__":
    main()
