import hashlib
import logging
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import polars as pl
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .catalog import ASSETS
from .config import settings
from .db import now, session_scope
from .detection import detect, health_score
from .incidents import correlate, evaluate_recovery
from .logging_config import configure
from .models import Anomaly, Dataset, Lease, ProductEvent, Profile, QualityResult, Rule, Run, WorkspaceState
from .profiling import profile_frame
from .quality import evaluate
from .sources import CSVConnector, RESTConnector, SQLConnector, generate_batch
from .transforms import transform


configure()
logger = logging.getLogger("data_police.pipeline")


class PipelineBusy(Exception):
    pass


def create_run(key=None, trigger="manual"):
    key = key or str(uuid.uuid4())
    try:
        return _create_run(key, trigger)
    except IntegrityError:
        # Concurrent submissions can both miss the initial read. The unique key is authoritative.
        with session_scope() as session:
            existing = session.scalar(select(Run).where(Run.idempotency_key == key))
            if existing:
                return existing.id
        raise


def _create_run(key, trigger):
    with session_scope() as session:
        existing = session.scalar(select(Run).where(Run.idempotency_key == key))
        if existing:
            return existing.id
        simulator = session.get(WorkspaceState, "simulator")
        identifier = str(uuid.uuid4())
        run = Run(
            id=identifier,
            idempotency_key=key,
            trigger=trigger,
            scenario=simulator.value.get("scenario") if simulator else None,
            seed=int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 100000,
        )
        session.add(run)
        session.add(ProductEvent(kind="run.queued", payload={"id": identifier}))
    return identifier


def acquire_lease(run_id):
    with session_scope() as session:
        expiry = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        # A database compare-and-swap works across API, worker and scheduler processes.
        result = session.execute(
            update(Lease)
            .where(Lease.key == "pipeline", Lease.expires_at < now())
            .values(owner=run_id, expires_at=expiry)
        )
        if result.rowcount != 1:
            raise PipelineBusy("Another materialization is still running")


def heartbeat(run_id):
    with session_scope() as session:
        result = session.execute(
            update(Lease)
            .where(Lease.key == "pipeline", Lease.owner == run_id)
            .values(expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
        )
        if result.rowcount != 1:
            raise RuntimeError("Pipeline lease was lost")


def profile_dict(row):
    return {
        key: getattr(row, key)
        for key in ("row_count", "column_count", "duplicate_rate", "schema", "columns", "metrics")
    }


def materialize_asset(run_id, asset, frame, frames):
    folder = settings.data_dir / "warehouse" / asset.layer / asset.id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{run_id}.parquet"
    temporary = target.with_suffix(".partial")
    frame.write_parquet(temporary, compression="zstd")
    temporary.replace(target)
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    current = profile_frame(frame)
    with session_scope() as session:
        historical = session.scalars(
            select(Profile)
            .where(Profile.dataset_id == asset.id, Profile.health >= 90)
            .order_by(Profile.id.desc())
            .limit(12)
        ).all()[::-1]
        anomalies = detect(current, [profile_dict(p) for p in historical])
        evaluation_inputs = []
        for rule in session.scalars(
            select(Rule).where(Rule.dataset_id == asset.id, Rule.enabled.is_(True))
        ).all():
            try:
                result = evaluate(rule, frame, frames)
            except Exception:
                from .quality import Evaluation

                result = Evaluation(
                    False,
                    1,
                    "Rule could not be evaluated; review its column and parameters",
                    frame.height,
                    [],
                    "error",
                )
            session.add(
                QualityResult(
                    rule_id=rule.id,
                    rule_version=rule.version,
                    dataset_id=asset.id,
                    run_id=run_id,
                    **asdict(result),
                )
            )
            evaluation_inputs.append((rule.kind, rule.severity, result))
            if not result.passed:
                anomalies.append(
                    {
                        "kind": "quality_failure",
                        "column": f"rule:{rule.id}",
                        "severity": rule.severity,
                        "title": rule.name,
                        "observed": result.observed,
                        "expected": result.expected,
                        "method": f"Rule v{rule.version}: {rule.kind}",
                        "details": {
                            "rule_id": rule.id,
                            "rule_version": rule.version,
                            "column": rule.column,
                            "failed_rows": result.failed_count,
                            "total_rows": frame.height,
                            "sample_values": result.sample,
                            "status": result.status,
                        },
                    }
                )
        health, components = health_score(evaluation_inputs, anomalies)
        session.add(
            Profile(
                dataset_id=asset.id,
                run_id=run_id,
                **current,
                health=health,
                path=str(target.resolve()),
                checksum=checksum,
                size_bytes=target.stat().st_size,
                health_components=components,
            )
        )
        dataset = session.get(Dataset, asset.id)
        dataset.health, dataset.status = (
            health,
            "critical" if health < 60 else "warning" if health < 90 else "healthy",
        )
        dataset.last_materialized, dataset.latest_run_id = now(), run_id
        for anomaly in anomalies:
            session.add(Anomaly(dataset_id=asset.id, run_id=run_id, **anomaly))
        session.add(
            ProductEvent(
                kind="dataset.materialized", payload={"id": asset.id, "run_id": run_id, "health": health}
            )
        )
    return target


def execute_run(run_id):
    with session_scope() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise ValueError("Unknown pipeline run")
        if run.status in {"succeeded", "failed", "paused"}:
            return run_id
        scenario, seed = run.scenario, run.seed
    acquire_lease(run_id)
    start = time.monotonic()
    frames, paths, stages = {}, {}, []
    failed_asset = "raw_orders"
    sql = SQLConnector()
    try:
        with session_scope() as session:
            run = session.get(Run, run_id)
            run.status, run.started_at = "running", now()
            session.add(ProductEvent(kind="run.started", payload={"id": run_id}))
        if scenario == "stale":
            with session_scope() as session:
                run = session.get(Run, run_id)
                run.status, run.completed_at = "paused", now()
            return run_id
        inventory_path = generate_batch(run_id, seed, scenario)
        for asset in ASSETS:
            failed_asset = asset.id
            asset_start = time.monotonic()
            heartbeat(run_id)
            with session_scope() as session:
                prior = session.scalar(
                    select(Profile).where(Profile.dataset_id == asset.id, Profile.run_id == run_id)
                )
            if prior:
                frame, path = pl.read_parquet(prior.path), prior.path
            else:
                match asset.id:
                    case "raw_orders" | "raw_order_items":
                        frame = sql.extract(asset.id.removeprefix("raw_"), run_id)
                    case "raw_payments" | "raw_shipments":
                        frame = RESTConnector().extract(asset.id.removeprefix("raw_"), run_id)
                    case "raw_inventory":
                        frame, _ = CSVConnector().extract(inventory_path)
                    case "dim_countries" | "dim_customers" | "dim_products":
                        frame = sql.extract(asset.id.removeprefix("dim_"), run_id)
                    case _:
                        frame = transform(asset.id, frames, paths, scenario)
                path = materialize_asset(run_id, asset, frame, frames)
            frames[asset.id], paths[asset.id] = frame, path
            stages.append(
                {
                    "asset": asset.id,
                    "status": "succeeded",
                    "rows": frame.height,
                    "duration_ms": int((time.monotonic() - asset_start) * 1000),
                }
            )
            with session_scope() as session:
                session.get(Run, run_id).stages = list(stages)
        with session_scope() as session:
            anomalies = session.scalars(
                select(Anomaly).where(Anomaly.run_id == run_id).order_by(Anomaly.id)
            ).all()
            correlate(session, anomalies)
            evaluate_recovery(session, list(frames), run_id)
            run = session.get(Run, run_id)
            run.status, run.completed_at, run.duration_ms = (
                "succeeded",
                now(),
                int((time.monotonic() - start) * 1000),
            )
            run.records = sum(frames[a.id].height for a in ASSETS if not a.parents)
            session.add(ProductEvent(kind="run.completed", payload={"id": run_id}))
        logger.info("pipeline_completed", extra={"run_id": run_id, "asset_count": len(frames)})
    except Exception as exc:
        logger.exception("pipeline_failed", extra={"run_id": run_id, "dataset": failed_asset})
        # Errors exposed to clients deliberately exclude connection strings and raw exception payloads.
        safe_error = f"{failed_asset}: {type(exc).__name__}. See local service logs for diagnosis."
        with session_scope() as session:
            run = session.get(Run, run_id)
            run.status, run.error, run.completed_at = "failed", safe_error, now()
            run.duration_ms = int((time.monotonic() - start) * 1000)
            run.stages = stages + [{"asset": failed_asset, "status": "failed", "error": safe_error}]
            session.get(Dataset, failed_asset).status = "critical"
            session.get(Dataset, failed_asset).health = 30
            failure = Anomaly(
                dataset_id=failed_asset,
                run_id=run_id,
                kind="pipeline_failure",
                column="",
                severity="critical",
                title="Materialization failed",
                expected="Successful extraction and transformation",
                method="Pipeline execution status",
                details={
                    "error_type": type(exc).__name__,
                    "attempt_policy": "HTTP: 3 attempts; transformation: fail without retry",
                },
            )
            session.add(failure)
            session.flush()
            anomalies = session.scalars(
                select(Anomaly).where(Anomaly.run_id == run_id).order_by(Anomaly.id)
            ).all()
            correlate(session, anomalies)
            session.add(ProductEvent(kind="run.failed", payload={"id": run_id}))
    finally:
        sql.close()
        with session_scope() as session:
            session.execute(
                update(Lease)
                .where(Lease.key == "pipeline", Lease.owner == run_id)
                .values(owner="", expires_at="")
            )
    return run_id


def freshness_sweep():
    timestamp = datetime.now(timezone.utc)
    with session_scope() as session:
        stale = [
            d
            for d in session.scalars(select(Dataset)).all()
            if d.last_materialized
            and d.status != "stale"
            and (timestamp - datetime.fromisoformat(d.last_materialized)).total_seconds()
            > settings.freshness_seconds
        ]
        if not stale:
            return 0
        identifier = str(uuid.uuid4())
        session.add(
            Run(
                id=identifier,
                idempotency_key="freshness:" + identifier,
                trigger="freshness",
                status="succeeded",
                completed_at=now(),
            )
        )
        session.flush()
        anomalies = []
        for dataset in stale:
            age = (timestamp - datetime.fromisoformat(dataset.last_materialized)).total_seconds()
            anomaly = Anomaly(
                dataset_id=dataset.id,
                run_id=identifier,
                kind="freshness",
                column="",
                severity="critical",
                title="Dataset is stale",
                observed=round(age),
                expected=f"Materialization within {settings.freshness_seconds} seconds",
                method="Independent wall-clock freshness sweep",
                details={
                    "last_materialized": dataset.last_materialized,
                    "threshold_seconds": settings.freshness_seconds,
                },
            )
            session.add(anomaly)
            anomalies.append(anomaly)
            dataset.status, dataset.health = "stale", min(dataset.health or 100, 40)
        session.flush()
        correlate(session, anomalies)
        session.add(ProductEvent(kind="freshness.updated", payload={"count": len(stale)}))
    return len(stale)
