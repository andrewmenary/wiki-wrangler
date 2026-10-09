# Implementation Status

This checklist tracks implementation against the [MVP Roadmap](./10-mvp-roadmap.md).
It reflects the current repository state; checked items have working code or verified
configuration, while partial items are intentionally called out in the notes.

## Phase 0 - Foundations

- [ ] Complete repository scaffold from the target structure
  - [x] Basic backend package and test layout
  - [ ] Web frontend
  - [ ] Worker package
- [ ] Docker Compose foundation
  - [ ] `web` service
  - [x] `api` service
  - [ ] `worker` service
  - [ ] `redis` service
  - [x] Descriptive Compose project, image, and volume names
- [ ] SQLite schema migrations with Alembic
  - [x] SQLite database initialization
  - [ ] Alembic migration history
- [ ] Local authentication
  - [ ] Admin registration
  - [ ] Login
  - [ ] Session cookie
  - [ ] Login screen
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
  - [x] HTML title and readable-text extraction
  - [x] Raw HTML attachment storage
  - [x] Response size limit
- [ ] Production conversion pipeline
  - [x] Built-in Markdown and plain-text conversion
  - [ ] MarkItDown integration
  - [ ] Pandoc cleanup pass
  - [ ] Docling PDF/OCR path
  - [ ] Async conversion worker
- [x] Conversion failure state for unsupported built-in formats
- [ ] Basic Inbox UI

## Phase 2 - Review and Approval

- [ ] Review API
- [ ] Review screen
- [ ] Editable Markdown and metadata fields
- [ ] Status transition API
- [x] Domain-level status transition rules
- [ ] Category CRUD and hierarchy

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