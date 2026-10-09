# Suggested GitHub Repository Structure

This describes the **Wiki Wrangler application repository** (this repo). For the
structure of the *target* wiki repository that Wiki Wrangler publishes into, see
[PRD §"Repository Strategy"](./01-prd.md) — summarized again at the end of this
document for convenience.

## 1. Application Repository Layout

```
wiki-wrangler/
├── backend/
│   ├── app/
│   │   ├── api/                 # FastAPI routers (items, categories, auth, capture, admin)
│   │   ├── core/                # config, security, logging, dependency wiring
│   │   ├── domain/               # pure domain models/state machine (framework-agnostic)
│   │   ├── connectors/           # one module per source: web, file, outlook, teams, ...
│   │   │   ├── base.py           # Connector interface
│   │   │   ├── web.py
│   │   │   ├── file_upload.py
│   │   │   └── graph/
│   │   ├── converters/           # one module per tool: markitdown, pandoc, docling
│   │   │   ├── base.py           # Converter interface
│   │   │   ├── markitdown_converter.py
│   │   │   ├── pandoc_converter.py
│   │   │   └── docling_converter.py
│   │   ├── publishing/           # Git operations, commit message generation, PR creation
│   │   ├── ai/                   # AI service abstraction + providers (Post-MVP)
│   │   ├── db/                   # SQLAlchemy models, session management
│   │   ├── worker.py              # arq/Celery worker entrypoint & job definitions
│   │   └── main.py                # FastAPI app entrypoint
│   ├── alembic/                   # DB migrations
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/                 # Inbox, Review, Settings, Login
│   │   ├── components/
│   │   ├── api/                    # typed API client
│   │   └── state/                  # client state/query layer
│   ├── Dockerfile
│   └── package.json
├── extension/
│   ├── src/
│   │   ├── popup/
│   │   ├── background/
│   │   ├── content-script/
│   │   └── options/
│   ├── manifest.json
│   └── package.json
├── docs/                           # this design documentation
│   ├── 01-prd.md
│   ├── 02-user-stories.md
│   ├── ... (all deliverables)
│   └── README.md                   # index
├── deploy/
│   ├── docker-compose.yml
│   ├── docker-compose.prod.yml
│   ├── .env.example
│   └── nginx/
├── .github/
│   └── workflows/
│       ├── ci.yml                  # lint, test, build
│       └── release.yml             # build & push images to GHCR on tag
├── LICENSE
└── README.md
```

## 2. Rationale

- **`backend/app/connectors/` and `backend/app/converters/`** are structured as plural
  per-implementation modules behind a shared interface (`base.py`), directly mirroring
  the extensibility goal in [Architecture](./04-architecture.md) §6 — adding a new
  source or tool means adding one file + a registry entry, not touching core logic.
- **`backend/app/domain/`** isolates the lifecycle/state-machine logic (
  [Domain Model](./03-domain-model.md)) from FastAPI/SQLAlchemy specifics, keeping it
  unit-testable without spinning up the database or HTTP layer.
- **`extension/`** lives in the same monorepo as `frontend/` and `backend/` (rather
  than a separate repo) so API contract changes and extension updates are reviewed and
  released together, avoiding version-skew bugs between the API and the capture
  endpoint contract.
- **`deploy/`** centralizes everything an operator needs to run the stack, separate
  from application source, so `docker-compose.yml` can be updated independently of a
  backend/frontend release.
- A **monorepo** is recommended over multi-repo given the tight coupling between
  backend API contracts, the frontend client, and the extension's capture payload
  shape — a single PR can update all three atomically.

## 3. Branching & Release Strategy

- `main` is always deployable; protected, requires PR + passing CI.
- Feature branches named `feat/<short-desc>`, `fix/<short-desc>`.
- Semantic version tags (`v1.0.0`) trigger the release workflow that builds and
  publishes `backend` and `frontend` images to GHCR and packages the extension for
  store submission.

## 4. Target Wiki Repository Layout (for reference)

The repository Wiki Wrangler *publishes into* (separate from this app repo) follows:

```
<wiki-repo>/
├── raw/
│   ├── outlook/
│   ├── teams/
│   ├── web/
│   └── files/
└── curated/
    ├── processes/
    ├── projects/
    ├── reference/
    └── troubleshooting/
```

Each curated Markdown file's front matter includes a `source:` field pointing back to
its corresponding file under `raw/`, preserving traceability per the
[Domain Model](./03-domain-model.md) invariants. See
[PRD §"Repository Strategy"](./01-prd.md) for the full rationale.
