"""Disposable live server used by the browser acceptance test, never by production."""

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path


root = Path(__file__).resolve().parents[1]
temporary = Path(tempfile.mkdtemp(prefix="data-police-browser-"))
os.environ.update(
    {
        "DP_ENV": "test",
        "DP_DATA_DIR": str(temporary),
        "DP_DATABASE_URL": f"sqlite:///{temporary / 'platform.db'}",
        "DP_SOURCE_DATABASE_URL": f"sqlite:///{temporary / 'source.db'}",
        "DP_ADMIN_EMAIL": "qa@example.test",
        "DP_ADMIN_PASSWORD": "local-browser-test-password",
        "DP_SESSION_SECRET": "local-browser-test-session-secret-long-enough",
        "DP_EXECUTOR": "local",
        "DP_FRESHNESS_SECONDS": "180",
        "DP_AUTO_RUN_SECONDS": "0",
        "DP_ALLOWED_ORIGINS": "http://127.0.0.1:8765",
    }
)
sys.path.insert(0, str(root / "backend"))
import uvicorn  # noqa: E402
from data_police.catalog import initialize_catalog  # noqa: E402
from data_police.config import settings  # noqa: E402
from data_police.db import Base, engine, session_scope  # noqa: E402
from data_police.demo_api import app as demo  # noqa: E402
from data_police.pipeline import create_run, execute_run  # noqa: E402
from data_police.models import Run  # noqa: E402


Base.metadata.create_all(engine)
with session_scope() as session:
    initialize_catalog(session)
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
settings.demo_api_url = f"http://127.0.0.1:{sock.getsockname()[1]}"
server = uvicorn.Server(uvicorn.Config(demo, log_level="error"))
thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
thread.start()
for _ in range(200):
    if server.started:
        break
    time.sleep(0.01)
for index in range(12):
    identifier = create_run(key=f"qa-baseline-{index}", trigger="baseline")
    execute_run(identifier)
    with session_scope() as session:
        if session.get(Run, identifier).status != "succeeded":
            raise SystemExit("QA baseline failed")
from data_police.api import app  # noqa: E402

print("QA_READY", flush=True)
uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
