import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  CheckCheck,
  Database,
  Download,
  Filter,
  GitBranch,
  Layers3,
  Search,
  ShieldCheck,
  SlidersHorizontal,
} from 'lucide-react';
import { api, clock, dateTime, formatNumber, human } from './api';
import {
  Badge,
  Button,
  DatasetTable,
  Heading,
  Health,
  IncidentRows,
  LineChart,
  Metric,
  Modal,
  Panel,
  State,
} from './components';
import { RunButton, useWorkspace } from './App';
import type { Dataset, DatasetDetail, Overview } from './types';

export function OverviewView() {
  const { go } = useWorkspace();
  const query = useQuery({
    queryKey: ['overview'],
    queryFn: () => api<Overview>('/overview'),
    refetchInterval: 15000,
  });
  if (!query.data) return <State error={query.error} />;
  const { stats, incidents, datasets, trend, runs, anomalies } = query.data;
  const degraded = datasets.filter((d) => d.status !== 'healthy').slice(0, 6);
  const hasData = runs.some((r) => r.status === 'succeeded');
  return (
    <>
      <Heading
        eyebrow="YOUR DATA ESTATE, AT A GLANCE"
        title="Reliability overview"
        description="The signals that matter. The context to act."
      >
        <Button onClick={() => go('simulator')}>
          <SlidersHorizontal size={15} />
          Failure lab
        </Button>
        <RunButton />
      </Heading>
      {!hasData && (
        <div className="onboarding-banner">
          <div>
            <h3>Your workspace is ready for its first run.</h3>
            <p>
              Start the demo provider, then run ingestion. Eight healthy batches establish the statistical
              baseline.
            </p>
          </div>
          <RunButton />
        </div>
      )}
      <div className="metrics-grid">
        <Metric
          label="Estate health"
          value={
            <>
              {hasData ? formatNumber(stats.health) : 'N/A'}
              <small>{hasData ? '/ 100' : ''}</small>
            </>
          }
          caption={
            <>
              <span className={'dot ' + (stats.health >= 90 ? 'green' : 'amber')} />
              {hasData
                ? stats.degraded
                  ? 'Attention required'
                  : 'Operating within expectations'
                : 'Awaiting first measurement'}
            </>
          }
          icon={<ShieldCheck size={17} />}
        />
        <Metric
          label="Monitored datasets"
          value={stats.datasets}
          caption={
            <>
              {stats.healthy} healthy <span className="sep">/</span> {stats.degraded} degraded
            </>
          }
          icon={<Database size={17} />}
        />
        <Metric
          label="Active incidents"
          value={stats.active_incidents}
          caption={stats.active_incidents ? 'Review the incident inbox' : 'No open investigations'}
          icon={<Activity size={17} />}
        />
        <Metric
          label="Enabled quality rules"
          value={stats.rules}
          caption="Versioned, evaluated on each run"
          icon={<CheckCheck size={17} />}
        />
      </div>
      <div className="overview-middle">
        <Panel
          title="Reliability over time"
          meta={<span className="meta">Last {trend.length} materializations</span>}
        >
          <div className="chart-summary">
            <span className="chart-legend">
              <i />
              Estate health
            </span>
            <span className="meta">Measured, not estimated</span>
          </div>
          <LineChart data={trend} series="health" max={100} height={255} />
        </Panel>
        <Panel
          title="Incident inbox"
          meta={
            <button className="text-button" onClick={() => go('incidents')}>
              View all <ArrowUpRight size={14} />
            </button>
          }
          className="inbox-panel"
        >
          <IncidentRows incidents={incidents.slice(0, 3)} onOpen={(id) => go('incidents/' + id)} />
          <div className="inbox-note">
            <GitBranch size={16} />
            <span>Connected anomalies become one investigation.</span>
          </div>
        </Panel>
      </div>
      <Panel
        title={degraded.length ? 'Datasets needing attention' : 'Data estate'}
        meta={
          <button className="text-button" onClick={() => go('datasets')}>
            Explore datasets <ArrowUpRight size={14} />
          </button>
        }
      >
        <DatasetTable
          datasets={degraded.length ? degraded : datasets.slice(0, 5)}
          onOpen={(id) => go('datasets/' + id)}
        />
      </Panel>
      <div className="two-column bottom-panels">
        <Panel title="Recent signals" meta={<span className="meta">Detection stream</span>}>
          {anomalies.length ? (
            <div className="signal-list">
              {anomalies.slice(0, 4).map((a) => (
                <button key={a.id} onClick={() => go('datasets/' + a.dataset_id)}>
                  <span className={'signal-dot ' + a.severity} />
                  <div>
                    <strong>{a.title}</strong>
                    <small>{a.dataset_id}</small>
                  </div>
                  <time>{clock(a.created_at)}</time>
                </button>
              ))}
            </div>
          ) : (
            <div className="quiet-success">
              <CheckCheck size={22} />
              <div>
                <strong>No anomalies detected</strong>
                <p>Rules and monitors are watching incoming batches.</p>
              </div>
            </div>
          )}
        </Panel>
        <Panel
          title="Pipeline activity"
          meta={
            <button className="text-button" onClick={() => go('pipelines')}>
              View runs <ArrowUpRight size={14} />
            </button>
          }
        >
          <div className="compact-runs">
            {runs.slice(0, 4).map((r) => (
              <button key={r.id} onClick={() => go('pipelines')}>
                <span className="run-icon">
                  <GitBranch size={17} />
                </span>
                <div>
                  <strong>Retail reliability pipeline</strong>
                  <small>
                    {r.id.slice(0, 8)} · {dateTime(r.started_at)}
                  </small>
                </div>
                <Badge status={r.status} />
              </button>
            ))}
            {!runs.length && <div className="small-empty">No pipeline runs yet.</div>}
          </div>
        </Panel>
      </div>
    </>
  );
}

export function DatasetsView({ search, setSearch }: { search: string; setSearch: (s: string) => void }) {
  const { go } = useWorkspace(),
    [layer, setLayer] = useState('all'),
    [status, setStatus] = useState('all');
  const query = useQuery({
    queryKey: ['datasets'],
    queryFn: () => api<Dataset[]>('/datasets'),
    refetchInterval: 15000,
  });
  if (!query.data) return <State error={query.error} />;
  const rows = query.data.filter(
    (d) =>
      (layer === 'all' || d.layer === layer) &&
      (status === 'all' || d.status === status) &&
      (d.name + ' ' + d.owner + ' ' + d.source).toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <>
      <Heading
        eyebrow="CATALOG"
        title="Datasets"
        description="Every asset, its health, and the people responsible."
      >
        <RunButton />
      </Heading>
      <div className="catalog-summary">
        {['raw', 'reference', 'staging', 'curated', 'analytics'].map((l) => (
          <button
            key={l}
            className={layer === l ? 'selected' : ''}
            onClick={() => setLayer(layer === l ? 'all' : l)}
          >
            <Layers3 size={18} />
            <strong>{query.data!.filter((d) => d.layer === l).length}</strong>
            <span>{l}</span>
          </button>
        ))}
      </div>
      <Panel>
        <div className="table-toolbar">
          <label className="search-field">
            <Search size={17} />
            <input
              placeholder="Search datasets or owners"
              aria-label="Filter datasets"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <label className="filter-select">
            <Filter size={15} />
            <select aria-label="Filter status" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="all">All statuses</option>
              {['healthy', 'warning', 'critical', 'stale', 'unknown'].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <span className="meta">{rows.length} datasets</span>
        </div>
        <DatasetTable datasets={rows} onOpen={(id) => go('datasets/' + id)} />
      </Panel>
    </>
  );
}

export function DatasetView({ id }: { id: string }) {
  const { go, act, busy } = useWorkspace(),
    [tab, setTab] = useState('Overview'),
    [editing, setEditing] = useState(false),
    [owner, setOwner] = useState('');
  const query = useQuery({
    queryKey: ['dataset', id],
    queryFn: () => api<DatasetDetail>('/datasets/' + id),
    refetchInterval: 15000,
  });
  if (!query.data) return <State error={query.error} />;
  const { dataset, latest, history, rules, results, upstream, downstream, anomalies, baseline_runs } =
    query.data;
  return (
    <>
      <button className="back-link" onClick={() => go('datasets')}>
        Datasets <span>/</span> {dataset.layer}
      </button>
      <Heading title={id} description={dataset.description}>
        <Badge status={dataset.status} />
        <Button onClick={() => go('lineage/' + id)}>
          <GitBranch size={15} />
          View lineage
        </Button>
      </Heading>
      <div className="asset-meta">
        <span>
          <Database size={15} />
          {dataset.source}
        </span>
        <span>
          Owner{' '}
          <button
            className="text-button"
            onClick={() => {
              setOwner(dataset.owner);
              setEditing(true);
            }}
          >
            {dataset.owner}
          </button>
        </span>
        <span>Last materialized {dateTime(dataset.last_materialized)}</span>
        {dataset.critical && <span className="critical-asset">Business critical</span>}
      </div>
      <div className="tabs" role="tablist" aria-label="Dataset sections">
        {['Overview', 'Schema & profile', 'Quality', 'Anomalies', 'Dependencies'].map((t) => (
          <button
            role="tab"
            aria-selected={tab === t}
            key={t}
            onClick={() => setTab(t)}
            className={tab === t ? 'active' : ''}
          >
            {t}
          </button>
        ))}
      </div>
      {!latest ? (
        <State empty title="This dataset has not been materialized">
          <p>Run the pipeline to collect its schema, profile and quality results.</p>
          <RunButton />
        </State>
      ) : (
        <>
          {tab === 'Overview' && (
            <>
              <div className="metrics-grid">
                <Metric
                  label="Data health"
                  value={
                    <>
                      {dataset.health}
                      <small>/ 100</small>
                    </>
                  }
                  caption={<Health value={dataset.health} />}
                />
                <Metric
                  label="Rows in latest batch"
                  value={formatNumber(latest.row_count)}
                  caption={`${latest.column_count} columns`}
                />
                <Metric
                  label="Excess duplicate rows"
                  value={(latest.duplicate_rate * 100).toFixed(1) + '%'}
                  caption="Exact duplicate rows in this batch"
                />
                <Metric
                  label="Healthy baseline runs"
                  value={baseline_runs}
                  caption={
                    baseline_runs >= 8
                      ? 'Statistical monitors are active'
                      : `${8 - baseline_runs} more needed for statistical monitors`
                  }
                />
              </div>
              <div className="two-column">
                <Panel title="Health history">
                  <LineChart data={history} series="health" max={100} />
                </Panel>
                <Panel title="Record volume">
                  <LineChart data={history} series="rows" label="Rows" color="#4c7895" />
                </Panel>
              </div>
              <div className="two-column bottom-panels">
                <Panel
                  title="Health components"
                  meta={<span className="meta">Critical failures cap the overall score</span>}
                >
                  <div className="component-scores">
                    {Object.entries(latest.health_components).map(([key, value]) => (
                      <div key={key}>
                        <span>{human(key)}</span>
                        <Health value={value} />
                      </div>
                    ))}
                  </div>
                </Panel>
                <Panel title="Materialization receipt">
                  <dl className="detail-list">
                    <div>
                      <dt>Batch ID</dt>
                      <dd className="mono wrap">{dataset.latest_run_id}</dd>
                    </div>
                    <div>
                      <dt>Storage format</dt>
                      <dd>Parquet · Zstandard</dd>
                    </div>
                    <div>
                      <dt>Size</dt>
                      <dd>{formatNumber(latest.size_bytes / 1024)} KB</dd>
                    </div>
                    <div>
                      <dt>Integrity</dt>
                      <dd className="mono wrap">
                        SHA-256
                        <br />
                        {latest.checksum}
                      </dd>
                    </div>
                  </dl>
                </Panel>
              </div>
            </>
          )}
          {tab === 'Schema & profile' && (
            <Panel
              title="Observed schema"
              meta={<span className="meta">All rows profiled; numeric drift uses bounded samples</span>}
            >
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Column</th>
                      <th>Type</th>
                      <th>Null rate</th>
                      <th>Distinct</th>
                      <th>Min</th>
                      <th>Mean</th>
                      <th>P95</th>
                      <th>Max</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(latest.columns).map(([name, c]) => (
                      <tr key={name}>
                        <td className="mono">{name}</td>
                        <td>
                          <span className="type-badge">{c.type}</span>
                        </td>
                        <td>{(c.null_rate * 100).toFixed(1)}%</td>
                        <td>{formatNumber(c.distinct)}</td>
                        <td>{c.min == null ? 'N/A' : formatNumber(c.min)}</td>
                        <td>{c.mean == null ? 'N/A' : formatNumber(c.mean)}</td>
                        <td>{c.p95 == null ? 'N/A' : formatNumber(c.p95)}</td>
                        <td>{c.max == null ? 'N/A' : formatNumber(c.max)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="distribution-grid">
                {Object.entries(latest.columns)
                  .filter(([, c]) => c.distribution)
                  .map(([name, c]) => (
                    <div className="distribution" key={name}>
                      <h3>{name}</h3>
                      {Object.entries(c.distribution!)
                        .sort((a, b) => b[1] - a[1])
                        .slice(0, 8)
                        .map(([value, count]) => (
                          <div key={value}>
                            <span title={value}>{value}</span>
                            <div>
                              <i style={{ width: `${(count / latest.row_count) * 100}%` }} />
                            </div>
                            <small>{((count / latest.row_count) * 100).toFixed(1)}%</small>
                          </div>
                        ))}
                    </div>
                  ))}
              </div>
            </Panel>
          )}
          {tab === 'Quality' && (
            <Panel
              title="Quality rules"
              meta={
                <Button onClick={() => go('rules')}>
                  Manage rules <ArrowUpRight size={14} />
                </Button>
              }
            >
              <div className="rule-cards">
                {rules.map((r) => {
                  const result = results.find((x) => x.rule_id === r.id);
                  return (
                    <div className="rule-card" key={r.id}>
                      <div>
                        <h3>{r.name}</h3>
                        <p>
                          {r.kind} · {r.column || 'dataset'} · v{r.version}
                        </p>
                      </div>
                      <Badge
                        status={
                          !r.enabled ? 'disabled' : !result ? 'unknown' : result.passed ? 'passed' : 'failed'
                        }
                      />
                      <div className="rule-result">
                        {result
                          ? `${result.failed_count} failed rows · ${result.expected}`
                          : 'Not evaluated yet'}
                      </div>
                    </div>
                  );
                })}
                {!rules.length && (
                  <State empty title="No configured rules">
                    Statistical monitoring still runs for this dataset.
                  </State>
                )}
              </div>
            </Panel>
          )}
          {tab === 'Anomalies' && (
            <Panel title="Recent anomalies">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Signal</th>
                      <th>Severity</th>
                      <th>Observed</th>
                      <th>Expected</th>
                      <th>Detected</th>
                    </tr>
                  </thead>
                  <tbody>
                    {anomalies.map((a) => (
                      <tr key={a.id}>
                        <td>
                          <strong>{a.title}</strong>
                          <small className="block muted">{a.method}</small>
                        </td>
                        <td>
                          <Badge status={a.severity} />
                        </td>
                        <td>{formatNumber(a.observed)}</td>
                        <td>{a.expected}</td>
                        <td>{dateTime(a.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!anomalies.length && (
                  <State empty title="No anomaly history">
                    This dataset has no detected failures.
                  </State>
                )}
              </div>
            </Panel>
          )}
          {tab === 'Dependencies' && (
            <div className="two-column">
              {[
                ['Upstream assets', upstream],
                ['Downstream assets', downstream],
              ].map(([title, assets]) => (
                <Panel key={String(title)} title={String(title)}>
                  <div className="dependency-list">
                    {Object.entries(assets).map(([name, distance]) => (
                      <button key={name} onClick={() => go('datasets/' + name)}>
                        <Database size={16} />
                        <span>{name}</span>
                        <small>
                          {distance} {distance === 1 ? 'hop' : 'hops'}
                        </small>
                        <ArrowRight size={14} />
                      </button>
                    ))}
                    {!Object.keys(assets).length && (
                      <div className="small-empty">No registered dependencies in this direction.</div>
                    )}
                  </div>
                </Panel>
              ))}
            </div>
          )}
        </>
      )}
      <Modal
        open={editing}
        onClose={() => setEditing(false)}
        title="Dataset owner"
        description="Assign a person or team accountable for this dataset."
      >
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (await act('Dataset owner updated', () => api('/datasets/' + id, 'PATCH', { owner })))
              setEditing(false);
          }}
        >
          <label>
            Owner
            <input value={owner} onChange={(e) => setOwner(e.target.value)} required maxLength={120} />
          </label>
          <Button primary type="submit" disabled={!!busy}>
            Save owner
          </Button>
        </form>
      </Modal>
    </>
  );
}
