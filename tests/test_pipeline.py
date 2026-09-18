from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from data_police.catalog import ASSETS
from data_police.db import session_scope
from data_police.incidents import impact
from data_police.investigation import investigate
from data_police.models import Anomaly, Dataset, Incident, Profile, Run, WorkspaceState
from data_police.pipeline import create_run, execute_run, freshness_sweep


def run(scenario=None):
    with session_scope() as session:
        session.get(WorkspaceState, "simulator").value = {"scenario": scenario}
    with session_scope() as session:
        sequence = session.scalar(select(func.count()).select_from(Run))
    identifier = create_run(key=f"test-batch-{sequence}")
    execute_run(identifier)
    return identifier


def test_healthy_pipeline_real_http_and_parquet(live_provider):
    identifier = run()
    with session_scope() as session:
        result = session.get(Run, identifier)
        assert result.status == "succeeded", result.error
        assert len(result.stages) == len(ASSETS)
        assert session.scalar(select(func.count()).select_from(Profile)) == len(ASSETS)
        assert session.scalar(select(func.count()).select_from(Anomaly)) == 0
        assert session.scalar(select(func.count()).select_from(Incident)) == 0
        assert all(d.health == 100 for d in session.scalars(select(Dataset)))


def test_idempotent_terminal_run(live_provider):
    identifier = run()
    execute_run(identifier)
    with session_scope() as session:
        assert session.scalar(
            select(func.count()).select_from(Profile).where(Profile.run_id == identifier)
        ) == len(ASSETS)


def test_concurrent_submissions_share_one_durable_run():
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=4) as pool:
        identifiers = list(pool.map(lambda _: create_run(key="shared-request"), range(8)))
    assert len(set(identifiers)) == 1
    with session_scope() as session:
        assert session.scalar(select(func.count()).select_from(Run)) == 1


def test_country_incident_root_cause_report_and_recovery(live_provider):
    for _ in range(8):
        run()
    identifier = run("country_code")
    with session_scope() as session:
        incidents = session.scalars(select(Incident).where(Incident.status != "resolved")).all()
        assert len(incidents) == 1
        incident = incidents[0]
        assert incident.root_dataset_id == "raw_payments"
        assert "fact_orders" in impact(session, incident.id)["observed"]
        assert "country_revenue" in impact(session, incident.id)["observed"]
        assert not session.scalar(
            select(Anomaly.id).where(Anomaly.run_id == identifier, Anomaly.kind == "schema_drift")
        )
        report = investigate(session, incident.id)
        assert report.provider == "deterministic"
        assert report.report["verified"][0]["evidence_ids"]
        incident_id = incident.id
    run()
    with session_scope() as session:
        assert session.get(Incident, incident_id).status == "monitoring", [
            (a.dataset_id, a.kind, a.title, a.details)
            for a in session.scalars(select(Anomaly).order_by(Anomaly.id.desc()).limit(15))
        ]
    run()
    with session_scope() as session:
        assert session.get(Incident, incident_id).status == "resolved"


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("null_spike", "raw_orders"),
        ("duplicates", "raw_orders"),
        ("missing_records", "fact_orders"),
        ("invalid_values", "raw_payments"),
        ("schema_removed", "raw_payments"),
        ("bad_transform", "fact_orders"),
        ("api_failure", "raw_payments"),
    ],
)
def test_fault_changes_data_and_generates_anomalies(live_provider, scenario, expected):
    run()
    identifier = run(scenario)
    with session_scope() as session:
        assert session.scalar(
            select(Anomaly.id).where(Anomaly.run_id == identifier, Anomaly.dataset_id == expected)
        )
        assert session.scalar(select(Incident.id))
        if scenario in {"api_failure", "schema_removed"}:
            assert session.get(Run, identifier).status == "failed"


def test_distribution_shift(live_provider):
    for _ in range(8):
        run()
    identifier = run("distribution")
    with session_scope() as session:
        assert session.scalar(
            select(Anomaly.id).where(Anomaly.run_id == identifier, Anomaly.kind == "distribution_drift")
        )


def test_freshness_is_independent_and_deduplicated(live_provider):
    run()
    with session_scope() as session:
        session.get(Dataset, "raw_orders").last_materialized = (
            datetime.now(timezone.utc) - timedelta(minutes=5)
        ).isoformat()
    assert freshness_sweep() == 1
    assert freshness_sweep() == 0
    with session_scope() as session:
        assert session.get(Dataset, "raw_orders").status == "stale"


def test_paused_pipeline_does_not_fake_profiles(live_provider):
    identifier = run("stale")
    with session_scope() as session:
        assert session.get(Run, identifier).status == "paused"
        assert session.scalar(select(func.count()).select_from(Profile)) == 0
