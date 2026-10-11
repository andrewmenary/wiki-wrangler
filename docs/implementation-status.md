# Implementation Status

This checklist tracks implementation against the [MVP Roadmap](./10-mvp-roadmap.md).
It reflects the current repository state; checked items have working code or verified
configuration, while partial items are intentionally called out in the notes.

## Publishing Design Decisions

- Category paths are relative to a repository's curated root; parent categories define
  the canonical nested path.
- Category names are human-friendly labels. Machine path segments use a fixed lowercase
  hyphenated slug convention, with a generated suggestion and validated override.
- Repository roots default to `raw/` and `curated/` but are configurable per repository.
- Category assignment and repository destination are separate. An item has one category
  and one MVP publication destination; re-importing creates a separate item for another
  repository.
- Future enhancement: clone an existing item while preserving its source relationship,
  then independently edit its category and publication destination.
- MVP publishing identity: use an existing GitHub account through a repository-scoped
  credential reference; do not create a separate paid bot account.
- Git commits identify the publishing service account, while the actual approver remains
  attributed through publication and audit metadata.
- Git commit name and email are supplied through deployment environment configuration;
  no publishing email is stored in source code.
- Public-repository publishing is a separate security boundary: repositories and items
  will need visibility/classification controls, public publishing must be explicit, raw
  binaries and private source URLs must be excluded, and private repositories remain
  the safe default until those controls are implemented.
- Published records retain the resolved raw and curated paths used at publication time.

## Phase 0 - Foundations

- [ ] Complete repository scaffold from the target structure
  - [x] Basic backend package and test layout
  - [x] Web frontend login screen
  - [x] Worker package (Redis-backed publish queue, async execution, and bounded retries)
- [ ] Docker Compose foundation
  - [x] `web` service
  - [x] `api` service
  - [x] `worker` service
  - [x] `redis` service with persistent AOF volume
  - [x] Descriptive Compose project, image, and volume names
  - [x] API capture storage mapped into the persistent named volume
- [ ] SQLite schema migrations with Alembic
  - [x] SQLite database initialization
  - [ ] Alembic migration history
- [ ] Local authentication
  - [x] Admin registration endpoint
  - [x] Login endpoint
  - [x] Session cookie
  - [x] Login screen
  - [x] Session protection for item and category APIs
- [ ] CI pipeline
  - [x] Lint workflow configured and passing on GitHub
  - [x] Unit-test workflow configured and passing on GitHub
  - [x] Docker image build workflow configured and passing on GitHub

## Phase 1 - Core Capture and Conversion

- [x] File upload endpoint
  - [x] Supported extension validation
  - [x] Raw attachment storage
  - [x] Upload size limit
- [x] URL submission endpoint
  - [x] HTTP/HTTPS validation
  - [x] Basic HTML-to-Markdown structure extraction
  - [x] Content-type-aware PDF/Office preservation for deferred conversion
  - [x] Raw HTML attachment storage
  - [x] Response size limit
- [ ] Production conversion pipeline
  - [x] Built-in Markdown, plain-text, and CSV conversion
  - [x] MarkItDown integration for Office and PDF formats
  - [ ] Pandoc cleanup pass
  - [ ] Docling PDF/OCR path
  - [ ] Async conversion worker
- [x] Conversion failure state for unsupported built-in formats
- [x] Basic Inbox UI

## Phase 2 - Review and Approval

- [x] Review API
- [x] Review screen
- [x] Editable Markdown field
- [x] Vite frontend build with GitHub-flavored Markdown rendering and sanitization
- [x] Contextual help popovers for tags and category path fields
- [x] Summary and tags metadata fields
- [x] Status transition API
- [x] Domain-level status transition rules
- [x] Category CRUD and hierarchy API with validated slugs and derived paths
- [x] Category management Settings UI with generated slugs and parent-aware path segments

## Phase 3 - Git Publishing

- [ ] Repository configuration
  - [x] Admin API for repository targets, roots, and default selection
  - [x] Repository Settings UI
  - [x] Repository visibility and raw-source publishing policy controls
- [ ] Publish worker
  - [x] Tested Git worktree publisher core for raw/curated writes and idempotent commits
  - [x] Clone/update/push orchestration core with branch-aware integration coverage
  - [x] Git installed and persistent publish workspace configured in Compose
  - [x] Synchronous approved-item publish API boundary
  - [x] End-to-end API publish test against a local bare Git remote
  - [x] Failed publish leaves the approved item retryable
- [ ] Raw and curated Git paths
  - [x] Approved-item publication path preview API
  - [x] Curated front matter links back to source and raw path
  - [x] Public publication redacts private source URLs and raw paths
  - [x] Item publication visibility control in review
  - [x] Explicit confirmation required before public publication
- [ ] Publication records and commit links
  - [x] Publication and audit schema foundation
  - [x] Publish API persists commit and resolved path metadata
  - [x] Approved review exposes Publish to Git and commit feedback
  - [x] Publication history API and published-item read-only review state
  - [x] GitHub commit URL exposed and rendered as a View commit link
- [ ] Audit log
  - [x] Authenticated item edit and approval events recorded
  - [x] Administrator audit feed API and workspace viewer

## Later Phases

- [ ] Browser extension capture
- [ ] Microsoft Entra ID authentication
- [ ] GitHub OAuth authentication
- [ ] Multi-user roles and authorization
  - [x] Admin user listing, role promotion/demotion, and last-admin protection
  - [x] Admin user enable/disable controls with last-admin protection
- [ ] Release hardening and installation documentation

## Verification

- [x] Backend unit/API tests pass
- [x] Editor diagnostics clear for touched Python files
- [x] Docker Compose naming verified in configuration
- [x] CI validates the same checks automatically on GitHub
- [x] Browser smoke test through Compose and Playwright tooling
  - [x] Login and registration mode behavior
  - [x] Display Name hidden during sign-in
  - [x] Registration transitions to the Inbox
  - [x] Inbox loads captures and categories
  - [x] Committed Playwright test verifies session restoration after refresh
  - [x] Committed Playwright test verifies sign-out persists after refresh
  - [x] Committed Playwright test verifies invalid credentials and returning login
- [ ] Repeat browser smoke test after future UI changes
- [x] Add committed automated Playwright test suite
- [x] Configure Playwright suite in CI
- [x] Committed Playwright test verifies category create/list/edit/delete,
      duplicate-path errors, and edit persistence after refresh
- [x] Committed Playwright test verifies UI upload and conversion, review metadata,
  title editing, category assignment, and approval
- [x] Committed Playwright test verifies source filename and generated Markdown preview
- [x] Committed Playwright test verifies expandable original source preview
- [x] Approved review shows the resolved repository publication destination when configured
- [x] Committed Playwright test verifies GFM tables and task lists in Markdown Preview
- [x] Committed Playwright test verifies the authenticated wide workspace replaces the login branding
- [x] Committed Playwright test verifies Inbox capture discard with history preserved
- [x] Isolate Playwright test data using a disposable Compose stack on port 8081