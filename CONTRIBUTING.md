# Development guide

Use Python 3.12 or newer and Node 22 in Ubuntu/WSL. Keep source, environments and container storage on your D-backed Linux filesystem.

## Install and run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python scripts/bootstrap.py
cd web
npm ci
npm run build
cd ..
python scripts/start_local.py
```

For fast frontend iteration, run `npm run dev` from `web` in a second terminal. Vite proxies `/api` to the running local API. Open the Vite URL and keep `.env` allowed origins aligned with that port.

## Required checks

```bash
ruff check backend tests scripts migrations
ruff format --check backend tests scripts migrations
pytest -q
python scripts/secret_audit.py
cd web
npm run test
npm run build
npx prettier --check src
npx playwright install chromium
cd ..
node scripts/browser_qa.mjs
```

The browser script starts an isolated source provider and API with disposable databases. It does not change your real workspace. It expects `.venv/bin/python`, or you can set `DP_QA_PYTHON` to another interpreter containing the locked dependencies. `DP_QA_BROWSER_PATH` with `DP_QA_CHROMIUM_MODULE` supports a separately supplied compatible browser on restricted QA hosts; normal development uses Playwright's browser.

See [docs/VERIFICATION.md](docs/VERIFICATION.md) for real Redis and PostgreSQL test configuration. External test databases must be explicitly named `datapolice_test`; those test schemas are cleared between tests. Never set the test variables to a real workspace database.

## Add a dataset

1. Add the asset, owner, layer and parent IDs to `catalog.ASSETS` in dependency order.
2. Implement its source extraction or transformation and add declarative rules where appropriate.
3. Add a migration to register it in existing workspaces. Initialization alone only handles new workspaces.
4. Exercise the actual connector and verify Parquet, profiles, downstream results and Dagster materializations.
5. Define what can fail and how the product should show the resulting evidence.

The graph comes from the shared contract. Do not add nodes only in the React view.

## Add a rule or detector

Rules must validate their parameters, return an expected/observed result and preserve a version. Keep failed-row sampling bounded. Arbitrary user-provided Python or SQL is not supported. Regex rules use Polars' linear-time regex implementation.

A detector must report its method, threshold, observation and supporting details. Respect warm-up and distinguish sampled statistics from full-batch measurements. Add tests for false-positive boundaries as well as the obvious failure case. Avoid presenting a heuristic evidence score as a probability.

## Dependency changes

Python direct ranges live in `pyproject.toml`; `requirements.lock` pins the complete tested environment, including development and Dagster dependencies. Regenerate deliberately with `uv pip compile pyproject.toml --extra dev --extra orchestration -o requirements.lock`, then test and audit. The runtime image currently installs that complete lock, so it includes development tools and is larger than a split-runtime lock would be.

JavaScript dependencies are pinned by `web/package-lock.json`. Use `npm ci` for reproduction. The build copies locally installed Swagger UI assets before compiling the product. Do not commit the generated copies in `web/public/api-doc-assets`.

## Version control and release

Inspect `git status` and staged file names before committing. `.gitignore` excludes `.env`, runtime databases, source data, dependency directories, screenshots generated under `artifacts`, and compiled UI files. The lightweight secret audit detects private environment paths and a small set of secret patterns; it is not a comprehensive scanner.

The release packager includes tracked source, the compiled UI, documentation and selected verification artifacts. It refuses environment files, runtime data, symlinks and dependency folders. Run `python scripts/package_release.py` only after the checks pass. Its manifest records SHA-256 for each packaged file. The archive excludes local Git history; initialize your own repository after extracting it.
