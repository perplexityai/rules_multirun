import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_TIMEOUT_SECONDS = 60 if os.name == "nt" else 10


def _event(path: str, kind: str = "source", success: bool = True) -> str:
    payload = {
        "version": 1,
        "type": "build_completed",
        "success": success,
        "changes": [{"path": path, "kind": kind}],
    }
    return "IBAZEL_EVENT " + json.dumps(payload, separators=(",", ":"))


def _wait_for_launches(path: Path, expected: dict[str, int]) -> None:
    deadline = time.monotonic() + _TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        launches = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        if all(launches.count(name) >= count for name, count in expected.items()):
            return
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for launches {expected}: {launches}")


def _main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        launch_log = Path(temp_dir) / "launches.txt"
        command = [sys.argv[1], str(launch_log)]
        if os.name == "nt":
            bash = os.environ.get("BAZEL_SH") or shutil.which("bash.exe")
            assert bash is not None
            command.insert(0, bash)

        process = subprocess.Popen(command, stdin=subprocess.PIPE, text=True)
        assert process.stdin is not None
        try:
            _wait_for_launches(launch_log, {"rpc": 1, "electron": 1})

            process.stdin.write(_event("pplx/rust/initial.rs") + "\n")
            process.stdin.flush()
            time.sleep(0.2)
            assert launch_log.read_text(encoding="utf-8").splitlines().count("rpc") == 1

            process.stdin.write(_event("pplx/rust/src/lib.rs", success=False) + "\n")
            process.stdin.flush()
            time.sleep(0.2)
            assert launch_log.read_text(encoding="utf-8").splitlines().count("rpc") == 1

            process.stdin.write(_event("pplx/rust/src/lib.rs") + "\n")
            process.stdin.flush()
            _wait_for_launches(launch_log, {"rpc": 2, "electron": 1})

            process.stdin.write(
                _event("pplx/frontend/apps/renderer/BUILD.bazel", "graph") + "\n"
            )
            process.stdin.flush()
            time.sleep(0.2)
            launches = launch_log.read_text(encoding="utf-8").splitlines()
            assert launches.count("rpc") == 2
            assert launches.count("electron") == 1

            process.stdin.write(_event("MODULE.bazel", "graph") + "\n")
            process.stdin.flush()
            _wait_for_launches(launch_log, {"rpc": 3, "electron": 2})
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        assert process.returncode == 0


if __name__ == "__main__":
    _main()
