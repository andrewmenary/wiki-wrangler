# Security Model

## 1. Threat Model Summary

Wiki Wrangler handles potentially sensitive organizational content (emails, chats,
documents) and holds credentials for Git remotes and Microsoft Graph. The primary
assets to protect are:

1. Captured content at rest (raw + curated, in SQLite and blob storage).
2. Credentials: Git push credentials, Graph app secrets/tokens, local user password
   hashes, AI provider API keys.
3. Integrity of what gets published — an attacker should not be able to get arbitrary
   content committed to the wiki repo without going through review/approval.

Primary actors: authenticated curators/admins (trusted but should be least-privileged),
external attackers (network-facing API + webhook endpoint + browser extension
endpoint), and a compromised dependency/container (supply-chain risk given multiple
third-party conversion tools).

## 2. Authentication

Three supported methods, selectable per deployment or combinable:

| Method | Use case | Mechanism |
|---|---|---|
| Local | Small/offline deployments | Username + password, Argon2id hashing, stored in `users.password_hash` |
| Microsoft Entra ID | Organizations already on M365 | OIDC Authorization Code + PKCE; ID token validated, `oid`/`sub` mapped to `users.external_id` |
| GitHub OAuth | Teams centered on GitHub | OAuth2 Authorization Code flow; useful since GitHub is also commonly the publish target |

- Session management: short-lived signed JWT or opaque session cookie
  (`HttpOnly`, `Secure`, `SameSite=Lax`) issued by the API after successful auth;
  refresh handled server-side so the SPA never directly holds Graph/GitHub refresh
  tokens.
- Browser extension uses a separate, narrowly-scoped **device token** mechanism (see
  [Edge Extension Architecture](./08-edge-extension-architecture.md) §5), never the
  user's primary session credential.
- Brute-force protection on local auth: rate limiting + exponential lockout per
  account/IP.

## 3. Authorization

- Two roles for MVP: **Admin** (manage connectors, repositories, users, credentials)
  and **Curator** (capture, review, approve, publish content). Role is enforced at the
  API layer via a dependency/middleware checked on every route, not just hidden in the
  UI.
- All mutating endpoints validate the authenticated principal owns or is permitted to
  act on the target resource (e.g. a Curator can approve any item by default in MVP;
  per-category ownership/ACLs are a Post-MVP extension point already supported by the
  `categories` table's hierarchical structure).
- Device tokens are scoped (`capture:write` only) so a leaked extension token cannot
  reach admin or publish endpoints.

## 4. Secrets Management

- No secret value (Graph client secret, Git PAT/SSH key, AI API key, OAuth client
  secret) is ever stored in the SQLite database or committed to the wiki repository.
- MVP/self-hosted default: secrets are supplied via environment variables / Docker
  secrets, referenced indirectly in the database by name (`credential_ref`), per the
  schema design in [Database Schema](./05-database-schema.md).
- Documented upgrade path: integrate HashiCorp Vault or cloud KMS-backed secret stores
  for larger deployments; the `credential_ref` indirection already supports swapping
  the backing resolver without a schema change.
- Secrets are redacted in all logs via a logging filter that masks known secret-shaped
  values and any field named like `*secret*`, `*token*`, `*password*`.

## 5. Transport & Network Security

- All client-facing traffic (web UI, browser extension, Graph webhook callback) is
  served over HTTPS; the bundled nginx/reverse-proxy container terminates TLS, with
  Let's Encrypt/ACME integration documented for self-hosters who expose the instance
  publicly (needed for Graph webhooks, see
  [Microsoft Graph Integration](./07-ms-graph-integration.md) §4).
- The `redis` and `worker` services are not exposed outside the Docker Compose
  network; only `web`/`api` publish host ports.
- CORS on the API is locked to the configured web origin and (for the capture
  endpoint only) the extension's origin pattern.

## 6. Data Protection

- SQLite file and blob volume are recommended to live on an encrypted-at-rest volume
  (host-level disk encryption, or a cloud provider's encrypted volume) — this is a
  deployment recommendation documented in the install guide rather than something the
  app can enforce itself.
- Raw captured content (`raw/`) and curated content are both written to the Git
  repository the user controls; Wiki Wrangler does not introduce an additional copy of
  published content beyond the repo and its own working volumes, limiting data
  sprawl.
- Attachments are served to the authenticated UI only through the API (never directly
  from the blob volume), so access control is enforced on every read.

## 7. Input/Content Safety

- Uploaded files are scanned for type/size limits before conversion (MIME sniffing in
  addition to trusting the declared content-type, max size config per connector).
- HTML captured from the browser extension or web pages is sanitized (e.g. via
  `bleach`/`nh3`) before storage and before any conversion step touches it, to reduce
  stored-XSS risk when the generated Markdown/HTML preview is later rendered in the
  review UI.
- Conversion tools (MarkItDown/Pandoc/Docling) run with no network access from inside
  their execution context where feasible, and with resource limits (CPU/time/memory)
  per job to blunt malicious-document denial-of-service attempts (e.g. zip bombs,
  pathological PDFs).
- Markdown preview rendering in the UI uses a sanitizing Markdown renderer (no raw
  HTML passthrough by default).

## 8. Publish-Path Integrity

- Only the Publish Worker holds Git push credentials; the API/web tier never touches
  Git credentials directly.
- An `Item` can only be published from the `approved` status, which itself can only be
  reached via an explicit authenticated action logged as an `audit_event` — there is
  no code path that publishes unreviewed content.
- Pull-request publish mode (Post-MVP, see [PRD](./01-prd.md) F27) provides an
  additional human gate before content lands on the protected branch, recommended for
  higher-sensitivity repositories.

## 9. Audit & Accountability

- Every state-changing action (capture, edit, approve, reject, publish, connector/
  credential change, user/role change) is recorded in `audit_events` with actor, time,
  and a details payload — see [Database Schema](./05-database-schema.md).
- Audit log is read-only via the API (no update/delete endpoint) and is viewable by
  Admins in the Settings UI.

## 10. Dependency & Supply-Chain Security

- Backend/worker image pins exact versions of MarkItDown, Pandoc, Docling, and Python
  dependencies via a lockfile; Dependabot/Renovate configured for the repo.
- Container images are built from minimal base images and scanned in CI (e.g.
  `docker scout` or Trivy) before publishing to GHCR.

## 11. Compliance Considerations (out of scope for MVP, noted for future work)

- No built-in DLP classification; organizations with regulatory requirements (e.g.
  PII handling) should pair Wiki Wrangler with their existing M365 compliance
  policies, since Graph connectors inherit the underlying permission/consent model.
- A future enhancement could add configurable content redaction rules
  (regex/NER-based) applied during normalization, before content ever reaches the
  review inbox.
