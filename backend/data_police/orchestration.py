"""Dagster materializations backed by the same executable asset contract as the product."""

import dagster as dg
from sqlalchemy import select

from .catalog import ASSETS
from .db import session_scope
from .models import Profile, Run
from .pipeline import create_run, execute_run


@dg.multi_asset(
    specs=[
        dg.AssetSpec(
            key=asset.id,
            deps=list(asset.parents),
            description=asset.description,
            metadata={"layer": asset.layer, "owner": asset.owner},
        )
        for asset in ASSETS
    ],
    can_subset=False,
)
def retail_assets(context: dg.AssetExecutionContext):
    identifier = create_run(key="dagster:" + context.run.run_id, trigger="dagster")
    execute_run(identifier)

    with session_scope() as session:
        run = session.get(Run, identifier)
        profiles = {
            profile.dataset_id: profile
            for profile in session.scalars(
                select(Profile).where(Profile.run_id == identifier)
            ).all()
        }

    for asset in ASSETS:
        profile = profiles.get(asset.id)
        if profile is None:
            continue

        yield dg.MaterializeResult(
            asset_key=profile.dataset_id,
            metadata={
                "rows": profile.row_count,
                "health": profile.health or 0,
                "parquet": dg.MetadataValue.path(profile.path),
                "sha256": profile.checksum,
                "data_police_run": identifier,
            },
        )

    if run.status != "succeeded":
        raise dg.Failure(
            description=f"Data Police pipeline ended with {run.status}: {run.error or 'source paused'}"
        )


retail_job = dg.define_asset_job(
    "retail_reliability",
    selection=dg.AssetSelection.assets(retail_assets),
)

retail_schedule = dg.ScheduleDefinition(
    job=retail_job,
    cron_schedule="*/2 * * * *",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)

defs = dg.Definitions(
    assets=[retail_assets],
    jobs=[retail_job],
    schedules=[retail_schedule],
)
