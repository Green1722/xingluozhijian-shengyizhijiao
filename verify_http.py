"""Run an isolated HTTP acceptance test with temporary local data."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def check(actual, expected):
    if actual != expected:
        raise AssertionError(f"Expected {expected!r}, got {actual!r}")


def verify(base, launch):
    def request(path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = Request(base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            response = urlopen(req, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response) if path != "/" else response.read()

    def post(route, expected=200, **data):
        code, body = request("/api/" + route, data)
        check(code, expected)
        return body

    def ready():
        for _ in range(60):
            try:
                if request("/healthz") == (200, {"service": "xiaosheng-training"}):
                    return
            except (URLError, TimeoutError):
                pass
            time.sleep(.1)
        raise RuntimeError("Service did not start")

    session_reports = {}
    with launch():
        ready()
        code, home = request("/")
        check(code, 200)
        check("教师复盘" in home.decode(), True)
        for scenario, completed, pending in [
            ("oxygen", "已经戴好鼻导管", "还没有戴好鼻导管"),
            ("feeding", "已经完成鼻饲", "还没有完成鼻饲"),
        ]:
            session = post("sessions", 201, scenario=scenario)["id"]

            def turn(line, expected=200, event_id=None):
                return post("turns", expected, session_id=session,
                            event_id=event_id or uuid.uuid4().hex, utterance=line)

            identity = turn("请问您的姓名和住院号")
            check(identity["marker"], "identity")
            check(identity["reply"], "我叫李华，住院号是一二三四五六。")
            baseline = turn("现在有什么感觉")["reply"]
            turn(pending)
            check(turn("现在有什么感觉")["reply"], baseline)
            turn(completed)
            check(turn("现在有什么感觉")["reply"] != baseline, True)
            turn("我刚才说错了，" + pending)
            check(turn("现在有什么感觉")["reply"], baseline)
            key = uuid.uuid4().hex
            original = turn("谢谢您的配合", event_id=key)
            check(turn("谢谢您的配合", event_id=key), original)
            turn("换一句", 409, key)
            post("review", 409, session_id=session)
            report = post("finish", session_id=session)
            check(len(report["turns"]), 9)
            check(len(report["evidence"]) < 9, True)
            check(post("review", session_id=session), report)
            turn("还有哪里不舒服", 409)
            session_reports[session] = report
            print(f"{scenario}: case, negation, correction, retry and review passed")
        empty = post("sessions", 201, scenario="oxygen")["id"]
        check(post("finish", session_id=empty)["turns"], [])
        print("New sessions remain isolated")
    with launch():
        ready()
        for session, report in session_reports.items():
            check(post("review", session_id=session), report)
        print("Completed reviews survived a service restart")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as working:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = dict(os.environ, HOST="127.0.0.1", PORT=str(port),
                   TRAINING_DB=str(Path(working) / "acceptance.sqlite3"))
        app = Path(__file__).resolve().with_name("app.py")

        def launch():
            from contextlib import contextmanager

            @contextmanager
            def service():
                with subprocess.Popen([sys.executable, str(app)], env=env,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as process:
                    try:
                        yield
                    finally:
                        process.terminate()
            return service()

        verify(f"http://127.0.0.1:{port}", launch)
