import os
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest
import uvicorn


TEST_ROOT = Path(tempfile.mkdtemp(prefix="data-police-tests-"))
for key in ("DP_TEST_DATABASE_URL", "DP_TEST_SOURCE_DATABASE_URL"):
    if os.environ.get(key) and not os.environ[key].rstrip("/").endswith("datapolice_test"):
        raise RuntimeError("External test databases must be explicitly named datapolice_test")
os.environ.update(
    {
        "DP_ENV": "test",
        "DP_DATA_DIR": str(TEST_ROOT),
        "DP_DATABASE_URL": os.getenv("DP_TEST_DATABASE_URL", f"sqlite:///{TEST_ROOT / 'platform.db'}"),
        "DP_SOURCE_DATABASE_URL": os.getenv(
            "DP_TEST_SOURCE_DATABASE_URL", f"sqlite:///{TEST_ROOT / 'source.db'}"
        ),
        "DP_ADMIN_PASSWORD": "test-only-password-12345",
        "DP_SESSION_SECRET": "test-only-session-secret-at-least-32-bytes",
        "DP_REDIS_URL": os.getenv("DP_TEST_REDIS_URL", "redis://127.0.0.1:6379/0"),
        "DP_EXECUTOR": "local",
        "DP_FRESHNESS_SECONDS": "180",
    }
)

from data_police.catalog import initialize_catalog  # noqa: E402
from data_police.config import settings  # noqa: E402
from data_police.db import Base, engine, session_scope  # noqa: E402
from data_police.demo_api import app as provider  # noqa: E402
from data_police.sources import source_engine, source_metadata  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    # Destructive reset applies only to the temporary test databases created above.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    source = source_engine()
    source_metadata.drop_all(source)
    source_metadata.create_all(source)
    source.dispose()
    with session_scope() as session:
        initialize_catalog(session)
    yield


@pytest.fixture(scope="session")
def live_provider():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    settings.demo_api_url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(provider, log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.01)
    assert server.started
    yield settings.demo_api_url
    server.should_exit = True
    thread.join(timeout=5)
