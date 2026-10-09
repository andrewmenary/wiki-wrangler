# wiki-wrangler
A tool for staging/curating content for LLM wiki ingestion.

## Design Documentation

Full product/design documentation (PRD, user stories, domain model, architecture,
database schema, Docker architecture, Microsoft Graph integration, Edge extension
architecture, security model, MVP/post-MVP roadmaps, repo structure, tech stack,
sequence diagrams, and risk analysis) lives in [docs/](./docs). Start at
[docs/README.md](./docs/README.md).

## Implementation Status

The initial backend slice provides:

- FastAPI application with SQLite initialization
- `GET /health` database health check
- `POST /api/items` capture endpoint creating Inbox items
- Framework-independent item lifecycle rules
- Pytest coverage for health, capture, and lifecycle behavior

Run the backend locally:

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m pytest
python -m uvicorn app.main:app --reload
```

Or run the API with Docker Compose:

```powershell
docker compose -f deploy/docker-compose.yml up --build
```

