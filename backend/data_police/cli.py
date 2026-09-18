import argparse
import logging
import time
import uuid

from sqlalchemy import func, or_, select

from .catalog import initialize_catalog
from .db import session_scope
from .models import Run
from .pipeline import create_run, execute_run, freshness_sweep


def main():
    parser = argparse.ArgumentParser(description="Operate the Data Police workspace")
    parser.add_argument("command", choices=["init", "seed", "run", "freshness", "scheduler"])
    parser.add_argument("--batches", type=int, default=12)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    with session_scope() as session:
        initialize_catalog(session)
    if args.command == "seed":
        for index in range(args.batches):
            key = f"initial-baseline-{index}"
            with session_scope() as session:
                complete = session.scalar(
                    select(Run)
                    .where(
                        or_(Run.idempotency_key == key, Run.idempotency_key.like(key + ":retry:%")),
                        Run.status == "succeeded",
                    )
                    .limit(1)
                )
                previous = session.scalar(select(Run).where(Run.idempotency_key == key))
            if complete:
                identifier = complete.id
            else:
                if previous and previous.status in {"failed", "paused"}:
                    key += ":retry:" + str(uuid.uuid4())
                identifier = create_run(key=key, trigger="baseline")
            execute_run(identifier)
            with session_scope() as session:
                run = session.get(Run, identifier)
                if run.status != "succeeded":
                    raise SystemExit(
                        f"Baseline batch {index + 1} failed. Check the demo provider is running."
                    )
            print(f"Baseline {index + 1}/{args.batches}: materialized and measured")
    elif args.command == "run":
        identifier = create_run()
        execute_run(identifier)
        with session_scope() as session:
            status = session.get(Run, identifier).status
        print(identifier, status)
        if status == "failed":
            raise SystemExit(1)
    elif args.command == "freshness":
        print("New stale datasets:", freshness_sweep())
    elif args.command == "scheduler":
        from .config import settings
        from .jobs import dispatch, redrive_pending

        last_run, last_redrive = 0, 0
        while True:
            try:
                freshness_sweep()
                tick = time.monotonic()
                if tick - last_redrive >= 60:
                    redrive_pending()
                    last_redrive = tick
                if settings.auto_run_seconds > 0 and tick - last_run >= settings.auto_run_seconds:
                    with session_scope() as session:
                        pending = session.scalar(
                            select(func.count()).select_from(Run).where(Run.status.in_(["queued", "running"]))
                        )
                    if not pending:
                        dispatch(create_run(trigger="schedule"))
                        last_run = tick
            except Exception:
                logging.exception("scheduler_tick_failed")
            time.sleep(5)


if __name__ == "__main__":
    main()
