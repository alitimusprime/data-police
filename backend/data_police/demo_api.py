from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import select

from .sources import ENTITY_FIELDS, SOURCE_TABLES, source_engine, source_metadata, source_state


@asynccontextmanager
async def lifespan(app):
    engine = source_engine()
    source_metadata.create_all(engine)
    app.state.engine = engine
    yield
    engine.dispose()


app = FastAPI(title="Northstar demo provider", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "synthetic": True}


@app.get("/{entity}")
def extract(
    entity: str,
    batch_id: str = Query(max_length=40),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=250),
):
    if entity not in {"payments", "shipments"}:
        raise HTTPException(404, "Unknown provider resource")
    with app.state.engine.connect() as conn:
        mode = conn.scalar(select(source_state.c.value).where(source_state.c.key == "scenario"))
        if entity == "payments" and mode == "api_failure":
            raise HTTPException(503, "Simulated payment-provider outage")
        table = SOURCE_TABLES[entity]
        result = (
            conn.execute(
                select(table)
                .where(table.c.batch_id == batch_id)
                .order_by(table.c.row_number)
                .offset(offset)
                .limit(limit + 1)
            )
            .mappings()
            .all()
        )
        rows = [
            {
                key: row[key]
                for key in ENTITY_FIELDS[entity]
                if not (entity == "payments" and mode == "schema_removed" and key == "payment_method")
            }
            for row in result
        ]
    return {
        "items": rows[:limit],
        "next_offset": offset + limit if len(rows) > limit else None,
        "synthetic": True,
    }
