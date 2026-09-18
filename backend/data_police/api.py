import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from . import __version__
from .catalog import SCENARIOS, initialize_catalog
from .config import settings
from .db import Session, now, session_scope
from .incidents import graph_edges, impact, incident_anomalies
from .investigation import investigate
from .jobs import dispatch
from .lineage import distances
from .models import (
    Anomaly,
    Candidate,
    ChangeEvent,
    Dataset,
    Evidence,
    Incident,
    IncidentEvent,
    Investigation,
    ProductEvent,
    Profile,
    QualityResult,
    Rule,
    RuleVersion,
    Run,
    WorkspaceState,
)
from .pipeline import create_run
from .quality import validate_rule
from .security import current_user, issue_session, verify_password
from .sources import RESTConnector, SQLConnector


logger = logging.getLogger("data_police.api")


def serialize(obj, exclude=()):
    return {
        column.name: getattr(obj, column.name)
        for column in obj.__table__.columns
        if column.name not in exclude
    }


def database():
    with Session() as session:
        yield session


@asynccontextmanager
async def lifespan(app):
    settings.prepare()
    with session_scope() as session:
        initialize_catalog(session)
    yield


app = FastAPI(
    title="Data Police API",
    version=__version__,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/openapi.json",
)


@app.middleware("http")
async def request_controls(request: Request, call_next):
    request_id, started = str(uuid.uuid4()), time.monotonic()
    if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        if request.headers.get("x-dp-request") != "1":
            return JSONResponse({"detail": "Required request header is missing"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin not in settings.allowed_origins.split(","):
            return JSONResponse({"detail": "Origin is not allowed"}, status_code=403)
        try:
            if int(request.headers.get("content-length", "0")) > 100000:
                return JSONResponse({"detail": "Request body is too large"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid content length"}, status_code=400)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    logger.info(
        "http_request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
        },
    )
    return response


@app.exception_handler(Exception)
async def safe_error(request, exc):
    logger.error("unhandled_api_error", exc_info=(type(exc), exc, exc.__traceback__))
    return JSONResponse(
        {"detail": "The request could not be completed. Check service logs using the request time."},
        status_code=500,
    )


class LoginBody(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=500)


@app.post("/api/auth/login")
def login(body: LoginBody, request: Request, response: Response):
    verify_password(request, body.email, body.password)
    response.set_cookie(
        "dp_session",
        issue_session(body.email),
        max_age=28800,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return {"email": body.email, "role": "admin"}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("dp_session", path="/")
    return {"ok": True}


@app.get("/api/health")
def health(session=Depends(database)):
    session.execute(select(1))
    return {"status": "ok", "version": __version__}


router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


@router.get("/auth/me")
def me(user=Depends(current_user)):
    return user


@router.get("/overview")
def overview(session=Depends(database)):
    datasets = session.scalars(select(Dataset).order_by(Dataset.id)).all()
    incidents = session.scalars(
        select(Incident).where(Incident.status != "resolved").order_by(Incident.updated_at.desc()).limit(8)
    ).all()
    runs = session.scalars(
        select(Run).where(Run.trigger != "freshness").order_by(Run.started_at.desc()).limit(24)
    ).all()
    trend = session.execute(
        select(
            Profile.run_id,
            func.avg(Profile.health),
            func.min(Profile.created_at),
            func.sum(Profile.row_count),
        )
        .group_by(Profile.run_id)
        .order_by(func.min(Profile.created_at).desc())
        .limit(24)
    ).all()[::-1]
    stats = {
        "datasets": len(datasets),
        "healthy": sum(d.status == "healthy" for d in datasets),
        "degraded": sum(d.status in {"critical", "warning", "stale"} for d in datasets),
        "active_incidents": session.scalar(
            select(func.count()).select_from(Incident).where(Incident.status != "resolved")
        ),
        "health": round(
            sum(d.health or 0 for d in datasets) / max(1, sum(d.health is not None for d in datasets)), 1
        ),
        "rules": session.scalar(select(func.count()).select_from(Rule).where(Rule.enabled.is_(True))),
    }
    return {
        "stats": stats,
        "datasets": [serialize(d) for d in datasets],
        "incidents": [serialize(i) for i in incidents],
        "runs": [serialize(r) for r in runs],
        "trend": [{"run_id": r[0], "health": round(r[1] or 0, 1), "at": r[2], "rows": r[3]} for r in trend],
        "anomalies": [
            serialize(a) for a in session.scalars(select(Anomaly).order_by(Anomaly.id.desc()).limit(8))
        ],
        "simulator": session.get(WorkspaceState, "simulator").value,
        "synthetic": True,
    }


@router.get("/datasets")
def datasets(session=Depends(database)):
    return [serialize(d) for d in session.scalars(select(Dataset).order_by(Dataset.id))]


@router.get("/datasets/{identifier}")
def dataset_detail(identifier: str, session=Depends(database)):
    dataset = session.get(Dataset, identifier)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    profiles = session.scalars(
        select(Profile).where(Profile.dataset_id == identifier).order_by(Profile.id.desc()).limit(24)
    ).all()
    latest = serialize(profiles[0], exclude={"path"}) if profiles else None
    if latest:
        latest["columns"] = {
            key: {k: v for k, v in val.items() if k != "sample"} for key, val in latest["columns"].items()
        }
    rules = session.scalars(select(Rule).where(Rule.dataset_id == identifier)).all()
    results = session.scalars(
        select(QualityResult)
        .where(QualityResult.dataset_id == identifier)
        .order_by(QualityResult.id.desc())
        .limit(40)
    ).all()
    return {
        "dataset": serialize(dataset),
        "latest": latest,
        "history": [
            {
                "at": p.created_at,
                "rows": p.row_count,
                "health": p.health,
                "duplicate_rate": p.duplicate_rate,
                "metrics": p.metrics,
            }
            for p in profiles[::-1]
        ],
        "baseline_runs": session.scalar(
            select(func.count())
            .select_from(Profile)
            .where(Profile.dataset_id == identifier, Profile.health >= 90)
        ),
        "rules": [serialize(r) for r in rules],
        "results": [serialize(r) for r in results],
        "upstream": distances(identifier, graph_edges(session), reverse=True),
        "downstream": distances(identifier, graph_edges(session)),
        "anomalies": [
            serialize(a)
            for a in session.scalars(
                select(Anomaly).where(Anomaly.dataset_id == identifier).order_by(Anomaly.id.desc()).limit(15)
            )
        ],
    }


class OwnerBody(BaseModel):
    owner: str = Field(min_length=1, max_length=120)


@router.patch("/datasets/{identifier}")
def update_dataset(identifier: str, body: OwnerBody, user=Depends(current_user)):
    with session_scope() as session:
        dataset = session.get(Dataset, identifier)
        if not dataset:
            raise HTTPException(404, "Dataset not found")
        dataset.owner = body.owner
        session.add(
            ChangeEvent(
                component=identifier,
                kind="ownership",
                description="Dataset owner changed",
                actor=user["email"],
            )
        )
    return {"ok": True}


@router.get("/lineage")
def lineage(session=Depends(database)):
    return {
        "nodes": [serialize(d) for d in session.scalars(select(Dataset))],
        "edges": [{"source": s, "target": t} for s, t in graph_edges(session)],
    }


@router.get("/runs")
def runs(session=Depends(database)):
    return [
        serialize(r)
        for r in session.scalars(
            select(Run).where(Run.trigger != "freshness").order_by(Run.started_at.desc()).limit(100)
        )
    ]


@router.post("/runs", status_code=202)
def run_pipeline(request: Request):
    key = request.headers.get("idempotency-key", str(uuid.uuid4()))
    if len(key) > 100:
        raise HTTPException(422, "Idempotency key is too long")
    run_id = create_run(key=key)
    try:
        dispatch(run_id)
    except Exception:
        # The durable queued row survives broker outages and is redriven by the scheduler.
        return {
            "id": run_id,
            "dispatch": "pending",
            "message": "Saved to the durable queue; awaiting worker delivery.",
        }
    return {"id": run_id, "dispatch": "submitted"}


@router.get("/incidents")
def incidents(session=Depends(database)):
    return [
        serialize(i)
        for i in session.scalars(select(Incident).order_by(Incident.updated_at.desc()).limit(100))
    ]


@router.get("/incidents/{identifier}")
def incident_detail(identifier: int, session=Depends(database)):
    incident = session.get(Incident, identifier)
    if not incident:
        raise HTTPException(404, "Incident not found")
    latest = session.scalar(
        select(Investigation)
        .where(Investigation.incident_id == identifier)
        .order_by(Investigation.id.desc())
        .limit(1)
    )
    return {
        "incident": serialize(incident),
        "impact": impact(session, identifier),
        "anomalies": [serialize(a) for a in incident_anomalies(session, identifier)],
        "evidence": [
            serialize(e)
            for e in session.scalars(
                select(Evidence).where(Evidence.incident_id == identifier).order_by(Evidence.id)
            )
        ],
        "timeline": [
            serialize(e)
            for e in session.scalars(
                select(IncidentEvent)
                .where(IncidentEvent.incident_id == identifier)
                .order_by(IncidentEvent.id)
            )
        ],
        "candidates": [
            serialize(c)
            for c in session.scalars(
                select(Candidate).where(Candidate.incident_id == identifier).order_by(Candidate.score.desc())
            )
        ],
        "investigation": serialize(latest) if latest else None,
    }


class IncidentUpdate(BaseModel):
    status: Literal["open", "investigating"] | None = None
    owner: str | None = Field(None, min_length=1, max_length=120)
    note: str | None = Field(None, max_length=2000)


@router.patch("/incidents/{identifier}")
def update_incident(identifier: int, body: IncidentUpdate, user=Depends(current_user)):
    with session_scope() as session:
        incident = session.get(Incident, identifier)
        if not incident:
            raise HTTPException(404, "Incident not found")
        if body.status:
            if incident.status == "resolved":
                raise HTTPException(
                    409, "Resolved incidents are historical. A new recurrence opens a new incident."
                )
            incident.status = body.status
        if body.owner:
            incident.owner = body.owner
        incident.updated_at = now()
        text = body.note or f"Status: {incident.status}. Owner: {incident.owner}."
        session.add(
            IncidentEvent(incident_id=identifier, kind="operator", message=f"{user['email']}: {text}")
        )
        session.add(ProductEvent(kind="incident.updated", payload={"id": identifier}))
    return {"ok": True}


class InvestigateBody(BaseModel):
    use_llm: bool = False


@router.post("/incidents/{identifier}/investigate")
def investigation(identifier: int, body: InvestigateBody):
    with session_scope() as session:
        if not session.get(Incident, identifier):
            raise HTTPException(404, "Incident not found")
        try:
            record = investigate(session, identifier, body.use_llm)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        except Exception:
            raise HTTPException(
                502, "The AI provider did not return a valid response. Use the evidence-based report instead."
            ) from None
        session.add(
            IncidentEvent(
                incident_id=identifier,
                kind="investigation",
                message=f"Investigation report generated using {record.provider}.",
            )
        )
        return serialize(record)


@router.get("/incidents/{identifier}/report")
def export_report(identifier: int, session=Depends(database)):
    data = incident_detail(identifier, session)
    incident = data["incident"]
    output = [
        f"# DP-{identifier + 1000}: {incident['title']}",
        "",
        f"Status: {incident['status']}",
        f"Evidence rank: {incident['root_score']}/100 (not a probability)",
        "",
        "## Observed affected datasets",
        ", ".join(data["impact"]["observed"]),
        "",
        "## Evidence",
    ]
    if data["investigation"]:
        report = data["investigation"]["report"]
        output = output[:-1] + ["## Investigation", report["summary"], ""]
        for key in ("verified", "inference", "hypotheses", "recommendations"):
            output += ["## " + key.capitalize(), ""]
            for statement in report[key]:
                references = ", ".join(f"E-{item}" for item in statement["evidence_ids"])
                output += [f"- {statement['text']} [{references}]", ""]
        output += ["## Evidence", ""]
    for evidence in data["evidence"]:
        output.extend(
            [
                f"### E-{evidence['id']}: {evidence['title']}",
                "```json",
                json.dumps(evidence["facts"], indent=2),
                "```",
                "",
            ]
        )
    output += ["## Timeline", ""]
    for event in data["timeline"]:
        output += [f"- {event['created_at']}: {event['message']}"]
    output += ["## Limitations", "Synthetic demo data. Heuristic root-cause ranking is not causal proof."]
    return PlainTextResponse(
        "\n".join(output),
        headers={"Content-Disposition": f'attachment; filename="DP-{identifier + 1000}-report.md"'},
    )


class RuleBody(BaseModel):
    dataset_id: str = Field(max_length=80)
    name: str = Field(min_length=3, max_length=160)
    kind: str = Field(max_length=32)
    column: str | None = Field(None, max_length=80)
    params: dict = Field(default_factory=dict)
    severity: Literal["warning", "critical"] = "warning"


@router.get("/rules")
def rules(session=Depends(database)):
    return [serialize(r) for r in session.scalars(select(Rule).order_by(Rule.id))]


@router.post("/rules", status_code=201)
def add_rule(body: RuleBody, user=Depends(current_user)):
    try:
        validate_rule(body.kind, body.column, body.params)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    with session_scope() as session:
        if not session.get(Dataset, body.dataset_id):
            raise HTTPException(422, "Unknown dataset")
        if body.kind == "reference" and not session.get(Dataset, body.params["dataset"]):
            raise HTTPException(422, "Unknown reference dataset")
        rule = Rule(**body.model_dump())
        session.add(rule)
        session.flush()
        session.add(RuleVersion(rule_id=rule.id, version=1, definition=body.model_dump() | {"enabled": True}))
        session.add(
            ChangeEvent(
                component=body.dataset_id, kind="rule_created", description=body.name, actor=user["email"]
            )
        )
        return serialize(rule)


class RuleToggle(BaseModel):
    enabled: bool


@router.patch("/rules/{identifier}")
def toggle_rule(identifier: int, body: RuleToggle, user=Depends(current_user)):
    with session_scope() as session:
        rule = session.get(Rule, identifier)
        if not rule:
            raise HTTPException(404, "Rule not found")
        rule.enabled = body.enabled
        rule.version += 1
        session.add(RuleVersion(rule_id=rule.id, version=rule.version, definition=serialize(rule)))
        session.add(
            ChangeEvent(
                component=rule.dataset_id,
                kind="rule_updated",
                description=f"{rule.name}: {'enabled' if body.enabled else 'disabled'}",
                actor=user["email"],
                version=str(rule.version),
            )
        )
    return {"ok": True}


@router.get("/simulator")
def simulator(session=Depends(database)):
    return {
        "enabled": settings.enable_simulator,
        "scenarios": SCENARIOS,
        "active": session.get(WorkspaceState, "simulator").value,
        "freshness_seconds": settings.freshness_seconds,
    }


class ScenarioBody(BaseModel):
    scenario: str | None = None


@router.post("/simulator")
def change_scenario(body: ScenarioBody, user=Depends(current_user)):
    if not settings.enable_simulator:
        raise HTTPException(403, "Simulator is disabled for this environment")
    if body.scenario and body.scenario not in {s["id"] for s in SCENARIOS}:
        raise HTTPException(422, "Unknown scenario")
    with session_scope() as session:
        if session.scalar(select(Run.id).where(Run.status.in_(["queued", "running"])).limit(1)):
            raise HTTPException(409, "Wait for the active pipeline run before changing the source scenario")
        session.get(WorkspaceState, "simulator").value = {"scenario": body.scenario, "changed_at": now()}
        target = next((s["target"] for s in SCENARIOS if s["id"] == body.scenario), "demo_sources")
        session.add(
            ChangeEvent(
                component=target,
                kind="source_scenario",
                description=f"Demo behavior changed to {body.scenario or 'healthy'}",
                actor=user["email"],
            )
        )
        session.add(ProductEvent(kind="simulator.changed", payload={"scenario": body.scenario}))
    return {"ok": True, "message": "Source behavior updated. Run the pipeline to observe its effects."}


@router.get("/changes")
def changes(session=Depends(database)):
    return [
        serialize(c) for c in session.scalars(select(ChangeEvent).order_by(ChangeEvent.id.desc()).limit(100))
    ]


@router.get("/settings")
def workspace_settings(session=Depends(database)):
    return {
        "workspace": "Northstar Retail",
        "environment": settings.env,
        "version": __version__,
        "synthetic": True,
        "database": "PostgreSQL"
        if settings.database_url.startswith("postgres")
        else "SQLite (local development)",
        "executor": settings.executor,
        "freshness_seconds": settings.freshness_seconds,
        "auto_run_seconds": settings.auto_run_seconds,
        "ai_configured": bool(settings.llm_base_url and settings.llm_model),
        "simulator_enabled": settings.enable_simulator,
        "baseline_minimum": 8,
        "source_types": [
            "PostgreSQL"
            if settings.source_database_url.startswith("postgres")
            else "SQLite (local development)",
            "REST API",
            "CSV",
        ],
        "queued_jobs": session.scalar(select(func.count()).select_from(Run).where(Run.status == "queued")),
    }


@router.post("/sources/{kind}/test")
def test_source(kind: Literal["database", "api", "csv"]):
    try:
        if kind == "database":
            connector = SQLConnector()
            try:
                return connector.test()
            finally:
                connector.close()
        if kind == "api":
            return RESTConnector().test()
        return {
            "ok": (settings.data_dir / "feeds").is_dir(),
            "message": "Feed directory exists"
            if (settings.data_dir / "feeds").is_dir()
            else "No feeds yet. Run ingestion first.",
        }
    except Exception:
        raise HTTPException(
            502, "Connection check failed. Verify the source service and environment configuration."
        ) from None


@router.get("/events")
async def events(request: Request):
    try:
        cursor = max(0, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        raise HTTPException(400, "Invalid event cursor") from None
    if not cursor:
        with Session() as session:
            cursor = session.scalar(select(func.max(ProductEvent.id))) or 0

    def read_events(after):
        with Session() as session:
            return [
                serialize(e)
                for e in session.scalars(
                    select(ProductEvent).where(ProductEvent.id > after).order_by(ProductEvent.id).limit(100)
                )
            ]

    async def stream():
        nonlocal cursor
        ticks = 0
        yield ": connected\n\n"
        while not await request.is_disconnected():
            current_user(request)  # Enforce session expiry on long-lived connections too.
            pending = await asyncio.to_thread(read_events, cursor)
            for event in pending:
                cursor = event["id"]
                yield f"id: {cursor}\nevent: update\ndata: {json.dumps(event)}\n\n"
            ticks += 1
            if ticks % 15 == 0:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


app.include_router(router)
web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
if web_dist.exists():
    app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")
    if (web_dist / "api-doc-assets").exists():
        app.mount(
            "/api-doc-assets", StaticFiles(directory=web_dist / "api-doc-assets"), name="api-doc-assets"
        )

    @app.get("/api/docs", include_in_schema=False, dependencies=[Depends(current_user)])
    def interactive_docs():
        return HTMLResponse(
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Data Police API</title><link rel="stylesheet" href="/api-doc-assets/swagger-ui.css"></head><body><div id="swagger-ui"></div><script src="/api-doc-assets/swagger-ui-bundle.js"></script><script src="/api-doc-assets/bootstrap.js"></script></body></html>'
        )

    @app.get("/favicon.svg")
    def favicon():
        return FileResponse(web_dist / "favicon.svg")

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Endpoint not found")
        return FileResponse(web_dist / "index.html")
