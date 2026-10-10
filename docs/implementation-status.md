# Implementation Status

This checklist tracks implementation against the [MVP Roadmap](./10-mvp-roadmap.md).
It reflects the current repository state; checked items have working code or verified
configuration, while partial items are intentionally called out in the notes.

## Phase 0 - Foundations

- [ ] Complete repository scaffold from the target structure
  - [x] Basic backend package and test layout
  - [x] Web frontend login screen
  - [ ] Worker package
- [ ] Docker Compose foundation
  - [x] `web` service
  - [x] `api` service
  - [ ] `worker` service
  - [ ] `redis` service
  - [x] Descriptive Compose project, image, and volume names
- [ ] SQLite schema migrations with Alembic
  - [x] SQLite database initialization
  - [ ] Alembic migration history
- [ ] Local authentication
  - [x] Admin registration endpoint
  - [x] Login endpoint
  - [x] Session cookie
  - [x] Login screen
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
  - [x] Raw HTML attachment storage
  - [x] Response size limit
- [ ] Production conversion pipeline
  - [x] Built-in Markdown and plain-text conversion
  - [ ] MarkItDown integration
  - [ ] Pandoc cleanup pass
  - [ ] Docling PDF/OCR path
  - [ ] Async conversion worker
- [x] Conversion failure state for unsupported built-in formats
- [x] Basic Inbox UI

## Phase 2 - Review and Approval

- [x] Review API
- [x] Review screen
- [x] Editable Markdown field
- [x] Summary and tags metadata fields
- [x] Status transition API
- [x] Domain-level status transition rules
- [x] Category CRUD and hierarchy API
- [ ] Category management Settings UI

## Phase 3 - Git Publishing

- [ ] Repository configuration
- [ ] Publish worker
- [ ] Raw and curated Git paths
- [ ] Publication records and commit links
- [ ] Audit log

## Later Phases

- [ ] Browser extension capture
- [ ] Microsoft Entra ID authentication
- [ ] GitHub OAuth authentication
- [ ] Multi-user roles and authorization
- [ ] Release hardening and installation documentation

## Verification

- [x] Backend unit/API tests pass
- [x] Editor diagnostics clear for touched Python files
- [x] Docker Compose naming verified in configuration
- [x] CI validates the same checks automatically on GitHub