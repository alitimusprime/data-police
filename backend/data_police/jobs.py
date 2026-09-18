import logging
import time
from concurrent.futures import ThreadPoolExecutor

from celery import Celery
from sqlalchemy import select

from .config import settings
from .db import session_scope
from .models import Run
from .pipeline import PipelineBusy, execute_run, freshness_sweep


celery_app = Celery("data_police", broker=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=540,
    task_soft_time_limit=510,
    broker_transport_options={"visibility_timeout": 900},
    broker_connection_retry_on_startup=True,
)
local_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dp-analysis")


@celery_app.task(bind=True, max_retries=120, name="data_police.materialize")
def materialize_task(self, run_id):
    try:
        return execute_run(run_id)
    except PipelineBusy as exc:
        raise self.retry(exc=exc, countdown=5)


@celery_app.task(name="data_police.freshness")
def freshness_task():
    return freshness_sweep()


def run_local(run_id):
    for _ in range(120):
        try:
            return execute_run(run_id)
        except PipelineBusy:
            time.sleep(2)
    logging.getLogger("data_police.jobs").error("local_job_lease_timeout", extra={"run_id": run_id})


def dispatch(run_id):
    if settings.executor == "celery":
        materialize_task.delay(run_id)
    else:
        local_executor.submit(run_local, run_id)


def redrive_pending():
    # Queued rows are durable. Redelivery is safe because the worker checks terminal status.
    with session_scope() as session:
        pending = session.scalars(select(Run.id).where(Run.status.in_(["queued", "running"])).limit(10)).all()
    for identifier in pending:
        dispatch(identifier)
