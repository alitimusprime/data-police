export interface Dataset {
  id: string;
  name: string;
  layer: string;
  source: string;
  owner: string;
  description: string;
  critical: boolean;
  health: number | null;
  status: string;
  last_materialized: string | null;
  latest_run_id: string | null;
}
export interface Run {
  id: string;
  status: string;
  trigger: string;
  started_at: string;
  completed_at: string | null;
  duration_ms: number;
  records: number;
  error: string | null;
  stages: { asset: string; status: string; rows?: number; duration_ms?: number; error?: string }[];
  synthetic: boolean;
  scenario: string | null;
}
export interface Incident {
  id: number;
  title: string;
  status: string;
  severity: string;
  root_dataset_id: string;
  root_score: number;
  owner: string;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  healthy_runs: number;
}
export interface Anomaly {
  id: number;
  dataset_id: string;
  run_id: string;
  kind: string;
  column: string;
  severity: string;
  title: string;
  observed: number | null;
  expected: string;
  method: string;
  details: Record<string, unknown>;
  created_at: string;
}
export interface Rule {
  id: number;
  dataset_id: string;
  name: string;
  kind: string;
  column: string | null;
  params: Record<string, unknown>;
  severity: string;
  enabled: boolean;
  version: number;
}
export interface QualityResult {
  id: number;
  rule_id: number;
  passed: boolean;
  status: string;
  observed: number;
  expected: string;
  failed_count: number;
  created_at: string;
}
export interface ColumnProfile {
  type: string;
  null_count: number;
  null_rate: number;
  distinct: number;
  min?: number;
  max?: number;
  mean?: number;
  median?: number;
  p95?: number;
  distribution?: Record<string, number>;
}
export interface Profile {
  id: number;
  row_count: number;
  column_count: number;
  duplicate_rate: number;
  health: number;
  schema: Record<string, string>;
  columns: Record<string, ColumnProfile>;
  metrics: Record<string, number>;
  size_bytes: number;
  checksum: string;
  created_at: string;
  health_components: Record<string, number>;
}
export interface DatasetDetail {
  dataset: Dataset;
  latest: Profile | null;
  history: {
    at: string;
    rows: number;
    health: number;
    duplicate_rate: number;
    metrics: Record<string, number>;
  }[];
  rules: Rule[];
  results: QualityResult[];
  upstream: Record<string, number>;
  downstream: Record<string, number>;
  anomalies: Anomaly[];
  baseline_runs: number;
}
export interface Evidence {
  id: number;
  title: string;
  facts: {
    dataset: string;
    run_id: string;
    kind: string;
    observed: number | null;
    expected: string;
    method: string;
    details: Record<string, unknown>;
    observed_at: string;
  };
}
export interface Statement {
  text: string;
  evidence_ids: number[];
}
export interface Investigation {
  id: number;
  provider: string;
  created_at: string;
  report: {
    summary: string;
    verified: Statement[];
    inference: Statement[];
    hypotheses: Statement[];
    recommendations: Statement[];
    limitations: string;
  };
}
export interface IncidentDetail {
  incident: Incident;
  impact: { observed: string[]; potential: string[] };
  anomalies: Anomaly[];
  evidence: Evidence[];
  timeline: { id: number; kind: string; message: string; created_at: string }[];
  candidates: {
    dataset_id: string;
    score: number;
    contributions: Record<string, number>;
    evidence_ids: number[];
  }[];
  investigation: Investigation | null;
}
export interface Overview {
  stats: {
    datasets: number;
    healthy: number;
    degraded: number;
    active_incidents: number;
    health: number;
    rules: number;
  };
  datasets: Dataset[];
  incidents: Incident[];
  runs: Run[];
  trend: { run_id: string; health: number; at: string; rows: number }[];
  anomalies: Anomaly[];
  simulator: { scenario: string | null };
  synthetic: boolean;
}
export interface Scenario {
  id: string;
  name: string;
  category: string;
  description: string;
  target: string;
}
export interface Simulation {
  enabled: boolean;
  scenarios: Scenario[];
  active: { scenario: string | null; changed_at?: string };
  freshness_seconds: number;
}
export interface Settings {
  workspace: string;
  environment: string;
  version: string;
  synthetic: boolean;
  database: string;
  executor: string;
  freshness_seconds: number;
  auto_run_seconds: number;
  ai_configured: boolean;
  simulator_enabled: boolean;
  baseline_minimum: number;
  source_types: string[];
  queued_jobs: number;
}
export interface Change {
  id: number;
  component: string;
  kind: string;
  description: string;
  actor: string;
  version: string;
  created_at: string;
}
