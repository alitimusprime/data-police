from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from .db import now
from .lineage import distances, rank_candidates, related
from .models import (
    Anomaly,
    Candidate,
    Dataset,
    Evidence,
    Incident,
    IncidentAnomaly,
    IncidentEvent,
    LineageEdge,
    ProductEvent,
)


def graph_edges(session):
    return [(e.source_id, e.target_id) for e in session.scalars(select(LineageEdge)).all()]


def incident_anomalies(session, incident_id):
    return session.scalars(
        select(Anomaly)
        .join(IncidentAnomaly, IncidentAnomaly.anomaly_id == Anomaly.id)
        .where(IncidentAnomaly.incident_id == incident_id)
        .order_by(Anomaly.created_at, Anomaly.id)
    ).all()


def refresh_ranking(session, incident):
    anomalies = incident_anomalies(session, incident.id)
    evidence_map = {
        e.anomaly_id: e.id
        for e in session.scalars(select(Evidence).where(Evidence.incident_id == incident.id)).all()
    }
    ranking = rank_candidates(anomalies, graph_edges(session), evidence_map)
    session.execute(delete(Candidate).where(Candidate.incident_id == incident.id))
    for candidate in ranking:
        session.add(Candidate(incident_id=incident.id, **candidate))
    if ranking:
        best = ranking[0]
        incident.root_dataset_id = best["dataset_id"]
        incident.root_score = best["score"]
        root_anomaly = next(a for a in anomalies if a.dataset_id == best["dataset_id"])
        incident.title = f"{root_anomaly.title.split(' · ')[0]} in {best['dataset_id']}"


def correlate(session, anomalies):
    if not anomalies:
        return []
    edges = graph_edges(session)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    active = session.scalars(
        select(Incident)
        .where(Incident.status != "resolved", Incident.updated_at >= cutoff)
        .order_by(Incident.id.desc())
    ).all()
    affected = {}
    for anomaly in anomalies:
        # Same batch alone is insufficient. Require an actual directed lineage relationship.
        target = None
        for candidate in active:
            prior = incident_anomalies(session, candidate.id)
            if any(related(anomaly.dataset_id, other.dataset_id, edges) for other in prior):
                target = candidate
                break
        if target is None:
            target = Incident(
                title=anomaly.title, severity=anomaly.severity, root_dataset_id=anomaly.dataset_id
            )
            session.add(target)
            session.flush()
            active.insert(0, target)
            session.add(
                IncidentEvent(
                    incident_id=target.id,
                    kind="detected",
                    message=f"A {anomaly.kind.replace('_', ' ')} monitor opened this incident.",
                )
            )
        if target.status == "monitoring":
            session.add(
                IncidentEvent(
                    incident_id=target.id,
                    kind="regression",
                    message="A related anomaly recurred during recovery monitoring.",
                )
            )
            target.status = "investigating"
        target.updated_at, target.healthy_runs = now(), 0
        if anomaly.severity == "critical":
            target.severity = "critical"
        session.add(IncidentAnomaly(incident_id=target.id, anomaly_id=anomaly.id))
        session.add(
            Evidence(
                incident_id=target.id,
                anomaly_id=anomaly.id,
                title=anomaly.title,
                facts={
                    "dataset": anomaly.dataset_id,
                    "run_id": anomaly.run_id,
                    "kind": anomaly.kind,
                    "observed": anomaly.observed,
                    "expected": anomaly.expected,
                    "method": anomaly.method,
                    "details": anomaly.details,
                    "observed_at": anomaly.created_at,
                },
            )
        )
        session.add(
            IncidentEvent(
                incident_id=target.id, kind="evidence", message=f"{anomaly.dataset_id}: {anomaly.title}"
            )
        )
        session.flush()
        affected[target.id] = target
    for incident in affected.values():
        refresh_ranking(session, incident)
        session.add(ProductEvent(kind="incident.updated", payload={"id": incident.id}))
    return list(affected)


def evaluate_recovery(session, materialized_ids, run_id):
    for incident in session.scalars(select(Incident).where(Incident.status != "resolved")).all():
        prior = incident_anomalies(session, incident.id)
        datasets = {a.dataset_id for a in prior}
        if any(a.run_id == run_id for a in prior):
            continue
        if not datasets.issubset(set(materialized_ids)):
            continue
        if any(session.get(Dataset, key).status != "healthy" for key in datasets):
            continue
        incident.healthy_runs += 1
        incident.status = "monitoring" if incident.healthy_runs < 2 else "resolved"
        incident.updated_at = now()
        if incident.status == "resolved":
            incident.resolved_at = now()
        session.add(
            IncidentEvent(
                incident_id=incident.id,
                kind=incident.status,
                message=f"All observed affected datasets passed monitoring in run {run_id[:8]}. Consecutive healthy runs: {incident.healthy_runs}/2.",
            )
        )
        session.add(ProductEvent(kind="incident.updated", payload={"id": incident.id}))


def impact(session, incident_id):
    anomalies = incident_anomalies(session, incident_id)
    confirmed = {a.dataset_id for a in anomalies}
    potential = set()
    for asset in confirmed:
        potential |= set(distances(asset, graph_edges(session)))
    return {"observed": sorted(confirmed), "potential": sorted(potential - confirmed)}
