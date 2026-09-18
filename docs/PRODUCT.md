# Product definition

## Who it serves

Data Police gives a data platform or analytics engineer one place to triage data failures, connect a business symptom to upstream evidence, record an investigation and confirm recovery. The release ships one configured retail workspace so its workflows can be demonstrated without connecting private company systems.

Its core product unit is an **incident supported by evidence**, not an alert count. A useful investigation identifies what was measured, which datasets are affected, why a candidate ranks first and what new measurements would confirm recovery.

## Primary operator journey

| Stage | Operator question | Product response |
| --- | --- | --- |
| Observe | Where should I look? | Estate summary, datasets needing attention, active incidents and recent signals |
| Inspect | What changed? | Schema/profile history, quality results, actual failed observations and pipeline timing |
| Trace | Where did the symptom originate? | Interactive dataset lineage and candidate score contributions |
| Investigate | What is known and what is still uncertain? | Evidence ledger, verified report, inference, hypotheses and recommendations |
| Coordinate | Who is handling it? | Incident ownership, notes, state and persisted timeline |
| Recover | Has the correction worked? | Two clean materializations of every observed affected dataset |

The interface includes responsive navigation, keyboard-focus styles, dialog labels, explicit loading/errors, meaningful empty states and live updates. It has not undergone a full accessibility certification or broad cross-browser compatibility audit.

## Ten supplied scenarios

| Scenario | Actual change | Expected evidence |
| --- | --- | --- |
| Country code change | Payment source emits PAK instead of PK | Accepted-value failure, distribution drift, unresolved country join and Pakistan revenue anomaly |
| Missing customer identifiers | Forty percent of orders have null customer IDs | Completeness and downstream reference failures |
| Duplicate order delivery | Extra copies of 25% of orders | Raw uniqueness/duplicate anomalies; cleanup keeps downstream exact duplicates out |
| Partial API response | Provider returns 40% of payments | Learned volume change after warm-up and missing order-payment joins |
| Paused ingestion | No new materializations | Independent freshness findings after the threshold |
| Payment mix shift | Payment mix moves to cash on delivery | JS distribution divergence after warm-up |
| Negative payment amounts | One in four amounts becomes negative | Range/reconciliation failures and possible distribution/metric changes |
| Removed API field | Actual response omits payment_method | Missing schema field, quality errors and downstream transform failure |
| Revenue calculation regression | Fact transform doubles captured amounts | Reconciliation failure at fact_orders |
| Provider unavailable | Real endpoint returns HTTP 503 | Bounded extraction retries followed by pipeline failure |

The lab is intentionally limited to one active scenario. Each run captures its scenario and deterministic random seed. A restore changes future source behavior; it does not rewrite incident history or pretend the fault never happened.

## v0.1 release boundaries

| Available now | Boundary |
| --- | --- |
| Configured SQL, HTTP and CSV source types | The Sources page tests existing adapters. It is not a generic Add connector wizard. |
| Custom rules | Create validated JSON definitions and enable/disable with saved versions. Editing a rule's parameters in place is not exposed. |
| Statistical baselines | Eight healthy batches minimum. No seasonal model, learned ML model or calibrated p-value claim across many tests. |
| Dataset lineage | Explicit dependencies. No SQL parser-derived or column-level lineage. |
| Source and operator changes | Logged simulator, rule and ownership actions. No automatic Git/deployment watcher. |
| Incident ranking | Transparent heuristic support score. No causal certainty. |
| Investigator | Built-in report and optional protocol integration. No autonomous remediation or unreviewed SQL execution. |
| Local sign-in | One administrator and one workspace. No tenant isolation, invitation workflow, SSO or RBAC. |
| Run history and recovery | Durable runs and per-asset checkpoints. No arbitrary partition backfills or generic job editor. |
| Self-hosted deployment files | Compose and CI configuration supplied. Container/PostgreSQL runtime acceptance still requires a suitable host. |

## Next release priorities

1. Complete native PostgreSQL and full Compose acceptance on the target WSL/Docker host, including restart and backup-restore drills.
2. Add retention policies and per-source extraction cursors before increasing schedule frequency or dataset volume.
3. Add tenant-aware authentication and least-privilege connector credentials before onboarding additional organizations.
4. Add parameter editing with rule-version diffs and graph-version migrations for ongoing source evolution.
5. Evaluate seasonal baselines and multi-root incident grouping on labeled, representative workloads before claiming better detection accuracy.

No paid external service is required for the built-in workspace. Optional AI usage can incur provider charges. Infrastructure storage, memory and compute consumption remain the operator's responsibility.
