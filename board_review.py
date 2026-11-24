"""Read-only review of records received from the board's serial capture."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3

ITEMS = {
    "introduction": ("自我介绍", r"我是.{0,12}护士|我是.{0,12}护理"),
    "identity": ("身份核对", r"叫什么|姓名|名字|住院号|几号床"),
    "purpose": ("解释目的", r"为了.{1,24}|目的是|是为了"),
    "reassurance": ("安抚提醒", r"别紧张|不用担心|有不舒服.{0,10}(告诉|叫|按铃)"),
}

EXCLUDED = r"没有|还没|不用.{0,4}(核对|询问|解释)|不必.{0,4}(核对|询问|解释)|忘了|举例|比如|示范|曾说|他说|她说|[「『“]"


def build_review(receipt, received_at, record):
    evidence = {key: [] for key in ITEMS}
    for number, event in enumerate(record["events"], 1):
        if event["direction"] != "recognized":
            continue
        text = event["text"]
        if re.search(EXCLUDED, text):
            continue
        for key, (_, pattern) in ITEMS.items():
            if re.search(pattern, text):
                evidence[key].append(number)
    return {
        "receipt": receipt,
        "received_at": received_at,
        "source": record["source"],
        "case": record["case"],
        "events": record["events"],
        "items": [
            {"id": key, "label": label, "events": evidence[key]}
            for key, (label, _) in ITEMS.items()
        ],
    }


def read_review(database, receipt):
    if not re.fullmatch(r"[0-9a-f]{64}", receipt):
        return 400, {"error": "回执编号应为 64 位十六进制字符"}
    if not database:
        return 503, {"error": "未配置板端回执数据库"}
    try:
        uri = Path(database).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            row = db.execute("SELECT payload, received_at FROM receipts WHERE id=?", (receipt,)).fetchone()
        if row is None:
            return 404, {"error": "未找到该回执"}
        return 200, build_review(receipt, row[1], json.loads(row[0]))
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        return 503, {"error": "板端回执暂时无法读取"}
