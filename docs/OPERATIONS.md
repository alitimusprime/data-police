# Operating Data Police

## Runtime profiles

| Profile | Data storage | Work execution | Scheduling |
| --- | --- | --- | --- |
| Docker Compose | PostgreSQL 16, Parquet under `runtime/app` | Redis 7 and Celery | Dagster every two minutes; independent monitor every five seconds |
| Local launcher | SQLite databases and Parquet under `runtime` | Single-thread local executor | Pipeline every 60 seconds by default; independent monitor every five seconds |

The complete stack disables the monitor's periodic pipeline trigger with `DP_AUTO_RUN_SECONDS=0`, because Dagster owns that schedule. The monitor still performs freshness checks and pending-job redelivery. Settings displays the local scheduler interval; a zero there does not mean the separate Dagster schedule is stopped.

For a controlled Docker demo, pause the Dagster schedule in its UI or stop its daemon with `docker compose stop dagster-daemon`. Keep `monitor` running if you want freshness monitoring. Resume with `docker compose start dagster-daemon`.

## Configuration

Bootstrap derives `.env` from `.env.example` once. It does not overwrite existing configuration. Configuration changes require restarting the affected processes. In Compose, use `docker compose up -d` to recreate services with changed environment values; a plain restart does not recreate their environment.

| Variable | Meaning |
| --- | --- |
| DP_DATABASE_URL | SQLAlchemy operational database URL |
| DP_SOURCE_DATABASE_URL | Synthetic source database URL, distinct from control-plane storage in Compose |
| DP_DATA_DIR | Feed and immutable warehouse storage root |
| DP_DEMO_API_URL | Administrator-configured provider base URL |
| DP_EXECUTOR | `local` or `celery` |
| DP_REDIS_URL | Celery broker URL |
| DP_ADMIN_EMAIL / DP_ADMIN_PASSWORD | Single local workspace administrator |
| DP_SESSION_SECRET | HMAC signing secret, at least 32 characters |
| DP_ALLOWED_ORIGINS | Comma-separated permitted browser origins for mutations |
| DP_COOKIE_SECURE | `false` for local HTTP; use `true` behind HTTPS |
| DP_ENABLE_SIMULATOR | Enables or disables lab mutations |
| DP_FRESHNESS_SECONDS | Arrival threshold; default 180 seconds |
| DP_AUTO_RUN_SECONDS | Local monitor's pipeline interval; zero disables that trigger |
| DP_LLM_BASE_URL / DP_LLM_MODEL / DP_LLM_API_KEY | Optional provider configuration |
| POSTGRES_PASSWORD / REDIS_PASSWORD | Generated Compose service credentials |

Compose overrides database URLs, executor, paths and schedule interval to refer to container services. Edit the corresponding Compose environment entry when changing those values for the full stack. `DP_ENV=production` is only a label; it does not automatically configure HTTPS or enterprise security.

## Password and session recovery

Open `.env` locally to retrieve your password. Do not post the file, screenshots of it, or unredacted `docker compose config` output. Compose's resolved output can include credentials.

To change the sign-in password, edit `DP_ADMIN_PASSWORD` locally and keep it at least 12 characters. Rotate `DP_SESSION_SECRET` as well to invalidate already issued sessions, then recreate the API service. Sessions expire after eight hours and are stored in HttpOnly, SameSite=Strict cookies.

Changing `POSTGRES_PASSWORD` in `.env` does not rotate an already initialized PostgreSQL user's password. Perform a database credential rotation as a coordinated operation before changing client configuration. Do not delete the database to fix a password mismatch.

## Service diagnosis

```bash
docker compose ps --all
docker compose logs --tail=100 api worker monitor
docker compose logs --tail=100 demo-api seed dagster-daemon
```

`GET /api/health` confirms that the API can query the operational database. It does not assert the health of the entire pipeline or broker. The Sources page exercises the configured SQL connector, provider API and feed directory. Pipelines shows persisted run status, stage counts, timing and sanitized failure types.

Application JSON logs include event, service, timestamp and selected request/run/dataset identifiers. Application exception logging records error class and trace locations without dumping raw source values or credentials. Uvicorn, Dagster and Celery also have their own logs. Review those before sharing them externally. A metrics exporter, distributed traces and external error collector are not included in v0.1.

Run records are the durable job backlog. During a Redis outage, the API can save a run and return `dispatch: pending`. The monitor retries pending delivery after the broker is healthy. A lost worker's lease expires after ten minutes; the next attempt can resume previously committed asset profiles. Do not manually clear leases while a worker is still operating.

## Optional AI provider

Configure a chat-completions-compatible base URL, model and credentials in `.env`. The base URL should end at the API prefix, for example `/v1`; the application appends `/chat/completions`. Restart the API after editing configuration.

The provider must support `response_format: {"type":"json_object"}` and return `choices[0].message.content` containing the expected JSON report. The server timeout is 45 seconds, and automatic redirect following is disabled. The integration is protocol based and has not been live-tested with a particular provider in this release.

Nothing is sent merely by configuring the key. The operator must click **Send evidence for AI suggestions**. The packet includes dataset identifiers, monitor descriptions, expected contracts, observed measurements, allowlisted aggregate details and evidence IDs. It excludes raw rows, failed-value samples and arbitrary nested details. Review contract descriptions before using sensitive data. The built-in evidence report remains available without a paid API or external connection.

## Backup and restore

The control-plane database and Parquet files reference one another. A database-only backup cannot restore dataset evidence files. Back up the source database if replaying original source batches matters. Keep `.env` in a separate protected credential backup.

For a small local Docker installation, stop the stack, copy the entire project `runtime` directory to a dated location, then resume it. A stopped PostgreSQL data-directory copy must be restored using the same PostgreSQL major version. For a running managed installation, use PostgreSQL's supported logical backup tools and a coordinated snapshot of the warehouse. The repo does not provide an online point-in-time recovery service.

An example cold backup, from the project root, to the D-backed WSL home:

```bash
docker compose stop
mkdir -p ~/data-police-backups
sudo tar -czf ~/data-police-backups/runtime-$(date -u +%Y%m%dT%H%M%SZ).tar.gz runtime
docker compose up -d
```

`sudo` may be needed to read PostgreSQL-owned files. Inspect the destination and available space first. Restore into an empty, separate installation using the same release and PostgreSQL major version; preserve ownership and verify the application before replacing the original. No destructive reset script is included.

For SQLite, stop the local launcher before copying the whole `runtime` directory. Copy any WAL sidecar files with the databases, or use SQLite's supported backup API. A copied database must remain paired with its warehouse files.

## Retention and capacity

Retention is manual in v0.1. Every run retains source rows, feeds, 19 Parquet batches, profiles, monitor results and events. The seed is 12 measured batches with roughly 330 orders each, not a large-data load test. At a two-minute schedule, a day creates 720 materializations per asset. Stop automatic scheduling when the workspace is not being used, and inspect disk consumption with `du -sh runtime`.

The engine materializes dataframes in memory. Pagination bounds connector requests but does not make the whole workload streaming. Do not point the supplied generator or connector contract at a production database. Real source onboarding requires a read-only adapter, explicit extraction boundaries, credentials management and data-volume tests.

## Upgrade discipline

Back up data before upgrading. Apply Alembic revisions through the `migrate` service before starting new API and worker code. The catalog is initialized once; changes to the registry or seeded rules need an explicit migration for an existing workspace. `create_all` is used only in disposable tests, not to upgrade a running installation.

The initial release has no remote repository or deployed instance attached. Initialize your own Git repository from the source when ready, inspect staged files and keep `.env`, `runtime`, dependency directories and build artifacts excluded.
