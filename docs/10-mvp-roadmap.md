# MVP Roadmap

## Guiding Principle

Ship the shortest path to the core loop — **manual/web capture → convert → review →
approve → publish to Git** — before any Microsoft Graph connector or AI feature. This
proves the product's central value (frictionless curation) with the smallest possible
surface area, and every later source/feature plugs into the same pipeline.

## Phase 0 — Foundations (Sprint 0-1)

- Repository scaffold per [Repository Structure](./12-repo-structure.md).
- Docker Compose skeleton: `web`, `api`, `worker`, `redis` services running with
  placeholder health-check endpoints.
- SQLite schema migrations in place (Alembic) matching
  [Database Schema](./05-database-schema.md).
- Local-auth login working end-to-end (register admin, log in, session cookie).
- CI pipeline: lint + unit tests + Docker image build on PRs.

**Exit criteria:** `docker compose up` yields a working login screen backed by a real
database.

## Phase 1 — Core Capture & Conversion (Sprint 2-3)

- File upload endpoint (DOCX/PDF/XLSX/PPTX/TXT/CSV/MD) → `source_submissions` + `items`.
- URL submission endpoint → fetch + HTML extraction.
- Conversion Worker wired to MarkItDown (primary) and Pandoc (cleanup pass); Docling
  integrated for PDFs needing table/OCR fidelity.
- Conversion failure handling: item lands in `error` status with raw content intact.
- Basic Inbox UI: list items with status/source/date.

**Exit criteria:** Uploading each supported file type and a URL produces a readable
Markdown draft visible in the Inbox within the performance target in the
[PRD](./01-prd.md) §7.

## Phase 2 — Review & Approval (Sprint 4)

- Review screen: original source preview, generated Markdown, editable draft, metadata
  form (title/summary/tags/category).
- Status transitions implemented per the
  [Domain Model](./03-domain-model.md) state machine (Draft → Review → Approved /
  Archived).
- Category management (CRUD, simple hierarchy) in Settings.

**Exit criteria:** A curator can take an uploaded file from Inbox through to Approved
entirely in the UI, including edits.

## Phase 3 — Git Publishing (Sprint 5)

- Repository configuration (remote URL, branch, credential, publish mode=direct) in
  Settings.
- Publish Worker: clone/pull, write `raw/<source>/...` and `curated/<category>/...`
  files with front matter, commit with generated message, push.
- Publication record + traceability link shown in the UI (commit link).
- Audit log (capture/approve/publish events) viewable by Admins.

**Exit criteria:** Approving an item results in a real commit visible in the configured
GitHub repository, with the UI showing the commit link.

## Phase 4 — Browser Extension (Sprint 6)

- Device token pairing flow (Settings UI + extension Options page).
- Extension popup: capture current page → `/api/v1/capture` → Inbox.
- End-to-end test: install unpacked extension in Edge, capture a real page, confirm it
  reaches Review.

**Exit criteria:** A page can be captured from Edge and published to Git without ever
leaving the browser except to open the Wiki Wrangler review tab.

## Phase 5 — Auth Hardening & Multi-User (Sprint 7)

- Microsoft Entra ID OIDC login.
- GitHub OAuth login.
- Roles (Admin/Curator) enforced across all mutating endpoints.
- Rate limiting + lockout on local auth.

**Exit criteria:** All three auth methods usable; role checks verified with tests for
every mutating route.

## Phase 6 — Polish & Release (Sprint 8)

- Error states, retry actions, and empty states across the UI.
- Health/metrics endpoints, structured logging finalized.
- Install documentation (Docker Compose quick start, `.env.example`, reverse-proxy/TLS
  guidance).
- Tag `v1.0.0`, publish images to GHCR.

**Exit criteria:** A new user can follow the README/quick-start to a working instance
in under 15 minutes, with no manual DB setup steps.

## MVP Scope Boundary (explicit non-goals)

- No Microsoft Graph connectors (Outlook/Teams/Planner/OneDrive/SharePoint).
- No AI-assisted metadata/categorization/duplicate/relationship features.
- No pull-request publish mode (direct-commit only).
- No GitHub Issues/Discussions or RSS connectors.

These are all deliberately deferred to [Post-MVP Roadmap](./11-post-mvp-roadmap.md) so
MVP stays focused on proving the core inbox → publish loop.
