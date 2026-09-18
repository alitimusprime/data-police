import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  ArrowUpRight,
  Check,
  ChevronDown,
  Database,
  FileSpreadsheet,
  FlaskConical,
  GitBranch,
  Globe,
  Info,
  Play,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
} from 'lucide-react';
import { api, dateTime, formatNumber, human } from './api';
import { Badge, Button, Heading, Metric, Modal, Panel, State } from './components';
import { RunButton, useWorkspace } from './App';
import type { Change, Dataset, Rule, Run, Settings, Simulation } from './types';

export function PipelinesView() {
  const { go } = useWorkspace(),
    [selected, setSelected] = useState<string | null>(null);
  const query = useQuery({ queryKey: ['runs'], queryFn: () => api<Run[]>('/runs'), refetchInterval: 8000 });
  if (!query.data) return <State error={query.error} />;
  const runs = query.data,
    latest = runs[0],
    successes = runs.filter((r) => r.status === 'succeeded'),
    completed = runs.filter((r) => ['succeeded', 'failed'].includes(r.status));
  return (
    <>
      <Heading
        eyebrow="ORCHESTRATION"
        title="Pipelines"
        description="Follow each run from extraction to the last quality check."
      >
        <RunButton />
      </Heading>
      <div className="pipeline-definition">
        <span className="pipeline-large-icon">
          <GitBranch size={26} />
        </span>
        <div>
          <h2>Retail reliability pipeline</h2>
          <p>
            SQL + REST + CSV <span>→</span> Raw <span>→</span> Staging <span>→</span> Curated <span>→</span>{' '}
            Analytics
          </p>
        </div>
        <Button onClick={() => go('lineage')}>
          View asset graph <ArrowUpRight size={15} />
        </Button>
      </div>
      <div className="metrics-grid">
        <Metric
          label="Latest run"
          value={<span className="status-value">{latest ? human(latest.status) : 'No runs'}</span>}
          caption={latest ? dateTime(latest.started_at) : 'Awaiting first run'}
        />
        <Metric
          label="Successful executions"
          value={successes.length}
          caption={`${completed.length} completed runs in this view`}
        />
        <Metric
          label="Latest duration"
          value={
            <>
              {latest ? formatNumber(latest.duration_ms / 1000) : 'N/A'}
              <small>s</small>
            </>
          }
          caption="End-to-end materialization time"
        />
        <Metric
          label="Source records"
          value={formatNumber(latest?.records)}
          caption="Latest run, counted at source boundaries"
        />
      </div>
      <Panel title="Run history" meta={<span className="meta">Last 100 runs · click to expand</span>}>
        <div className="run-history">
          {runs.map((run) => (
            <div className="run-entry" key={run.id}>
              <button
                className="run-row"
                onClick={() => setSelected(selected === run.id ? null : run.id)}
                aria-expanded={selected === run.id}
              >
                <GitBranch size={18} />
                <div>
                  <strong className="mono">{run.id.slice(0, 8)}</strong>
                  <small>{dateTime(run.started_at)}</small>
                </div>
                <span className="trigger-label">{human(run.trigger)}</span>
                <span>{formatNumber(run.records)} rows</span>
                <span>{formatNumber(run.duration_ms / 1000)}s</span>
                <Badge status={run.status} />
                <ChevronDown size={16} />
              </button>
              {selected === run.id && (
                <div className="run-detail">
                  {run.error && <div className="inline-error">{run.error}</div>}
                  {run.scenario && (
                    <p className="microcopy">Synthetic source scenario: {human(run.scenario)}</p>
                  )}
                  <div className="stage-grid">
                    {run.stages.map((stage) => (
                      <button
                        key={stage.asset}
                        onClick={() => go('datasets/' + stage.asset)}
                        className={stage.status}
                      >
                        <span>{stage.status === 'succeeded' ? <Check size={14} /> : <Info size={14} />}</span>
                        <strong>{stage.asset}</strong>
                        <small>
                          {stage.rows == null
                            ? stage.error
                            : formatNumber(stage.rows) + ' rows · ' + stage.duration_ms + 'ms'}
                        </small>
                      </button>
                    ))}
                  </div>
                  {!run.stages.length && (
                    <p className="small-empty">
                      {run.status === 'paused'
                        ? 'Ingestion is deliberately paused. Independent freshness monitoring remains active.'
                        : 'This run is awaiting execution.'}
                    </p>
                  )}
                </div>
              )}
            </div>
          ))}
          {!runs.length && (
            <State empty title="No pipeline history">
              Run ingestion to collect real execution receipts.
            </State>
          )}
        </div>
      </Panel>
    </>
  );
}

const defaults: Record<string, Record<string, unknown>> = {
  not_null: {},
  unique: {},
  accepted: { values: ['paid', 'processing', 'cancelled'] },
  range: { min: 0 },
  pattern: { pattern: '^[^@]+@[^@]+\\.[^@]+$' },
  reference: { dataset: 'dim_customers', column: 'customer_id' },
  schema: { columns: ['order_id', 'amount'] },
  volume: { min: 1 },
};
export function RulesView() {
  const { act, busy } = useWorkspace(),
    [open, setOpen] = useState(false),
    [search, setSearch] = useState(''),
    [dataset, setDataset] = useState('raw_orders'),
    [name, setName] = useState(''),
    [kind, setKind] = useState('not_null'),
    [column, setColumn] = useState('customer_id'),
    [params, setParams] = useState('{}'),
    [severity, setSeverity] = useState('warning'),
    [error, setError] = useState('');
  const query = useQuery({ queryKey: ['rules'], queryFn: () => api<Rule[]>('/rules') });
  const datasets = useQuery({ queryKey: ['datasets'], queryFn: () => api<Dataset[]>('/datasets') });
  if (!query.data) return <State error={query.error} />;
  const rows = query.data.filter((r) =>
    (r.name + ' ' + r.dataset_id).toLowerCase().includes(search.toLowerCase()),
  );
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    let parsed;
    try {
      parsed = JSON.parse(params);
    } catch {
      setError('Parameters must be valid JSON.');
      return;
    }
    if (
      await act('Quality rule created', () =>
        api('/rules', 'POST', {
          dataset_id: dataset,
          name,
          kind,
          column: ['schema', 'volume'].includes(kind) ? null : column,
          params: parsed,
          severity,
        }),
      )
    ) {
      setOpen(false);
      setName('');
    }
  }
  return (
    <>
      <Heading
        eyebrow="DATA CONTRACTS"
        title="Quality rules"
        description="Define what good data looks like. Keep every change traceable."
      >
        <Button primary onClick={() => setOpen(true)}>
          <Plus size={16} />
          Create rule
        </Button>
      </Heading>
      <div className="rule-summary">
        <span>
          <ShieldCheck size={17} />
          <strong>{query.data.filter((r) => r.enabled).length}</strong> enabled rules
        </span>
        <span>{query.data.filter((r) => r.severity === 'critical').length} critical expectations</span>
        <span>Versioned definitions · Evaluated on materialization</span>
      </div>
      <Panel>
        <div className="table-toolbar">
          <label className="search-field">
            <Search size={16} />
            <input
              placeholder="Search rules or datasets"
              aria-label="Search rules"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Expectation</th>
                <th>Dataset</th>
                <th>Type</th>
                <th>Severity</th>
                <th>Version</th>
                <th>Enabled</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((rule) => (
                <tr key={rule.id}>
                  <td>
                    <strong>{rule.name}</strong>
                    <small className="block muted">{rule.column || 'Dataset-level rule'}</small>
                  </td>
                  <td className="mono">{rule.dataset_id}</td>
                  <td>{human(rule.kind)}</td>
                  <td>
                    <Badge status={rule.severity} />
                  </td>
                  <td>v{rule.version}</td>
                  <td>
                    <button
                      className={'switch ' + (rule.enabled ? 'on' : '')}
                      role="switch"
                      aria-checked={rule.enabled}
                      aria-label={'Enable ' + rule.name}
                      disabled={!!busy}
                      onClick={() =>
                        act('Rule configuration updated', () =>
                          api('/rules/' + rule.id, 'PATCH', { enabled: !rule.enabled }),
                        )
                      }
                    >
                      <span />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="panel-footnote">
          Rules are structured and validated. Arbitrary Python or SQL execution is not exposed.
        </p>
      </Panel>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Create a quality rule"
        description="The new expectation will be evaluated on the next materialization."
      >
        <form onSubmit={submit}>
          <label>
            Rule name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Customer ID must be present"
              minLength={3}
              maxLength={160}
              required
            />
          </label>
          <div className="form-grid">
            <label>
              Dataset
              <select value={dataset} onChange={(e) => setDataset(e.target.value)}>
                {datasets.data?.map((d) => (
                  <option key={d.id}>{d.id}</option>
                ))}
              </select>
            </label>
            <label>
              Type
              <select
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value);
                  setParams(JSON.stringify(defaults[e.target.value], null, 2));
                }}
              >
                {Object.keys(defaults).map((k) => (
                  <option value={k} key={k}>
                    {human(k)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {!['schema', 'volume'].includes(kind) && (
            <label>
              Column
              <input value={column} onChange={(e) => setColumn(e.target.value)} required maxLength={80} />
            </label>
          )}
          <label>
            Parameters <span className="muted">(JSON configuration)</span>
            <textarea className="mono" rows={4} value={params} onChange={(e) => setParams(e.target.value)} />
          </label>
          <label>
            Severity
            <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option value="warning">Warning</option>
              <option value="critical">Critical</option>
            </select>
          </label>
          {error && <div className="inline-error">{error}</div>}
          <Button primary disabled={!!busy} type="submit">
            Create rule
          </Button>
        </form>
      </Modal>
    </>
  );
}

export function SourcesView() {
  const { act, busy, go } = useWorkspace(),
    [checks, setChecks] = useState<Record<string, { ok: boolean; at: string }>>({});
  const config = useQuery({ queryKey: ['settings'], queryFn: () => api<Settings>('/settings') });
  const sources = [
    {
      id: 'database',
      name: 'Retail database',
      type: config.data?.source_types[0] || 'SQL database',
      icon: Database,
      description:
        'Native relational source tables with bounded keyset pagination and immutable batch identifiers.',
      assets: 'Orders, order items, customers, countries, products',
    },
    {
      id: 'api',
      name: 'Payments & fulfillment',
      type: 'REST API',
      icon: Globe,
      description:
        'Paginated HTTP extraction with request timeouts, bounded retries and response validation.',
      assets: 'Payments and shipments',
    },
    {
      id: 'csv',
      name: 'Supplier inventory',
      type: 'CSV feed',
      icon: FileSpreadsheet,
      description:
        'Inventory files validated at the ingestion boundary and preserved in checksummed batches.',
      assets: 'Inventory snapshots',
    },
  ];
  return (
    <>
      <Heading
        eyebrow="SOURCE CONNECTIONS"
        title="Connected sources"
        description="Three real extraction boundaries. One reliability workspace."
      >
        <RunButton />
      </Heading>
      <div className="source-cards">
        {sources.map(({ id, name, type, icon: Icon, description, assets }) => (
          <Panel key={id}>
            <div className="source-card">
              <span className="source-icon">
                <Icon size={26} />
              </span>
              <span className="type-badge">{type}</span>
              <h2>{name}</h2>
              <p>{description}</p>
              <dl>
                <dt>Data assets</dt>
                <dd>{assets}</dd>
              </dl>
              <div className="source-check">
                {checks[id] ? (
                  <>
                    <Badge status={checks[id].ok ? 'passed' : 'failed'} />
                    <small>Checked {dateTime(checks[id].at)}</small>
                  </>
                ) : (
                  <span className="muted">Connection not checked in this session</span>
                )}
              </div>
              <Button
                disabled={!!busy}
                onClick={() =>
                  act('Connection check completed', async () => {
                    const result = await api<{ ok: boolean }>('/sources/' + id + '/test', 'POST');
                    setChecks((c) => ({ ...c, [id]: { ok: result.ok, at: new Date().toISOString() } }));
                  })
                }
              >
                Test connection <ArrowUpRight size={15} />
              </Button>
            </div>
          </Panel>
        ))}
      </div>
      <div className="info-banner">
        <Info size={19} />
        <div>
          <strong>Connections are administrator-configured.</strong>
          <p>
            Source endpoints and credentials are configured through your environment, never entered into a
            publicly writable URL field. The bundled sources contain synthetic Northstar Retail data.
          </p>
        </div>
        <Button onClick={() => go('settings')}>Environment details</Button>
      </div>
    </>
  );
}

export function SimulatorView() {
  const { act, busy, go } = useWorkspace(),
    [confirm, setConfirm] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ['simulator'],
    queryFn: () => api<Simulation>('/simulator'),
    refetchInterval: 10000,
  });
  if (!query.data) return <State error={query.error} />;
  const { scenarios, active, enabled, freshness_seconds } = query.data;
  const selected = scenarios.find((s) => s.id === confirm);
  async function inject() {
    if (!selected) return;
    if (
      await act('Source fault activated and pipeline queued', async () => {
        await api('/simulator', 'POST', { scenario: selected.id });
        await api('/runs', 'POST');
      })
    )
      setConfirm(null);
  }
  return (
    <>
      <Heading
        eyebrow="CONTROLLED FAILURE TESTING"
        title="Failure lab"
        description="Change the source. Watch the system find the problem."
      >
        <Button
          disabled={!!busy || !active.scenario || !enabled}
          onClick={() =>
            act('Healthy source behavior restored. Run twice to verify recovery.', () =>
              api('/simulator', 'POST', { scenario: null }),
            )
          }
        >
          <RotateCcw size={15} />
          Restore healthy source
        </Button>
        <RunButton />
      </Heading>
      <div className={'lab-status ' + (active.scenario ? 'fault-active' : '')}>
        <span className="lab-icon">
          <FlaskConical size={24} />
        </span>
        <div>
          <strong>
            {active.scenario
              ? 'Active fault: ' + scenarios.find((s) => s.id === active.scenario)?.name
              : 'Sources are in healthy mode'}
          </strong>
          <p>
            {active.scenario
              ? 'The fault remains active until you restore the source. Incidents are detected from actual data changes.'
              : 'Select a scenario to inject a controlled fault into synthetic data. This does not connect to real customer systems.'}
          </p>
        </div>
        {active.scenario && (
          <Button onClick={() => go('incidents')}>
            View incidents <ArrowUpRight size={15} />
          </Button>
        )}
      </div>
      {!enabled && <div className="inline-error">The simulator is disabled for this environment.</div>}
      <div className="scenario-grid">
        {scenarios.map((scenario, index) => (
          <button
            className={'scenario-card ' + (active.scenario === scenario.id ? 'active' : '')}
            key={scenario.id}
            onClick={() => setConfirm(scenario.id)}
            disabled={!enabled || !!busy}
          >
            <div>
              <span className="scenario-number">{String(index + 1).padStart(2, '0')}</span>
              <span className="scenario-category">{scenario.category}</span>
              {active.scenario === scenario.id && <span className="active-fault-label">ACTIVE</span>}
            </div>
            <h2>{scenario.name}</h2>
            <p>
              {scenario.id === 'stale'
                ? `Pause real materializations while independent freshness monitoring continues. Current threshold: ${freshness_seconds} seconds.`
                : scenario.description}
            </p>
            <footer>
              <span className="mono">{scenario.target}</span>
              <span>
                Inject fault <ArrowUpRight size={15} />
              </span>
            </footer>
          </button>
        ))}
      </div>
      <p className="panel-footnote">
        Recovery is evidence-driven. Restoring a source does not clear incidents; two healthy materializations
        do.
      </p>
      <Modal
        open={!!selected}
        onClose={() => setConfirm(null)}
        title={selected?.name || 'Inject fault'}
        description="This changes the demo source or transformation behavior and runs the actual pipeline. Any existing demo scenario will be replaced."
      >
        <p>{selected?.description}</p>
        <div className="modal-actions">
          <Button onClick={() => setConfirm(null)}>Cancel</Button>
          <Button primary disabled={!!busy} onClick={inject}>
            <Play size={15} />
            Inject & run
          </Button>
        </div>
      </Modal>
    </>
  );
}

export function ActivityView() {
  const query = useQuery({
    queryKey: ['changes'],
    queryFn: () => api<Change[]>('/changes'),
    refetchInterval: 10000,
  });
  if (!query.data) return <State error={query.error} />;
  return (
    <>
      <Heading
        eyebrow="AUDIT TRAIL"
        title="Activity log"
        description="Source changes, ownership decisions, and quality-rule versions."
      />
      <Panel title="Workspace changes">
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Change</th>
                <th>Component</th>
                <th>Actor</th>
                <th>Version</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((c) => (
                <tr key={c.id}>
                  <td>
                    <strong>{c.description}</strong>
                    <small className="block muted">{human(c.kind)}</small>
                  </td>
                  <td className="mono">{c.component}</td>
                  <td>{c.actor}</td>
                  <td>{c.version}</td>
                  <td>{dateTime(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!query.data.length && (
            <State empty title="No changes recorded yet">
              Workspace configuration changes will appear here.
            </State>
          )}
        </div>
      </Panel>
    </>
  );
}

export function SettingsView() {
  const query = useQuery({ queryKey: ['settings'], queryFn: () => api<Settings>('/settings') });
  if (!query.data) return <State error={query.error} />;
  const s = query.data;
  return (
    <>
      <Heading
        eyebrow="ADMINISTRATION"
        title="Workspace settings"
        description="The operating configuration behind your reliability workspace."
      />
      <div className="two-column">
        <Panel title="Workspace">
          <dl className="detail-list">
            <div>
              <dt>Name</dt>
              <dd>{s.workspace}</dd>
            </div>
            <div>
              <dt>Environment</dt>
              <dd>
                <span className="env-pill">{s.environment}</span>
              </dd>
            </div>
            <div>
              <dt>Application version</dt>
              <dd>{s.version}</dd>
            </div>
            <div>
              <dt>Data provenance</dt>
              <dd>Synthetic retail data</dd>
            </div>
            <div>
              <dt>Access</dt>
              <dd>Single-workspace administrator</dd>
            </div>
          </dl>
        </Panel>
        <Panel title="Runtime">
          <dl className="detail-list">
            <div>
              <dt>System database</dt>
              <dd>{s.database}</dd>
            </div>
            <div>
              <dt>Job execution</dt>
              <dd>{s.executor === 'celery' ? 'Celery + Redis' : 'Local background worker'}</dd>
            </div>
            <div>
              <dt>Queued jobs</dt>
              <dd>{s.queued_jobs}</dd>
            </div>
            <div>
              <dt>Raw / analytical storage</dt>
              <dd>Parquet + DuckDB</dd>
            </div>
            <div>
              <dt>Live updates</dt>
              <dd>SSE with durable event replay</dd>
            </div>
          </dl>
        </Panel>
        <Panel title="Monitoring policy">
          <dl className="detail-list">
            <div>
              <dt>Freshness threshold</dt>
              <dd>{s.freshness_seconds} seconds</dd>
            </div>
            <div>
              <dt>Local schedule interval</dt>
              <dd>{s.auto_run_seconds > 0 ? s.auto_run_seconds + ' seconds' : 'Disabled'}</dd>
            </div>
            <div>
              <dt>Statistical warmup</dt>
              <dd>{s.baseline_minimum} healthy batches</dd>
            </div>
            <div>
              <dt>Automatic resolution</dt>
              <dd>2 consecutive healthy runs</dd>
            </div>
            <div>
              <dt>Failure simulator</dt>
              <dd>{s.simulator_enabled ? 'Enabled' : 'Disabled'}</dd>
            </div>
          </dl>
        </Panel>
        <Panel title="Investigation & privacy">
          <div className="settings-prose">
            <ShieldCheck size={26} />
            <h3>{s.ai_configured ? 'AI provider configured' : 'Evidence-first mode'}</h3>
            <p>
              The deterministic incident engine works without AI. No evidence is sent externally unless an
              administrator explicitly requests AI-assisted suggestions.
            </p>
            <p>
              Raw customer rows are excluded from the investigation packet. Scores are evidence rankings, not
              calibrated probabilities.
            </p>
            <span className="provider-label">
              {s.ai_configured ? 'Optional external provider' : 'No external provider configured'}
            </span>
          </div>
        </Panel>
      </div>
      <div className="info-banner">
        <SlidersHorizontal size={20} />
        <p>
          Runtime settings and credentials are managed through your private environment configuration. Restart
          the affected services after changing them. Secrets are never returned by this API.
        </p>
      </div>
    </>
  );
}
