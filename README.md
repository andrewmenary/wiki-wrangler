# Wiki Wrangler

<p align="center">
   <img src="web/logo.png" alt="Wiki Wrangler logo" width="280">
</p>

Turn scattered web content into durable, searchable knowledge.

Wiki Wrangler is a self-hosted curation workspace for capturing useful material,
cleaning it into Markdown, reviewing it with context, and publishing it to a Git-backed
LLM wiki. Every published note keeps its provenance, metadata, approval history, and
commit link.

## Why It Exists

Important knowledge is often trapped in pages, documents, and announcements that are
hard to revisit. Wiki Wrangler gives that material a deliberate path:

```text
capture -> convert -> review -> approve -> publish
```

The result is a curated Markdown repository that both people and downstream LLM
workflows can use.

## What It Does

- Captures public URLs, uploaded documents, and content pasted from authenticated pages
- Converts HTML, Markdown, text, CSV, PDF, DOCX, PPTX, and XLSX content into Markdown
- Preserves headings, lists, links, emphasis, summaries, tags, and source references
- Provides a review workspace for editing title, summary, tags, category, visibility, and Markdown
- Requires approval before publication
- Publishes curated Markdown and optional raw attachments to Git
- Adds YAML front matter for reliable LLM ingestion:

```yaml
---
title: "Example note"
summary: "A concise description"
tags: ["operations", "onboarding"]
category: "department/operations"
visibility: "private"
source: "https://example.com/page"
raw_published: false
---
```

- Records publication commits, audit events, job status, retries, and failures
- Runs conversion and publication work outside the API request path
- Keeps SQLite, captured files, Git workspaces, and Redis data in persistent volumes

## Quick Start

### Prerequisites

- Docker Desktop with Docker Compose
- A GitHub repository for the curated wiki, such as `wiki-inbox`
- A fine-grained GitHub PAT with access to that repository

For the GitHub PAT, grant:

- Repository access: only the target wiki repository
- Contents: **Read and write**
- Metadata: **Read-only**

No Issues, Actions, Pages, Administration, or Webhooks permissions are required for
the current direct-commit workflow.

### Configure Git Publishing

Set these values in the PowerShell session where you will start Compose:

```powershell
$env:WIKI_WRANGLER_GIT_TOKEN = "github_pat_..."
$env:WIKI_WRANGLER_GIT_AUTHOR_NAME = "Wiki Wrangler"
$env:WIKI_WRANGLER_GIT_AUTHOR_EMAIL = "your-github-noreply-address@example.com"
```

The token is passed to Git through an environment-only authorization header. It is not
stored in SQLite, the repository settings, or the published wiki. Never commit a PAT
or a `.env` file containing one.

### Start the Application

From the repository root:

```powershell
docker compose -f deploy/docker-compose.yml up --build
```

Open [http://localhost:8080](http://localhost:8080).

The stack includes:

- `web`: the browser application
- `api`: authentication, capture, review, and publication APIs
- `worker`: queued Git publication worker
- `conversion-worker`: queued document conversion worker
- `redis`: publication queue and persistent AOF data

The API health endpoint is available at [http://localhost:8080/health](http://localhost:8080/health).

### First-Time Setup

1. Select **Create an account**.
2. Register the first user. The first account becomes an administrator.
3. Open **Manage repositories**.
4. Add the GitHub repository:
   - Remote URL: `https://github.com/<account>/wiki-inbox.git`
   - Default branch: `main`
   - Credential reference: a label such as `github-wiki-inbox`
   - Publish mode: **Direct commit**
   - Curated root: `curated`
   - Visibility: **Private** unless you deliberately want public content
5. Create one or more categories.

The credential reference is currently a safe label for the repository configuration.
Actual Git authentication comes from `WIKI_WRANGLER_GIT_TOKEN`.

## Your First Knowledge Note

### Public URL

Paste a public URL into **Capture a web page** and select **Add to inbox**. Wiki
Wrangler fetches the page from the server and creates a Markdown draft.

### Authenticated or Restricted Page

The server cannot use your browser cookies or SSO session. For a page that requires
your login:

1. Open the page in your authenticated browser.
2. Copy the useful article content.
3. Use **Capture copied content** in Wiki Wrangler.
4. Include the original page URL as the optional source URL.

Rich clipboard HTML is converted into Markdown, including headings, links, lists, and
emphasis. The converter also handles common malformed formatting from rich web pages.

### Review and Publish

1. Open the new item from the Inbox.
2. Review generated Markdown and the editable final draft.
3. Set the title, summary, tags, category, and visibility.
4. Save changes.
5. Select **Approve**.
6. Select **Publish to Git**.
7. Watch the publication status and open the resulting commit link.

For private repositories, source URLs and raw paths may be included when appropriate.
For public repositories, private source details and raw paths are redacted and explicit
confirmation is required.

## Data and Operations

Normal Compose uses named volumes:

- `wiki-wrangler-data`: SQLite database, captured files, and Git workspaces
- `wiki-wrangler-redis`: Redis AOF queue data

Stop the stack without deleting data:

```powershell
docker compose -f deploy/docker-compose.yml down
```

Start it again without rebuilding:

```powershell
docker compose -f deploy/docker-compose.yml up -d
```

Use `down -v` only when you intentionally want to delete the database, captured files,
publish workspaces, and Redis data. Back up important data before doing so.

Useful diagnostics:

```powershell
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f api
docker compose -f deploy/docker-compose.yml logs -f worker
docker compose -f deploy/docker-compose.yml logs -f conversion-worker
```

When a queued publication fails, the actual Git error is stored in the job status and
shown in the administrator audit log. A failed item remains approved and can be
published again after the configuration problem is corrected.

## Local Development

Install the backend and development dependencies:

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m pytest
ruff check app tests
```

Run the API locally:

```powershell
python -m uvicorn app.main:app --reload
```

The local API is available at [http://localhost:8000](http://localhost:8000).

Build the frontend:

```powershell
cd ..
npm ci
npm run build
```

## Browser Tests

The browser suite uses an isolated Docker stack on port 8081. Its database and files
are temporary and separate from the normal application volumes.

```powershell
docker compose -f deploy/docker-compose.test.yml up -d --build --wait
npm run test:ui
docker compose -f deploy/docker-compose.test.yml down
```

Install browser dependencies when needed:

```powershell
npm ci
npx playwright install chromium
```

## Architecture and Documentation

The detailed product and architecture documentation is in [docs/](docs/). Start with:

- [Implementation status](docs/implementation-status.md)
- [Product requirements](docs/01-prd.md)
- [Architecture](docs/04-architecture.md)
- [MVP roadmap](docs/10-mvp-roadmap.md)

## Current Boundaries

Wiki Wrangler is a strong working MVP, not yet a fully hardened multi-user service.
The current boundaries are:

- Authenticated webpages require copy-and-paste capture; browser-extension capture is future work.
- Local authentication is implemented; enterprise SSO and GitHub OAuth are future work.
- Direct Git commits are supported; pull-request publishing is not yet implemented.
- SQLite initialization is working; a full Alembic migration history is future work.
- AI enrichment, Microsoft Graph connectors, and automated categorization are intentionally out of scope.
