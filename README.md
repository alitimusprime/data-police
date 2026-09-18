# Data Police

**A data reliability workspace that connects a downstream symptom to its upstream evidence.**

Data Police ingests a synthetic retail ecosystem through real SQL, HTTP and file interfaces, stores immutable dataset batches, measures their health, and groups related failures into investigations. Operators can trace dependencies, inspect evidence, assign incidents, change quality rules and verify recovery from one interface.

Version 0.1.0 is a self-hosted, single-workspace product build. Start with [START_HERE.md](START_HERE.md) for the Windows/WSL and D-drive setup. The release includes the source and a compiled interface.

![Data Police incident overview](docs/screenshots/overview-incident.png)

## Run it

Inside your D-backed Ubuntu WSL distribution, from the extracted project directory, with Docker Desktop's WSL integration running:

```bash
python3 scripts/bootstrap.py
docker compose up --build -d
docker compose ps --all
```

Open **http://localhost:8000** and sign in with the email and password printed by bootstrap. Keep those credentials private. First startup builds dependencies, applies the migration and measures 12 real baseline batches. Successful one-shot services such as `seed` show `Exited (0)`.

The complete stack includes PostgreSQL, Redis, Celery workers, a live provider API, an independent freshness monitor, Dagster scheduling and the product API. The lighter SQLite profile runs without Docker and is described in [START_HERE.md](START_HERE.md).

## Demonstrate the product

1. Open Overview. The initial estate contains **19 datasets** and **14 enabled rules**. History is computed from measured batches.
2. Open Failure lab, choose **Country code change**, then **Inject & run**.
3. The provider returns `PAK` where the country dimension expects `PK`. The pipeline continues, country joins fail, and country revenue changes.
4. Open the incident. `raw_payments` ranks above the downstream symptoms. Inspect its score contributions, evidence records and observed versus potential impact.
5. Generate an investigation. Verified observations, inference and hypotheses are separate. Export the report and inspect the lineage path.
6. Restore the healthy source, then complete two clean pipeline runs. The incident moves through monitoring to resolved.

This scenario changes source data. The simulator does not insert an incident, overwrite a chart or prescribe the root-cause result. Monetary values and exact counts vary by batch; the example moves all Pakistan payments to an unmatched country, so it can show a 100% drop in resolved Pakistan revenue. That is a reporting allocation failure, not proof that total business revenue disappeared.

## What is implemented

| Capability | Implementation |
| --- | --- |
| SQL ingestion | Native typed source tables, parameterized SQLAlchemy queries and keyset paging within immutable batches |
| REST ingestion | Live FastAPI provider, actual HTTP pagination, bounded retries, timeouts and response checks |
| File ingestion | Supplier CSVs, directory allowlist, size/schema checks and SHA-256 checksums |
| Processing | Polars cleanup and joins, DuckDB SQL aggregation over committed Parquet |
| Historical profiling | Row and column counts, nulls, exact duplicates, cardinality, numeric summaries, categorical counts, timestamp ranges and selected business metrics |
| Data quality | Eight declarative rule types, validation, saved versions, per-run outcomes and failed-value samples |
| Detection | Schema differences, independent freshness, robust volume bounds, null/duplicate changes, JS and KS distribution tests, country-revenue anomalies |
| Lineage | One asset contract drives execution, saved dependency edges, Dagster assets and the interactive graph |
| Investigations | Directional graph/time correlation, immutable evidence, explainable candidate scores, ownership, notes and automatic recovery |
| Optional AI | Configured chat-completions-compatible provider, filtered evidence packet, structured output and evidence-ID validation |
| Durable work | Database run records, idempotency keys, shared lease, resumable asset commits and Redis/Celery delivery |
| Product interface | Overview, catalog, dataset profiles, lineage, incident inbox/detail, pipelines, rules, sources, failure lab, activity and settings |
| Operations | Alembic migration, containers, CI workflow, structured application logs, health endpoint and SSE live updates |

## Verification and boundaries

The local backend, real HTTP ingestion, real Redis/Celery delivery, Dagster in-process materializations and browser acceptance workflow have been exercised. See [docs/VERIFICATION.md](docs/VERIFICATION.md) for exact results and reproduction commands.

The Docker stack and native PostgreSQL runtime are supplied but were **not executed in the build workspace**. Docker was unavailable, and native PostgreSQL initialization was blocked by process-ownership restrictions. CI includes PostgreSQL and container checks, but no remote CI run has been performed. A live external AI provider has not been tested.

This release does not provide multi-tenant SaaS isolation, SSO/RBAC, billing, generic connector onboarding, CDC, column-level lineage, seasonal forecasting, calibrated causal confidence, automated retention or a production availability guarantee. It is a complete integrated release for the supplied retail workspace, with those expansion boundaries made explicit.

## Engineering guide

| File | Use |
| --- | --- |
| [START_HERE.md](START_HERE.md) | Install and use Data Police on your Windows/WSL setup |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Data flow, persistence, algorithm definitions and design decisions |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Credentials, scheduling, backups, failure handling and configuration |
| [docs/VERIFICATION.md](docs/VERIFICATION.md) | Test evidence and remaining runtime gates |
| [docs/PRODUCT.md](docs/PRODUCT.md) | Product workflow, capability boundaries and next release priorities |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development, tests and extension contracts |
| [SECURITY.md](SECURITY.md) | Implemented controls and deployment assumptions |

The Python code lives in `backend/data_police`, the React/TypeScript interface in `web/src`, and deployment definitions in `compose.yaml`, `Dockerfile` and `infra`. Sign in, then visit **http://localhost:8000/api/docs** for the interactive API reference. Its assets are bundled locally.
