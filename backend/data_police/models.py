from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, now


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    layer: Mapped[str] = mapped_column(String(24))
    source: Mapped[str] = mapped_column(String(40))
    owner: Mapped[str] = mapped_column(String(120), default="Data Platform")
    description: Mapped[str] = mapped_column(Text, default="")
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    health: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="unknown")
    latest_run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_materialized: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class Run(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    trigger: Mapped[str] = mapped_column(String(32), default="manual")
    started_at: Mapped[str] = mapped_column(String(40), default=now)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    records: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stages: Mapped[list] = mapped_column(JSON, default=list)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    scenario: Mapped[str | None] = mapped_column(String(40), nullable=True)
    seed: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (Index("ix_runs_started", "started_at"),)


class Profile(Base):
    __tablename__ = "dataset_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    row_count: Mapped[int] = mapped_column(Integer)
    column_count: Mapped[int] = mapped_column(Integer)
    duplicate_rate: Mapped[float] = mapped_column(Float)
    health: Mapped[float | None] = mapped_column(Float, nullable=True)
    schema: Mapped[dict] = mapped_column(JSON)
    columns: Mapped[dict] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    path: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    health_components: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("dataset_id", "run_id"),)


class Rule(Base):
    __tablename__ = "quality_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(32))
    column: Mapped[str | None] = mapped_column(String(80), nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class RuleVersion(Base):
    __tablename__ = "quality_rule_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("quality_rules.id"))
    version: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    __table_args__ = (UniqueConstraint("rule_id", "version"),)


class QualityResult(Base):
    __tablename__ = "quality_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("quality_rules.id"))
    rule_version: Mapped[int] = mapped_column(Integer)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    passed: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20), default="evaluated")
    observed: Mapped[float] = mapped_column(Float)
    expected: Mapped[str] = mapped_column(Text)
    failed_count: Mapped[int] = mapped_column(Integer)
    sample: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    __table_args__ = (UniqueConstraint("rule_id", "run_id"),)


class LineageEdge(Base):
    __tablename__ = "lineage_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    target_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    transformation: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(64), default="1")
    __table_args__ = (UniqueConstraint("source_id", "target_id"),)


class Anomaly(Base):
    __tablename__ = "anomalies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    column: Mapped[str | None] = mapped_column(String(80), nullable=True)
    severity: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    observed: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    __table_args__ = (UniqueConstraint("dataset_id", "run_id", "kind", "column"),)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    root_dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    root_score: Mapped[float] = mapped_column(Float, default=0)
    owner: Mapped[str] = mapped_column(String(120), default="Unassigned")
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)
    resolved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    healthy_runs: Mapped[int] = mapped_column(Integer, default=0)


class IncidentAnomaly(Base):
    __tablename__ = "incident_anomalies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    anomaly_id: Mapped[int] = mapped_column(ForeignKey("anomalies.id"), unique=True)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    anomaly_id: Mapped[int] = mapped_column(ForeignKey("anomalies.id"), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    facts: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class IncidentEvent(Base):
    __tablename__ = "incident_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class Candidate(Base):
    __tablename__ = "root_cause_candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    score: Mapped[float] = mapped_column(Float)
    contributions: Mapped[dict] = mapped_column(JSON)
    evidence_ids: Mapped[list] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("incident_id", "dataset_id"),)


class Investigation(Base):
    __tablename__ = "investigations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    report: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class ChangeEvent(Base):
    __tablename__ = "change_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    component: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(64), default="1")
    actor: Mapped[str] = mapped_column(String(120), default="system")
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class ProductEvent(Base):
    __tablename__ = "product_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class WorkspaceState(Base):
    __tablename__ = "workspace_state"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Lease(Base):
    __tablename__ = "job_leases"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner: Mapped[str] = mapped_column(String(40), default="")
    expires_at: Mapped[str] = mapped_column(String(40), default="")
