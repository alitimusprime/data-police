import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  Download,
  FileSearch,
  GitBranch,
  MessageSquare,
  Search,
  ShieldCheck,
  Sparkles,
  UserRound,
} from 'lucide-react';
import { api, dateTime, formatNumber, human } from './api';
import { Badge, Button, Heading, Metric, Modal, Panel, State } from './components';
import { useWorkspace } from './App';
import type { Incident, IncidentDetail, Settings, Statement } from './types';

export function IncidentsView() {
  const { go } = useWorkspace(),
    [filter, setFilter] = useState('active'),
    [search, setSearch] = useState('');
  const query = useQuery({
    queryKey: ['incidents'],
    queryFn: () => api<Incident[]>('/incidents'),
    refetchInterval: 15000,
  });
  if (!query.data) return <State error={query.error} />;
  const rows = query.data.filter(
    (i) =>
      (filter === 'all' || (filter === 'active' ? i.status !== 'resolved' : i.status === 'resolved')) &&
      (i.title + ' DP-' + (i.id + 1000)).toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <>
      <Heading
        eyebrow="INVESTIGATE & RESOLVE"
        title="Incident inbox"
        description="From disconnected signals to a clear next step."
      >
        <Button onClick={() => go('simulator')}>
          <Activity size={16} />
          Open failure lab
        </Button>
      </Heading>
      <div className="tabs" role="tablist" aria-label="Incident state">
        {['active', 'resolved', 'all'].map((f) => (
          <button
            role="tab"
            aria-selected={filter === f}
            key={f}
            className={filter === f ? 'active' : ''}
            onClick={() => setFilter(f)}
          >
            {human(f)}
            <span>
              {
                query.data!.filter(
                  (i) => f === 'all' || (f === 'active' ? i.status !== 'resolved' : i.status === 'resolved'),
                ).length
              }
            </span>
          </button>
        ))}
      </div>
      <Panel>
        <div className="table-toolbar">
          <label className="search-field">
            <Search size={16} />
            <input
              placeholder="Search incidents"
              aria-label="Search incidents"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <span className="meta">{rows.length} investigations</span>
        </div>
        <div className="table-scroll">
          <table className="incidents-table">
            <thead>
              <tr>
                <th>Incident</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Evidence rank</th>
                <th>Owner</th>
                <th>Last update</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => (
                <tr className="clickable" onClick={() => go('incidents/' + i.id)} key={i.id}>
                  <td>
                    <button
                      className="cell-link"
                      onClick={(e) => {
                        e.stopPropagation();
                        go('incidents/' + i.id);
                      }}
                    >
                      <span>
                        <strong>{i.title}</strong>
                        <small className="block muted">
                          DP-{i.id + 1000} · {i.root_dataset_id}
                        </small>
                      </span>
                    </button>
                  </td>
                  <td>
                    <Badge status={i.severity} />
                  </td>
                  <td>
                    <Badge status={i.status} />
                  </td>
                  <td>
                    <span className="score-pill">
                      {i.root_score.toFixed(0)}
                      <small>/100</small>
                    </span>
                  </td>
                  <td>{i.owner}</td>
                  <td className="muted">{dateTime(i.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && (
            <State
              empty
              title={filter === 'active' ? 'Your incident inbox is clear' : 'No matching incidents'}
            >
              New incidents are created from measured failures, not simulator shortcuts.
            </State>
          )}
        </div>
      </Panel>
    </>
  );
}

function Statements({
  title,
  rows,
  onEvidence,
}: {
  title: string;
  rows: Statement[];
  onEvidence: () => void;
}) {
  return (
    <section className="report-section">
      <h3>{title}</h3>
      {rows.map((row, index) => (
        <div key={index}>
          <p>{row.text}</p>
          <div className="evidence-references">
            {row.evidence_ids.map((id) => (
              <button key={id} onClick={onEvidence}>
                E-{id}
              </button>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

export function IncidentView({ id }: { id: number }) {
  const { go, act, busy } = useWorkspace(),
    [tab, setTab] = useState('Investigation'),
    [noteOpen, setNoteOpen] = useState(false),
    [note, setNote] = useState('');
  const query = useQuery({
    queryKey: ['incident', id],
    queryFn: () => api<IncidentDetail>('/incidents/' + id),
    refetchInterval: 15000,
  });
  const config = useQuery({ queryKey: ['settings'], queryFn: () => api<Settings>('/settings') });
  if (!query.data) return <State error={query.error} />;
  const { incident: i, impact, evidence, timeline, candidates, investigation } = query.data;
  const root = candidates[0];
  const businessSignals = evidence.filter((item) => item.facts.kind === 'business_metric').slice(-3);
  const investigate = (use_llm = false) =>
    act('Investigation report generated', () =>
      api('/incidents/' + id + '/investigate', 'POST', { use_llm }),
    );
  return (
    <>
      <button className="back-link" onClick={() => go('incidents')}>
        Incident inbox <span>/</span> DP-{id + 1000}
      </button>
      <Heading title={i.title} description={`Opened ${dateTime(i.created_at)} · DP-${id + 1000}`}>
        <Badge status={i.status} />
        <a className="btn" href={'/api/incidents/' + id + '/report'} download>
          <Download size={15} />
          Export report
        </a>
      </Heading>
      <div className="incident-toolbar">
        <div>
          <Badge status={i.severity} />
          <span>
            <UserRound size={14} />
            {i.owner}
          </span>
          <span>
            <BookOpen size={14} />
            {evidence.length} evidence records
          </span>
        </div>
        <div>
          {i.status !== 'resolved' && (
            <>
              <Button
                disabled={!!busy}
                onClick={() =>
                  act('Investigation assigned to you', async () => {
                    const user = await api<{ email: string }>('/auth/me');
                    return api('/incidents/' + id, 'PATCH', { owner: user.email, status: 'investigating' });
                  })
                }
              >
                Assign to me
              </Button>
              <Button onClick={() => setNoteOpen(true)}>
                <MessageSquare size={14} />
                Add note
              </Button>
            </>
          )}
        </div>
      </div>
      <div className="incident-stats">
        <Metric
          label="Probable origin"
          value={<span className="origin-name">{i.root_dataset_id}</span>}
          caption="Ranked by observed evidence"
          icon={<GitBranch size={16} />}
        />
        <Metric
          label="Evidence rank"
          value={
            <>
              {i.root_score.toFixed(0)}
              <small>/ 100</small>
            </>
          }
          caption="Heuristic score, not a probability"
        />
        <Metric
          label="Observed impact"
          value={impact.observed.length}
          caption={`${impact.potential.length} additional assets potentially affected`}
        />
        <Metric
          label="Recovery checks"
          value={
            <>
              {i.healthy_runs}
              <small>/ 2</small>
            </>
          }
          caption={i.status === 'resolved' ? 'Healthy runs verified' : 'Consecutive healthy runs required'}
        />
      </div>
      {businessSignals.length > 0 && (
        <Panel title="Observed business impact">
          <div className="business-impact">
            {businessSignals.map((item) => (
              <div key={item.id}>
                <strong>{item.title.replace('Business metric · revenue:', '')} revenue</strong>
                <p>
                  Measured {formatNumber(item.facts.observed)} against a healthy baseline of{' '}
                  {formatNumber(Number(item.facts.details.baseline))}. Change:{' '}
                  {Number(item.facts.details.delta_pct).toFixed(1)}%.
                </p>
                <button className="text-button" onClick={() => setTab('Evidence')}>
                  Inspect evidence E-{item.id} <ArrowRight size={14} />
                </button>
              </div>
            ))}
            <p className="muted">
              A reporting change can reflect a failed join or allocation. It does not establish a loss in
              total business revenue.
            </p>
          </div>
        </Panel>
      )}
      <div className="tabs" role="tablist" aria-label="Incident sections">
        {['Investigation', 'Evidence', 'Timeline', 'Affected assets'].map((t) => (
          <button
            role="tab"
            aria-selected={tab === t}
            key={t}
            onClick={() => setTab(t)}
            className={tab === t ? 'active' : ''}
          >
            {t}
            {t === 'Evidence' && <span>{evidence.length}</span>}
          </button>
        ))}
      </div>
      {tab === 'Investigation' && (
        <div className="investigation-grid">
          <div>
            <Panel className="root-cause-panel">
              <div className="root-label">
                <FileSearch size={18} />
                PROBABLE ROOT CAUSE<span>Evidence model v1</span>
              </div>
              <h2>{i.root_dataset_id}</h2>
              <p>
                The current evidence ranks this dataset highest based on its upstream position, the affected
                paths it explains, and supporting monitor failures.
              </p>
              <div className="evidence-references">
                {root?.evidence_ids.slice(0, 6).map((e) => (
                  <button onClick={() => setTab('Evidence')} key={e}>
                    E-{e}
                  </button>
                ))}
              </div>
              <Button onClick={() => go('lineage/' + i.root_dataset_id)}>
                <GitBranch size={15} />
                Trace the downstream path <ArrowRight size={15} />
              </Button>
            </Panel>
            <Panel
              title="Investigation report"
              meta={
                <span className="provider-label">
                  {investigation?.provider === 'configured_llm'
                    ? 'AI-assisted suggestions'
                    : 'Evidence synthesis'}
                </span>
              }
            >
              {!investigation ? (
                <div className="investigate-empty">
                  <span className="investigate-icon">
                    <FileSearch size={27} />
                  </span>
                  <h3>Turn the evidence into a clear next step.</h3>
                  <p>
                    Generate a report that separates verified observations, inference, and unproven
                    hypotheses. No AI provider is required.
                  </p>
                  <Button primary disabled={!!busy} onClick={() => investigate()}>
                    <FileSearch size={16} />
                    Generate investigation
                  </Button>
                </div>
              ) : (
                <div className="investigation-report">
                  <p className="report-summary">{investigation.report.summary}</p>
                  <Statements
                    title="Verified evidence"
                    rows={investigation.report.verified}
                    onEvidence={() => setTab('Evidence')}
                  />
                  <Statements
                    title="Inference"
                    rows={investigation.report.inference}
                    onEvidence={() => setTab('Evidence')}
                  />
                  <Statements
                    title="Unproven hypotheses"
                    rows={investigation.report.hypotheses}
                    onEvidence={() => setTab('Evidence')}
                  />
                  <Statements
                    title="Recommended next steps"
                    rows={investigation.report.recommendations}
                    onEvidence={() => setTab('Evidence')}
                  />
                  <div className="report-limits">
                    <ShieldCheck size={17} />
                    <p>{investigation.report.limitations}</p>
                  </div>
                  <Button disabled={!!busy} onClick={() => investigate()}>
                    Refresh evidence report
                  </Button>
                </div>
              )}
              {config.data?.ai_configured && (
                <div className="ai-consent">
                  <p>
                    Optional: send measurements, dataset identifiers and contract descriptions to your
                    configured AI provider. Raw rows and failed-value samples are excluded.
                  </p>
                  <Button disabled={!!busy} onClick={() => investigate(true)}>
                    <Sparkles size={15} />
                    Send evidence for AI suggestions
                  </Button>
                </div>
              )}
            </Panel>
          </div>
          <div>
            <Panel title="Why this candidate ranks first">
              <div className="rank-total">
                <strong>{i.root_score.toFixed(0)}</strong>
                <span>
                  out of 100
                  <br />
                  evidence points
                </span>
              </div>
              <div className="score-breakdown">
                {root &&
                  Object.entries(root.contributions).map(([name, points]) => (
                    <div key={name}>
                      <span>{name}</span>
                      <strong>+{points}</strong>
                    </div>
                  ))}
              </div>
              <p className="panel-footnote">
                Scores measure support under the documented heuristic. They do not establish causation.
              </p>
            </Panel>
            <Panel title="Other candidates">
              <div className="candidate-list">
                {candidates.slice(1, 5).map((c) => (
                  <button key={c.dataset_id} onClick={() => go('datasets/' + c.dataset_id)}>
                    <DatabaseIcon />
                    <span>{c.dataset_id}</span>
                    <strong>{c.score}</strong>
                  </button>
                ))}
                {candidates.length < 2 && (
                  <p className="small-empty">No other anomalous dataset candidates.</p>
                )}
              </div>
            </Panel>
            <Panel title="Investigation checkpoints">
              <div className="checkpoints">
                {[
                  ['Detection', evidence.length > 0],
                  ['Lineage correlation', !!root],
                  ['Root-cause ranking', !!root],
                  ['Investigation report', !!investigation],
                  ['Verified recovery', i.status === 'resolved'],
                ].map(([name, done]) => (
                  <div key={String(name)} className={done ? 'complete' : ''}>
                    <span>{done ? <Check size={12} /> : null}</span>
                    {name}
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </div>
      )}
      {tab === 'Evidence' && (
        <Panel
          title="Evidence ledger"
          meta={<span className="meta">Immutable observations with source run references</span>}
        >
          <div className="evidence-ledger">
            {evidence.map((e) => (
              <details key={e.id}>
                <summary>
                  <span className="evidence-id">E-{e.id}</span>
                  <div>
                    <strong>{e.title}</strong>
                    <small>
                      {e.facts.dataset} · {dateTime(e.facts.observed_at)}
                    </small>
                  </div>
                  <span className="meta">{e.facts.method}</span>
                  <ArrowUpRight size={15} />
                </summary>
                <div className="evidence-body">
                  <dl>
                    <dt>Observed</dt>
                    <dd>{formatNumber(e.facts.observed)}</dd>
                    <dt>Expected</dt>
                    <dd>{e.facts.expected}</dd>
                    <dt>Run ID</dt>
                    <dd className="mono">{e.facts.run_id}</dd>
                  </dl>
                  <pre>{JSON.stringify(e.facts.details, null, 2)}</pre>
                </div>
              </details>
            ))}
          </div>
        </Panel>
      )}
      {tab === 'Timeline' && (
        <Panel
          title="Incident timeline"
          meta={<span className="meta">Actual observation and operator timestamps</span>}
        >
          <div className="timeline">
            {timeline.map((event) => (
              <div className="timeline-event" key={event.id}>
                <div className={'timeline-dot ' + event.kind} />
                <time>{dateTime(event.created_at)}</time>
                <div>
                  <span className="timeline-kind">{human(event.kind)}</span>
                  <p>{event.message}</p>
                </div>
              </div>
            ))}
          </div>
          <p className="panel-footnote">
            Detection order is not proof of when the underlying source fault began.
          </p>
        </Panel>
      )}
      {tab === 'Affected assets' && (
        <div className="two-column">
          {[
            ['Observed impact', impact.observed],
            ['Potential downstream impact', impact.potential],
          ].map(([title, assets]) => (
            <Panel key={String(title)} title={String(title)}>
              <p className="panel-footnote">
                {title === 'Observed impact'
                  ? 'These assets have recorded anomalies in this incident.'
                  : 'Lineage-reachable assets without a recorded anomaly in this incident.'}
              </p>
              <div className="dependency-list">
                {(assets as string[]).map((asset) => (
                  <button key={asset} onClick={() => go('datasets/' + asset)}>
                    <GitBranch size={16} />
                    <span>{asset}</span>
                    <ArrowRight size={15} />
                  </button>
                ))}
                {!assets.length && <div className="small-empty">No assets in this category.</div>}
              </div>
            </Panel>
          ))}
        </div>
      )}
      <Modal
        open={noteOpen}
        onClose={() => setNoteOpen(false)}
        title="Add an investigation note"
        description="Your note becomes part of the incident's permanent timeline."
      >
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (await act('Note added to the incident', () => api('/incidents/' + id, 'PATCH', { note }))) {
              setNote('');
              setNoteOpen(false);
            }
          }}
        >
          <label>
            Note
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              required
              maxLength={2000}
              rows={5}
            />
          </label>
          <Button primary type="submit" disabled={!!busy}>
            Add note
          </Button>
        </form>
      </Modal>
    </>
  );
}
function DatabaseIcon() {
  return <GitBranch size={15} />;
}
