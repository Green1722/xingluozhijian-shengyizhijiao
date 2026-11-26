"""Turn a captured ESP32 serial log into a board receipt payload.

The board console prints two kinds of application lines:

    I (12345) Application: >> 学员说的话
    I (12345) Application: << 设备/患者的回复

``>>`` is the recognizer output for the nurse, ``<<`` is the reply the board
played.  Each line carries a monotonic millisecond stamp which we anchor to the
host clock markers (``#T``) written by the capture script, so the payload times
stay on the same second as the real session.
"""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
LINE = re.compile(r"I \((\d+)\) Application: (>>|<<)\s*(.*)$")


def parse(log_path):
    anchor = None
    anchor_ms = None
    events = []
    for raw in log_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#T "):
            anchor = datetime.fromisoformat(line[3:].strip())
            anchor_ms = None
            continue
        match = LINE.search(line)
        if not match:
            continue
        ms = int(match.group(1))
        direction = "recognized" if match.group(2) == ">>" else "device_reply"
        text = match.group(3).strip()
        if not text:
            continue
        if anchor is None:
            anchor = datetime.now().astimezone()
        if anchor_ms is None:
            anchor_ms = ms
        when = anchor + timedelta(milliseconds=ms - anchor_ms)
        events.append({"time": when.isoformat(timespec="seconds"), "direction": direction,
                       "text": text[:350]})
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, default=ROOT / ".run" / "serial.log")
    parser.add_argument("--case", default="小儿静脉输液（实机 2026-11-26）")
    parser.add_argument("--out", type=Path, default=ROOT / "samples" / "board-capture.json")
    args = parser.parse_args()

    events = parse(args.log)
    if not events:
        print("没有从日志里解析到任何 >> / << 行")
        return 1
    events = events[:80]
    record = {"source": "usb_serial_capture", "case": args.case[:80], "events": events}

    sys.path.insert(0, str(ROOT))
    from board_receipts import encode, validate
    from hashlib import sha256

    validate(record)
    body = encode(record)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"写入 {args.out}")
    print(f"事件数 {len(events)}，请求体 {len(body)} 字节")
    print(f"预期回执 {sha256(body).hexdigest()}")
    for n, event in enumerate(events, 1):
        side = "学员" if event["direction"] == "recognized" else "设备"
        print(f"  {n:2d} {event['time']} {side}：{event['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
