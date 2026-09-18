"""Optional real Redis broker test in an isolated temporary directory.

Requires the test-only redislite package. Production uses the Compose Redis service.
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import redislite
import redis


root = Path(__file__).resolve().parents[1]
temporary = Path(tempfile.mkdtemp(prefix="dp-redis-qa-"))
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
server = subprocess.Popen(
    [
        redislite.__redis_executable__,
        "--port",
        str(port),
        "--bind",
        "127.0.0.1",
        "--daemonize",
        "no",
        "--save",
        "",
        "--appendonly",
        "no",
        "--dir",
        str(temporary),
    ],
    stdout=subprocess.DEVNULL,
)
try:
    connection = redis.Redis(host="127.0.0.1", port=port)
    for _ in range(100):
        try:
            if connection.ping():
                break
        except redis.ConnectionError:
            time.sleep(0.05)
    else:
        raise RuntimeError("Test Redis could not start")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_worker.py",
            "-q",
            "--junitxml=artifacts/redis-worker-tests.xml",
        ],
        cwd=root,
        env=os.environ | {"DP_TEST_REDIS_URL": f"redis://127.0.0.1:{port}/0"},
    )
    raise SystemExit(result.returncode)
finally:
    server.terminate()
    server.wait(timeout=5)
