import dagster as dg
from sqlalchemy import select

from data_police.catalog import ASSETS
from data_police.db import session_scope
from data_police.jobs import materialize_task
from data_police.models import Run
from data_police.orchestration import retail_assets
from data_police.pipeline import create_run


def test_dagster_executes_real_assets(live_provider):
    result = dg.materialize([retail_assets])
    assert result.success
    materializations = [e for e in result.all_events if e.event_type_value == "ASSET_MATERIALIZATION"]
    assert len(materializations) == len(ASSETS)
    with session_scope() as session:
        run = session.scalar(select(Run).where(Run.trigger == "dagster"))
        assert run.status == "succeeded"
        assert run.records > 0


def test_celery_task_executes_pipeline_eagerly(live_provider):
    identifier = create_run(key="celery-eager-test")
    result = materialize_task.apply(args=[identifier])
    assert result.successful()
    with session_scope() as session:
        assert session.get(Run, identifier).status == "succeeded"
