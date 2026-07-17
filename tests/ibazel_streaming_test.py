import os
import queue
import shutil
import subprocess
import sys
import threading
from typing import TextIO


def _read_lines(stream: TextIO, lines: queue.Queue[str]) -> None:
    for line in stream:
        lines.put(line)


def _main() -> None:
    command = [sys.argv[1]]
    if os.name == "nt":
        bash = os.environ.get("BAZEL_SH") or shutil.which("bash.exe")
        assert bash is not None
        command.insert(0, bash)

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.stdin is not None
    assert process.stdout is not None

    lines: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(target=_read_lines, args=(process.stdout, lines))
    reader.start()

    notification = "IBAZEL_BUILD_COMPLETED SUCCESS"
    process.stdin.write(f"{notification}\n")
    process.stdin.flush()

    output = []
    try:
        while len([line for line in output if notification in line]) < 2:
            output.append(lines.get(timeout=10))
    finally:
        process.stdin.close()
        process.wait(timeout=10)
        reader.join(timeout=10)

    assert f"capable: {notification}\n" in output
    assert f"wrapped: {notification}\n" in output
    assert f"plain: {notification}\n" not in output


if __name__ == "__main__":
    _main()
