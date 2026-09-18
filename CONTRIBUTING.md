# Contributing to Data Police

Thank you for taking the time to improve Data Police. This guide covers local setup, checks, and the contracts that keep the pipeline, product interface, and evidence model aligned.

## Development requirements

Install the following tools before starting:

- Git
- Python 3.12 or newer
- Node.js 22 or newer with npm
- Docker with Compose v2 for the full service stack and PostgreSQL integration tests

Python must include `pip` and the `venv` module. Debian and Ubuntu users may need to install the matching venv package separately, such as `python3.12-venv`.

Linux, macOS, Windows PowerShell, and WSL2 can run the local profile. Linux or WSL2 is recommended when working on the complete Docker stack because its bind mounts and service processes match the container runtime closely.

Clone your fork and create a branch:

```bash
git clone https://github.com/YOUR-USERNAME/data-police.git
cd data-police
git switch -c change/short-description
```

## Set up the local profile

### Linux, macOS, or WSL

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
cd web
npm ci
npm run build
cd ..
python scripts/bootstrap.py
python scripts/start_local.py
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
Set-Location web
npm ci
npm run build
Set-Location ..
.\.venv\Scripts\python.exe scripts\bootstrap.py
.\.venv\Scripts\python.exe scripts\start_local.py
```

If `py` is unavailable, use `python` for the first command after confirming that it points to Python 3.12 or newer.

The launcher starts the synthetic provider, applies migrations, creates the baseline when needed, and serves the product at [http://localhost:8000](http://localhost:8000). Stop it with `Ctrl+C`.

For frontend development, keep the local launcher running and start Vite in another terminal:

```bash
cd web
npm run dev
```

Vite serves the interface on `127.0.0.1:5173` and proxies API requests to port 8000. If you change the port or hostname, update `DP_ALLOWED_ORIGINS` in `.env` and restart the API.

## Run the full stack

Create local secrets and start the services:

```bash
python3 scripts/bootstrap.py
docker compose up --build -d
docker compose ps --all
```

On Windows PowerShell, use `py -3.12 scripts/bootstrap.py` for the first command. Run the Docker workflow inside WSL2 if the project is stored on a Windows filesystem that does not preserve Linux ownership correctly.

Use `docker compose logs --tail=100 SERVICE_NAME` while diagnosing startup. Stop the stack with `docker compose stop` so its data remains available for the next run.

## Checks before a pull request

Run Python formatting, linting, tests, and the secret audit from the repository root:

```bash
python -m ruff format --check backend tests scripts migrations
python -m ruff check backend tests scripts migrations
python -m pytest -q
python scripts/secret_audit.py
```

Run the frontend checks from `web`:

```bash
npm run test
npm run build
npx prettier --check src
```

Install Playwright's Chromium once, then run the browser acceptance test from the repository root:

```bash
cd web
npx playwright install chromium
cd ..
DP_QA_PYTHON="$(pwd)/.venv/bin/python" node scripts/browser_qa.mjs
```

Windows PowerShell uses a different environment-variable form:

```powershell
Set-Location web
npx playwright install chromium
Set-Location ..
$env:DP_QA_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
node scripts\browser_qa.mjs
```

The browser test creates temporary databases and starts its own provider and API. It does not use or reset the normal workspace under `runtime`.

## PostgreSQL and Redis integration tests

The standard test suite uses SQLite and skips the separate Redis worker test unless a broker URL is supplied. The CI workflow runs the suite again with PostgreSQL and Redis services.

For PostgreSQL testing, create an empty database named exactly `datapolice_test` and use test-only credentials:

```bash
export DP_TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/datapolice_test'
export DP_TEST_SOURCE_DATABASE_URL="$DP_TEST_DATABASE_URL"
export DP_TEST_REDIS_URL='redis://127.0.0.1:6379/0'
python -m pytest -q
```

PowerShell uses `$env:DP_TEST_DATABASE_URL`, `$env:DP_TEST_SOURCE_DATABASE_URL`, and `$env:DP_TEST_REDIS_URL` instead of `export`.

These tests drop and recreate tables. The safety check rejects external database names other than `datapolice_test`, but the supplied URLs must still point to disposable local services. Never use a development, staging, or production database.

## Working with the codebase

### Adding a dataset

1. Add the asset, layer, owner, and parent IDs to `catalog.ASSETS` in dependency order.
2. Implement its connector or transformation using the existing batch contract.
3. Add declarative quality rules where they provide useful evidence.
4. Add a migration so existing workspaces receive the catalog change.
5. Test the Parquet output, profile, quality results, downstream dependencies, and Dagster materialization.

The asset registry drives execution, stored lineage, Dagster, and the frontend graph. A dataset should not be added only to the UI.

### Adding a rule or detector

Rules must validate their parameters and return measured, expected, and failed-row results. Keep samples bounded and do not execute user-provided Python or SQL.

Detectors should record the observation, threshold, method, and supporting details. Respect baseline warm-up and label sampled statistics clearly. Include a normal boundary case as well as the failure case in tests. Evidence rankings must remain explainable and must not be presented as probabilities.

### Changing the API or interface

Keep API responses typed in `web/src/types.ts` and cover error behavior in `web/src/api.test.ts` or backend route tests. Test keyboard navigation and the 390-pixel mobile layout when changing shared navigation, tables, dialogs, or incident actions.

Do not expose secrets, connector credentials, raw failed rows, or internal exception text through API responses, browser events, or logs.

## Dependency changes

Direct Python dependency ranges live in `pyproject.toml`. `requirements.lock` pins the complete development and orchestration environment used by CI and the runtime image. Regenerate it deliberately:

```bash
uv pip compile pyproject.toml --extra dev --extra orchestration -o requirements.lock
```

Review the resulting diff, run the complete checks, and repeat the dependency audit. Installing `uv` is only necessary when changing the Python lock file.

Frontend dependencies are recorded in `web/package.json` and pinned in `web/package-lock.json`. Use `npm install PACKAGE` to change them and `npm ci` to reproduce the locked environment. The frontend build copies Swagger UI assets into `web/public/api-doc-assets`; the generated JavaScript and CSS files remain ignored.

## Commits and pull requests

- Keep a pull request focused on one problem or capability.
- Explain the behavior change and the reason for it.
- Include migrations for persistent schema or catalog changes.
- Add tests that prove meaningful behavior or prevent a likely regression.
- Update documentation when commands, configuration, or product behavior change.
- Keep `.env`, runtime data, databases, Parquet files, dependency folders, and compiled output out of Git.
- Check `git status` and `git diff --cached` before every push.

The release packager includes tracked source, the compiled UI, documentation, and selected verification artifacts. Run `python scripts/package_release.py` only after the relevant checks pass. The generated archive contains a SHA-256 manifest and excludes local Git history, credentials, dependencies, and runtime data.
