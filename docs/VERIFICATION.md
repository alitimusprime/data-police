# Release verification

Release: **Data Police 0.1.0**. Final application checks ran on **14 September 2026** in a Linux build workspace. The evidence below distinguishes completed checks from supplied configuration that still needs a suitable runtime.

## Completed

| Check | Result | Evidence and scope |
| --- | --- | --- |
| Backend suite | **45 passed, 1 skipped** | Rule boundaries, schema/drift detection, scores, lineage traversal, real HTTP pipeline ingestion, fault scenarios, Parquet, incident correlation/recovery, authentication and AI output boundaries |
| Real Redis/Celery worker | **1 passed** separately | Native Redis process, separate Celery worker, real HTTP provider, durable run completion and duplicate delivery without duplicate profiles |
| Dagster execution | Passed inside the backend suite | `dg.materialize` executes the actual multi-asset and records all 19 materializations |
| Frontend tests | **5 passed** | API failure handling, cookie/header boundary and display formatting |
| TypeScript and Vite build | Passed | Compiled static production UI, including bundled Swagger assets |
| Browser acceptance | **18 checks passed** | Real Chromium, logged-in UI, healthy baseline, rule creation, source test, country fault, root ranking, report, ownership, export, 19 graph nodes, mobile navigation, recovery and API docs |
| Browser runtime errors | **0** | No page exceptions or unexpected HTTP failures during acceptance |
| Clean local install | **5 checks passed** | Fresh isolated copy, generated secrets, Alembic migration, 12 seed runs, actual login, 19 healthy datasets and bundled pages |
| SQLite migration | Passed | Upgrade from an empty database followed by `alembic check`; no missing upgrade operations |
| Ruff | Passed | Python lint and formatting checks |
| Dependency audits | No known vulnerabilities found | Locked Python dependencies and production npm dependencies at audit time |

The one skipped backend test is the real Redis worker test, which runs only when `DP_TEST_REDIS_URL` is supplied. It was subsequently run and passed with an actual isolated Redis server. Do not add the Dagster materialization result again to the backend test count.

The external-provider tests use controlled HTTP-client doubles to check output validation and evidence filtering. They verify the contract, not a live model provider's behavior. The browser did not use mocked API fixtures: its server seeded and processed actual synthetic data through SQL, live HTTP, files and Parquet.

Stored evidence is under `docs/verification`: backend and Redis JUnit results, browser checks, clean-startup results and dependency audit JSON. Screenshots are under `docs/screenshots`. The browser runs on synthetic disposable data with `qa@example.test`; this is not a shipped administrator account or password.

## Not executed here

| Gate | Reason / next verification |
| --- | --- |
| Full Docker Compose startup | No Docker engine was available in the build workspace. Start the supplied stack on the target WSL host. |
| Native PostgreSQL tests | The attempted local PostgreSQL initialization was blocked by the workspace's process-ownership restriction. No successful PostgreSQL runtime claim is made. |
| Docker image build | Docker was unavailable. The frontend and Python components built locally, and the container build is included in CI. |
| PostgreSQL-backed Dagster daemon | In-process materialization passed; daemon scheduling with PostgreSQL storage requires the Compose runtime. |
| Remote GitHub Actions run | Workflow supplied, but no external repository was connected or workflow remotely executed. |
| Live optional AI provider | No provider credentials were supplied. Built-in reports and provider contract tests passed. |
| Production scale, failover and recovery drills | No load test, multi-tenant security audit, online backup restoration or high-availability exercise was performed. |

## Reproduce the checks

From the project root with the Python environment active:

```bash
ruff check backend tests scripts migrations
ruff format --check backend tests scripts migrations
pytest -q --junitxml=artifacts/backend-tests.xml
python scripts/secret_audit.py
python scripts/smoke_local.py
```

From `web`:

```bash
npm ci
npm run test
npm run build
npx prettier --check src
npx playwright install chromium
```

Then from the project root:

```bash
node scripts/browser_qa.mjs
```

Run the broker integration against a **dedicated test Redis**:

```bash
DP_TEST_REDIS_URL=redis://127.0.0.1:6379/0 pytest tests/test_worker.py -q
```

Alternatively, install the QA-only `redislite` package into a disposable test environment and run `python scripts/redis_worker_qa.py`. That wrapper launches a native Redis server and a separate Celery process; it does not use an in-memory fake broker. `redislite` is not a runtime dependency.

To validate PostgreSQL, create a separate empty database named exactly `datapolice_test` with test-only credentials, set `DP_TEST_DATABASE_URL` and `DP_TEST_SOURCE_DATABASE_URL` to its SQLAlchemy `postgresql+psycopg://` URLs, then run `pytest -q`. These tests intentionally drop and recreate the test schema between cases. Never point them at a real workspace. The GitHub Actions workflow creates disposable PostgreSQL and Redis services for this purpose.

On a Docker host, run bootstrap, `docker compose config --quiet`, then build/start the stack using START_HERE. Check migration and seed exit codes, service health, sign-in, the country fault and two-run recovery. Check a stop/resume cycle and a backup restore before relying on retained history.

## Non-blocking observations

The pinned FastAPI/Starlette test adapter emits deprecation warnings for its HTTPX and AnyIO compatibility paths. Tests pass; future dependency upgrades should address those upstream transitions. Vite reports that the ECharts chunk exceeds 500 kB uncompressed, approximately 181 kB compressed. This is a bundle-size warning, not a build failure. No production load-time target has been measured.

Dependency audits are advisory snapshots, not a guarantee of vulnerability absence. They cover published findings available to the tools at audit time. Release source and archive paths are also checked to exclude credentials and generated workspace data; the lightweight secret scanner does not recognize every secret format.
