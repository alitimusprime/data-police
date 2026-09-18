# Security policy

## Supported versions

Security fixes are applied to the current release line and the `main` branch.

| Version          | Status               |
| ---------------- | -------------------- |
| `main`           | Active development   |
| `0.1.x`          | Current release line |
| Earlier versions | Not supported        |

## Reporting a vulnerability

Please do not disclose a suspected vulnerability in a public issue, discussion, or pull request.

Use [GitHub private vulnerability reporting](https://github.com/alitimusprime/data-police/security/advisories/new) when it is available. If GitHub does not show the private reporting form, open a public issue asking the maintainer for a private contact method, but do not include security details in that issue.

A useful report includes:

- The affected version or commit
- A clear description of the issue and its impact
- The minimum steps needed to reproduce it
- Relevant logs with secrets, credentials, source rows, and personal data removed
- Any suggested mitigation, if known

Ordinary bugs and feature requests can use the [public issue tracker](https://github.com/alitimusprime/data-police/issues).

## Deployment model

Data Police is currently designed for one trusted workspace with one administrator. The administrator email and password are configured through environment variables. It does not yet provide separate user accounts, role-based access control, tenant isolation, SSO, account recovery, or individual session revocation.

In the supplied Compose configuration, the product API and Dagster interface bind to `127.0.0.1`. PostgreSQL, Redis, and the synthetic provider remain on the internal container network. The default setup is intended for local evaluation and development, not direct exposure to the public internet.

The `/api/health` endpoint and `/api/openapi.json` schema expose service metadata without authentication. Dataset contents, incident records, and the interactive API documentation require a valid session.

## Implemented controls

- Bootstrap generates unique administrator, session, database, and broker secrets in a private `.env` file.
- Startup validates the administrator password and session secret outside the test environment.
- Sign-in creates an eight-hour signed cookie with `HttpOnly` and `SameSite=Strict` attributes. Password and signature comparisons use constant-time checks.
- Sign-in attempts are rate limited per client address within each API process.
- Data and mutation routes require authentication. Mutations also require a custom request header and an allowed `Origin` when an origin is present.
- Pydantic validates API input. A request-size check rejects requests whose declared `Content-Length` is too large.
- SQL values are parameterized, source tables come from an internal registry, and file access is limited to the configured feed directory.
- Responses set a Content Security Policy, prevent framing and MIME sniffing, and disable caching for API responses.
- Application errors use safe client-facing messages. Structured application logs are designed to omit credentials, raw exception text, and source rows.
- The application image runs as an unprivileged user after a one-time service prepares the runtime directory.
- Optional AI output is constrained by a typed schema and cannot replace deterministic facts, scores, or evidence identifiers.

## Secrets and local files

The bootstrap script writes credentials to `.env`. That file, the `runtime/` directory, build output, and local dependency directories are ignored by Git. Keep them private even when Git reports a clean working tree.

Before committing or publishing changes, run:

```bash
python scripts/secret_audit.py
git status --short
git diff --cached
```

The audit script catches common secret patterns, but it is not a complete guarantee. Review staged files for:

- `.env` contents or resolved Compose configuration
- Passwords, API keys, tokens, cookies, and database URLs
- Production data, failed-value samples, or exported evidence
- Private hostnames, internal addresses, and customer identifiers

If a secret enters Git history, rotate or revoke it first. Removing it from a later commit does not make the original value safe.

## Optional AI provider

The standard incident report is deterministic and does not require an AI provider. AI analysis only runs after an explicit operator action.

The provider request may contain dataset identifiers, contracts, monitor metadata, observed metrics, allowlisted aggregate values, and evidence identifiers. It excludes raw source rows, raw failed-value samples, and arbitrary nested evidence. This reduces exposure but does not make the remaining metadata anonymous. Review the configured provider's data handling policy before enabling it for a real environment.

Provider output is treated as untrusted. The application validates its schema and keeps deterministic facts and evidence authoritative. Generated text is limited to interpretation, hypotheses, and recommendations.

## Before exposing the service to a network

Do not make the stack public by changing a bind address alone. A production deployment needs, at minimum:

- TLS termination and secure cookie transport
- An identity provider, account lifecycle, roles, and tenant boundaries appropriate to the deployment
- Network access controls for both the product API and Dagster
- Distributed rate limiting and ingress-level request-size limits
- Separate least-privilege database identities for the application and connected sources
- A managed secrets store and documented rotation process
- Encryption and access controls for databases, warehouse files, logs, and backups
- Defined retention, audit, monitoring, incident response, backup, and recovery procedures
- Dependency, container image, and infrastructure vulnerability scanning

The Compose database user owns the included synthetic source ecosystem. It is not a suitable read-only identity for a production connector.

## Data and backup protection

Data Police does not provide application-level encryption at rest. Protect the host filesystem, Docker volumes, warehouse directory, database, logs, and backups using the controls provided by the operating system and deployment platform.

The included retail data is synthetic. Connecting real or regulated data requires a deliberate access, retention, redaction, and deletion policy. Back up the PostgreSQL database and the warehouse files together so incident metadata and evidence remain consistent.

## Dependency security

Python dependencies are pinned in `requirements.lock`, and frontend dependencies are locked in `web/package-lock.json`. Dependency changes should include regenerated lock data and the relevant test results. Published security advisories and automated audit tools are useful inputs, but their results still require review for reachability and impact in this project.
