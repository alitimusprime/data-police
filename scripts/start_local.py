"""Portable launcher for the lightweight SQLite profile. Keeps every child in one lifecycle."""

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-schedule", action="store_true")
    parser.add_argument("--no-seed", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    os.environ["PYTHONPATH"] = str(root / "backend")
    if not (root / ".env").exists():
        subprocess.run([sys.executable, "scripts/bootstrap.py"], check=True)
    if not (root / "web/dist/index.html").exists():
        raise SystemExit("Build the UI first: cd web, then npm ci and npm run build.")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    children = []

    def shutdown(*_):
        for child in reversed(children):
            child.terminate()
        for child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "data_police.demo_api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8001",
                ]
            )
        )
        for _ in range(100):
            if children[0].poll() is not None:
                raise RuntimeError("Demo provider failed to start; check port 8001")
            try:
                urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Demo provider startup timed out")
        if not args.no_seed:
            subprocess.run([sys.executable, "-m", "data_police.cli", "seed"], check=True)
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "data_police.api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ]
            )
        )
        if not args.no_schedule:
            children.append(subprocess.Popen([sys.executable, "-m", "data_police.cli", "scheduler"]))
        print(
            "\nData Police: http://localhost:8000\nSign in with the credentials in .env. Press Ctrl+C to stop.\n",
            flush=True,
        )
        while all(child.poll() is None for child in children):
            time.sleep(1)
        raise RuntimeError("A required service stopped. Read the preceding error before restarting.")
    except KeyboardInterrupt:
        print("Stopping Data Police. Persistent data is preserved.")
    finally:
        shutdown()


if __name__ == "__main__":
    main()
