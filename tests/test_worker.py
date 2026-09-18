import os
import subprocess
import sys
import time

import pytest
from sqlalchemy import func, select

from data_police.config import settings
from data_police.db import session_scope
from data_police.jobs import materialize_task
from data_police.models import Profile, Run
from data_police.pipeline import create_run


@pytest.mark.skipif(not os.getenv("DP_TEST_REDIS_URL"), reason="A dedicated test Redis server is required")
def test_real_broker_worker_and_redelivery(live_provider):
    env = os.environ | {"DP_DEMO_API_URL": settings.demo_api_url, "PYTHONPATH": "backend"}
    with (settings.data_dir / "celery-test.log").open("w") as log:
        worker = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "data_police.jobs:celery_app",
                "worker",
                "--pool=solo",
                "--concurrency=1",
                "--loglevel=WARNING",
                "--without-gossip",
                "--without-mingle",
            ],
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            identifier = create_run(key="real-worker-delivery")
            materialize_task.delay(identifier)
            materialize_task.delay(identifier)
            for _ in range(150):
                with session_scope() as session:
                    status = session.get(Run, identifier).status
                if status in {"succeeded", "failed"}:
                    break
                if worker.poll() is not None:
                    pytest.fail("Worker exited. Inspect celery-test.log in the temporary test directory.")
                time.sleep(0.2)
            assert status == "succeeded"
            with session_scope() as session:
                assert (
                    session.scalar(
                        select(func.count()).select_from(Profile).where(Profile.run_id == identifier)
                    )
                    == 19
                )
        finally:
            worker.terminate()
            try:
                worker.wait(timeout=8)
            except subprocess.TimeoutExpired:
                worker.kill()
