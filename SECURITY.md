# Security model

Data Police v0.1 is designed for a trusted local operator and synthetic retail data. The Docker API and Dagster ports bind to `127.0.0.1`. The provider, database and broker are internal container services.

## Implemented controls

- Bootstrap generates unique administrator, session, database and broker secrets. Startup checks the administrator password and session-secret lengths outside tests.
- Sign-in issues an eight-hour signed HttpOnly, SameSite=Strict cookie. Password and signature comparisons are constant time. Sign-in attempts are limited per client address in the API process.
- Data and mutation routes require authentication. Mutations require a custom request header and permitted Origin. Pydantic validates route input. A declared request-size check rejects oversized Content-Length values.
- CSP, frame restrictions, MIME sniffing protection and API no-store headers apply to normal responses. Swagger assets are served locally.
- SQL inputs are parameterized, source tables are allowlisted, file reads are restricted to the feed directory, and arbitrary rule code is not evaluated.
- Application errors return safe messages. Application structured logs exclude raw exception text and credential values by design.
- The default report uses local evidence. Optional AI requests require an operator action and omit raw failed-value samples and arbitrary nested details. Generated verified facts are discarded in favor of deterministic evidence.
- The runtime image uses a non-root application user. A separate one-shot service sets ownership only on the application runtime directory.

## Boundaries before internet deployment

There is one environment-configured administrator, with no password database, SSO, roles, account recovery, invitation or tenant isolation. The rate limiter is per process and does not coordinate across API replicas. Session-secret rotation invalidates issued sessions; individual session revocation is not implemented. The UI's administrative settings do not grant separate privileges.

TLS termination, ingress body-size enforcement, distributed rate limits, protected Dagster access, least-privilege production database users, backup encryption, a secrets manager and infrastructure audit logging are not provided. The Compose demo database user also owns the synthetic source ecosystem and is not a production read-only connector identity. Do not expose this stack publicly by changing a host bind address alone.

Raw Parquet, internal evidence samples and operational metadata are not encrypted at rest by the application. Protect the host filesystem and backups. The supplied data is synthetic. Replacing it with sensitive real data requires a deliberate access, retention and redaction design.

The `/api/health` endpoint and OpenAPI schema are public metadata. Dataset contents and incident records require authentication. Configured URLs are administrator controlled; a public arbitrary-URL fetch endpoint is not exposed.

## Reporting a problem

No external issue tracker or security mailbox is configured for this generated release. Use your repository's private reporting channel after establishing one. When sharing a reproduction, exclude `.env`, source rows, passwords, tokens, resolved Compose configuration and database URLs. Share the sanitized error type, run/request ID, relevant version and minimum reproduction steps.
