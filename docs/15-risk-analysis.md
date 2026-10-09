# Risk Analysis & Mitigation Plan

Risks are scored Likelihood (L) × Impact (I) on a 1-3 scale (3 = high), with
**Score = L × I** used only to rank, not as a precise metric.

## 1. Product & Scope Risks

| Risk | L | I | Score | Mitigation |
|---|---|---|---|---|
| Scope creep from the long list of sources/features delays shipping any usable product | 3 | 3 | 9 | Strict MVP boundary (see [MVP Roadmap](./10-mvp-roadmap.md) "Scope Boundary"); Graph connectors and AI explicitly deferred |
| Users abandon items in the inbox instead of reviewing them (friction still too high) | 2 | 2 | 4 | Track "% published" success metric from [PRD](./01-prd.md) §8; add inbox digest notifications post-MVP if abandonment is high |
| Generated Markdown quality is poor for complex documents, eroding trust | 2 | 3 | 6 | Converter routing (MarkItDown → Docling escalation for complex PDFs), explicit error state instead of silent bad output, human review step is mandatory by design |

## 2. Technical Risks

| Risk | L | I | Score | Mitigation |
|---|---|---|---|---|
| SQLite concurrency limits under heavier multi-user/connector load | 2 | 2 | 4 | WAL mode for MVP; documented PostgreSQL migration path via SQLAlchemy/Alembic (see [Database Schema](./05-database-schema.md) §1) |
| Long-running conversions (large PDFs/OCR) block or time out | 2 | 2 | 4 | Dedicated async worker pool with per-job time limits and retries, decoupled from the API request/response cycle (see [Architecture](./04-architecture.md) §4) |
| Git publish conflicts (concurrent commits, force-pushes by other tools) corrupt the working clone | 2 | 2 | 4 | Publish Worker always fetches/rebases before writing; failed publishes return the item to `review` status rather than retrying blindly; PR mode (Post-MVP) adds a further safety net |
| Conversion tool version drift changes output unexpectedly after an image rebuild | 2 | 2 | 4 | Pin exact versions in lockfiles/Dockerfile; `conversion_runs` records which tool/version produced each output for traceability |
| Docling/OCR dependencies are heavy (model downloads, memory use) and bloat the container | 2 | 2 | 4 | Document minimum resource requirements; consider an optional separate "rich-pdf" worker image so lightweight deployments can skip it |

## 3. Microsoft Graph Integration Risks

| Risk | L | I | Score | Mitigation |
|---|---|---|---|---|
| Tenant admin consent required for channel messages/transcripts blocks adoption in locked-down orgs | 3 | 2 | 6 | Ship OneDrive/SharePoint (less-privileged) connector first; document exact permissions needed per connector so admins can pre-approve ([MS Graph Integration](./07-ms-graph-integration.md) §2) |
| Graph API throttling/quota during bulk historical sync | 2 | 2 | 4 | Backoff honoring `Retry-After`, batching via `$batch`, incremental delta sync rather than full history pulls by default |
| Webhook subscriptions silently expire, causing missed updates | 2 | 2 | 4 | Scheduled renewal job + polling fallback + "last synced" indicator and alerting in Settings UI if a connector goes stale |
| Refresh token invalidation (password reset, conditional access policy) breaks a connector without clear signal | 2 | 2 | 4 | Surface sync failures as visible audit events/errors in Settings, not just logs |

## 4. Security & Compliance Risks

| Risk | L | I | Score | Mitigation |
|---|---|---|---|---|
| Leaked Git/Graph/AI credentials from a compromised container or misconfigured env | 2 | 3 | 6 | Secrets-by-reference design, never stored in DB or repo; log redaction; documented Vault/KMS upgrade path (see [Security Model](./09-security-model.md) §4) |
| Captured content contains sensitive/regulated data published without adequate review | 2 | 3 | 6 | Human-in-the-loop approval is mandatory by design; redaction rules flagged as a Post-MVP compliance extension ([Post-MVP Roadmap](./11-post-mvp-roadmap.md) Phase 16) |
| Stored-XSS via captured HTML rendered in the review UI | 2 | 2 | 4 | Mandatory HTML sanitization before storage and sanitized Markdown rendering (see [Security Model](./09-security-model.md) §7) |
| Browser extension device token theft | 1 | 2 | 2 | Narrowly scoped token (`capture:write` only), per-device revocation, not the primary session credential |
| Malicious uploaded document (zip bomb, pathological PDF) causes DoS on the worker | 2 | 2 | 4 | Size/type limits, per-job CPU/time/memory limits, isolated worker containers |

## 5. Operational Risks

| Risk | L | I | Score | Mitigation |
|---|---|---|---|---|
| Self-hosters struggle with Docker/TLS/webhook networking setup, hurting adoption | 2 | 2 | 4 | Polling fallback for all Graph connectors (no public endpoint required); clear quick-start docs; Caddy auto-TLS as a documented easy path |
| Data loss from volume mismanagement (user deletes a Docker volume) | 2 | 3 | 6 | Document backup guidance explicitly (SQLite file copy + `sqlite3 .backup`, blob volume archive); Git remote itself is a secondary backup of all *published* content |
| No dedicated maintainer bandwidth to keep up with MarkItDown/Docling/Graph API changes | 2 | 2 | 4 | Pin dependency versions; CI dependency-update automation (Dependabot/Renovate) with required review before merge |

## 6. Top 3 Risks to Monitor Actively Post-Launch

1. **Scope creep (9)** — enforce the MVP boundary in sprint planning; any Graph/AI work
   proposed before MVP ships should require explicit re-prioritization discussion.
2. **Data loss from volume mismanagement (6)** and **credential leakage (6)** — both
   stem from self-hosted/operational maturity; prioritize clear backup and secrets
   documentation in the Phase 6 release checklist ([MVP Roadmap](./10-mvp-roadmap.md)).
3. **Admin-consent friction for Teams/Planner connectors (6)** — validate the
   OneDrive/SharePoint-first connector ordering with early adopters before investing in
   higher-consent-friction connectors.
