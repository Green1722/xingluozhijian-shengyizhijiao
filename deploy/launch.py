"""Start one training service fully detached from the calling shell.

Windows keeps a pipeline open while any process still holds an inherited pipe
handle, and a launcher terminated with its process tree also kills ordinary
children.  ``subprocess.Popen`` with ``DETACHED_PROCESS`` and ``close_fds``
avoids both problems: the service gets its own log files and survives the shell
that started it.

Usage:
    python deploy/launch.py --name app --pid-file .run/app.pid \
        --log-dir .run/logs -- app.py
"""
import argparse
from contextlib import closing
from pathlib import Path
import subprocess
import sys

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--pid-file", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--working-dir", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = [part for part in args.command if part != "--"]
    if not command:
        parser.error("missing service command")

    args.pid_file.parent.mkdir(parents=True, exist_ok=True)
    args.log_dir.mkdir(parents=True, exist_ok=True)

    if args.pid_file.exists():
        try:
            previous = int(args.pid_file.read_text().strip())
        except ValueError:
            previous = None
        if previous and process_alive(previous):
            print(f"{args.name} already running (pid {previous})")
            return 0
        args.pid_file.unlink()

    stdout_path = args.log_dir / f"{args.name}.out.log"
    stderr_path = args.log_dir / f"{args.name}.err.log"
    with stdout_path.open("ab") as out, stderr_path.open("ab") as err, closing(out), closing(err):
        process = subprocess.Popen(
            [sys.executable, *command],
            cwd=str(args.working_dir) if args.working_dir else None,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            close_fds=True,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        )
    args.pid_file.write_text(str(process.pid), encoding="ascii")
    print(f"{args.name} started pid {process.pid}")
    return 0


def process_alive(pid):
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=15,
            creationflags=CREATE_NO_WINDOW,
        )
        return str(pid) in result.stdout
    except (OSError, subprocess.SubprocessError):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
