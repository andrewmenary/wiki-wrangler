# Product Requirements Document (PRD) — Wiki Wrangler

## 1. Summary

Wiki Wrangler is a self-hosted, Docker-deployable staging and curation platform that
collects content from heterogeneous sources (Microsoft 365, files, web pages, and future
feeds), normalizes it to Markdown, and guides a human reviewer through approving and
publishing that content into a Git-based repository that serves as the corpus for an
LLM-powered wiki (e.g. retrieval-augmented generation / AI search over documentation).

Wiki Wrangler is not itself the wiki or the LLM. It is the **ingestion, curation, and
publishing layer** that sits in front of a Git repository.

## 2. Problem Statement

Teams want an LLM-searchable knowledge base, but building one requires tedious manual
work: exporting content from various tools, converting it to Markdown, organizing it into
folders, cleaning up formatting, tracking where it came from, and committing it to Git.
This friction means valuable knowledge (meeting notes, chats, documents, web research)
never makes it into the wiki.

## 3. Target User

A technical professional (e.g. engineer, IT admin, team lead) who:

- Already uses Microsoft 365 (Outlook, Teams, SharePoint/OneDrive, Planner).
- Maintains or wants to maintain a Git-backed knowledge base consumed by an LLM
  (e.g. via embeddings/RAG or a static-site wiki generator).
- Wants a low-friction "drop it in, review it, publish it" workflow rather than manual
  file wrangling.
- Is comfortable self-hosting a small Docker Compose stack.

## 4. Goals

### 4.1 Primary Goal

Reduce "capture → review → approve → publish" to a few clicks per item, regardless of
source format.

### 4.2 Secondary Goals

- Preserve source attribution and provenance for every published article.
- Maintain full version history via Git.
- Support Git-native workflows (branches, PRs, commits) so the wiki repo remains a
  normal, auditable Git repository usable outside of Wiki Wrangler.
- Lay groundwork for AI-assisted enrichment (metadata, categorization, de-duplication)
  without requiring it for MVP.
- Remain self-hostable, with no mandatory external SaaS dependency (cloud AI/Graph
  integrations are optional and configurable).
- Be deployable with a single `docker compose up`.

### 4.3 Non-Goals (for MVP)

- Replacing the LLM/wiki front-end itself (search UI, chat UI, embeddings pipeline).
- Real-time collaborative editing of Markdown (single-editor review is sufficient).
- Full enterprise DLP/compliance tooling.
- Automatic unattended publishing without human review (approval is always required
  unless explicitly configured otherwise in a later phase).

## 5. Core Concept

Wiki Wrangler behaves like an **inbox for knowledge**:

1. **Capture** — content arrives from a source connector or manual upload/URL/browser
   extension submission.
2. **Normalize** — the content is converted to Markdown, cleaned, and metadata is
   extracted (title, source, author, captured date, suggested tags).
3. **Review** — the user sees the original source, the generated Markdown, and an
   editable Markdown draft, side by side.
4. **Approve** — the user accepts (optionally after edits) and assigns final
   categorization/metadata.
5. **Publish** — Wiki Wrangler commits the Markdown (and any extracted assets) to the
   target Git repository under a well-defined path convention, with a meaningful commit
   message.

## 6. Functional Requirements

### 6.1 Source Ingestion

| ID | Requirement | Priority |
|----|-------------|----------|
| F1 | Users can upload files (DOCX, PDF, XLSX, PPTX, TXT, CSV, Markdown) directly through the web UI. | MVP |
| F2 | Users can submit a URL; the backend fetches and converts the page to Markdown. | MVP |
| F3 | A companion browser extension can submit the current page's URL, title, and rendered HTML directly to the inbox. | MVP |
| F4 | The system can connect to Microsoft Graph to ingest Outlook emails. | Post-MVP (Phase 2) |
| F5 | The system can ingest Teams chats and channel messages via Graph. | Post-MVP (Phase 2) |
| F6 | The system can ingest meeting transcripts via Graph. | Post-MVP (Phase 2) |
| F7 | The system can ingest Planner tasks via Graph. | Post-MVP (Phase 3) |
| F8 | The system can ingest OneDrive/SharePoint documents via Graph (webhook or polling). | Post-MVP (Phase 2) |
| F9 | The system can ingest GitHub Issues/Discussions and RSS feeds. | Post-MVP (Phase 3) |

### 6.2 Normalization

| ID | Requirement | Priority |
|----|-------------|----------|
| F10 | Office documents (DOCX/XLSX/PPTX) are converted to Markdown using MarkItDown. | MVP |
| F11 | PDFs are converted using Docling when table/figure/OCR fidelity is required, falling back to MarkItDown for simple text PDFs. | MVP |
| F12 | HTML/web pages are converted to Markdown with a readability-style extraction pass before conversion. | MVP |
| F13 | Pandoc is available as a secondary/cleanup conversion & reformatting engine (e.g. Markdown dialect normalization, TOC generation). | MVP |
| F14 | Conversion failures are captured as inbox items in an "error" state with the raw source preserved, never silently dropped. | MVP |
| F15 | Extracted metadata (title, author, captured date, source type, source URL/id) is auto-populated into the item's front matter. | MVP |

### 6.3 Review & Curation

| ID | Requirement | Priority |
|----|-------------|----------|
| F16 | Inbox view lists all captured items with status, source type, and capture date. | MVP |
| F17 | Review screen shows original source (or a link/preview to it), generated Markdown preview, and an editable Markdown draft. | MVP |
| F18 | Users can edit title, summary, tags, and target category/folder before approval. | MVP |
| F19 | Users can reject/archive an item without publishing. | MVP |
| F20 | Content moves through statuses: Inbox → Draft → Review → Approved → Published → Archived. | MVP |
| F21 | AI-assisted metadata suggestion (title/summary/tags) is available as an optional, explicitly-triggered action. | Post-MVP |
| F22 | AI-assisted categorization suggestions based on existing repo structure. | Post-MVP |
| F23 | Duplicate-content detection against existing curated articles. | Post-MVP |
| F24 | Related-document suggestions. | Post-MVP |

### 6.4 Publishing & Git Integration

| ID | Requirement | Priority |
|----|-------------|----------|
| F25 | Approved items are committed to a configured Git repository under configurable raw and curated roots (defaulting to `raw/<source>/...` and `curated/<category>/...`) with the original and reviewed content linked. | MVP |
| F26 | Commit messages are auto-generated from title/source/category and are human-meaningful (e.g. "Add Teams discussion on registration workflow"). | MVP |
| F27 | Publishing supports direct-commit-to-branch and commit-via-pull-request modes, configurable per repository. | MVP (direct commit); PR mode Post-MVP |
| F28 | Traceability links are preserved between curated Markdown and its raw source (front matter reference + raw file path). | MVP |
| F29 | Git push uses a configured credential (PAT, GitHub App, or SSH key) scoped to the target repo. | MVP |

### 6.5 Platform

| ID | Requirement | Priority |
|----|-------------|----------|
| F30 | Runs via Docker Compose on Windows and Linux hosts. | MVP |
| F31 | Supports local username/password authentication. | MVP |
| F32 | Supports Microsoft Entra ID (OIDC) authentication. | MVP |
| F33 | Supports GitHub OAuth authentication (useful since GitHub is also the publish target). | MVP |
| F34 | Multi-user support with basic roles (Admin, Curator). | MVP |
| F35 | Audit log of who approved/published what, and when. | MVP |

## 7. Non-Functional Requirements

- **Self-hosted & offline-capable**: all MVP conversion tooling (MarkItDown, Pandoc,
  Docling) runs locally in containers; no mandatory outbound calls except to the
  configured Git remote and, optionally, Microsoft Graph/AI providers.
- **Data durability**: inbox/metadata state persisted in SQLite (file-backed volume);
  published content durability is delegated to Git itself.
- **Security**: secrets (Graph app credentials, Git tokens, AI API keys) stored
  encrypted at rest; never logged.
- **Performance**: a typical document (<20 pages or <5MB) should convert and appear in
  the inbox within 30 seconds.
- **Extensibility**: new source connectors and new converters should be addable without
  changing the core domain model (see [Domain Model](./03-domain-model.md) and
  [Architecture](./04-architecture.md)).
- **Observability**: structured logs and basic health/metrics endpoints for each
  backend service.

## 8. Success Metrics

- Time from "content exists" to "content published to wiki" for a typical item: under
  5 minutes of active user time.
- % of captured items that reach "Published" (vs. abandoned in inbox) — target >70%
  after 30 days of use.
- Zero silent data loss: every captured item is visible in some status at all times.

## 9. Assumptions & Constraints

- The target Git repository already exists (or can be initialized) and is reachable
  from the Wiki Wrangler host (network access to GitHub, GitLab, or self-hosted Git).
- The "LLM wiki" that consumes the repository is out of scope; Wiki Wrangler only needs
  to produce well-structured Markdown + front matter that such a system can ingest.
- Microsoft Graph access requires the user (or their tenant admin) to register an Entra
  ID application with the necessary delegated/application permissions.

## 10. Related Documents

- [User Stories](./02-user-stories.md)
- [Domain Model](./03-domain-model.md)
- [Architecture](./04-architecture.md)
- [Database Schema](./05-database-schema.md)
- [Docker Architecture](./06-docker-architecture.md)
- [Microsoft Graph Integration](./07-ms-graph-integration.md)
- [Edge Extension Architecture](./08-edge-extension-architecture.md)
- [Security Model](./09-security-model.md)
- [MVP Roadmap](./10-mvp-roadmap.md)
- [Post-MVP Roadmap](./11-post-mvp-roadmap.md)
- [Repository Structure](./12-repo-structure.md)
- [Technology Stack](./13-tech-stack.md)
- [Sequence Diagrams](./14-sequence-diagrams.md)
- [Risk Analysis](./15-risk-analysis.md)
