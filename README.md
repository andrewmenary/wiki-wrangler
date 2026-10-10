# wiki-wrangler
A tool for staging/curating content for LLM wiki ingestion.

## Design Documentation

Full product/design documentation (PRD, user stories, domain model, architecture,
database schema, Docker architecture, Microsoft Graph integration, Edge extension
architecture, security model, MVP/post-MVP roadmaps, repo structure, tech stack,
sequence diagrams, and risk analysis) lives in [docs/](./docs). Start at
[docs/README.md](./docs/README.md).

## Implementation Status

Current implementation progress is tracked in
[docs/implementation-status.md](./docs/implementation-status.md).

The working application currently provides:

- Docker Compose web and API services with descriptive image and volume names
- Local account registration, login, logout, and session cookies
- A web Inbox with URL capture and recent-item listing
- HTML extraction into Markdown drafts with raw source preservation
- SQLite initialization and backend API tests

Run the backend locally:

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m pytest
python -m uvicorn app.main:app --reload
```

The local API is then available at `http://localhost:8000`.

Run the full web application with Docker Compose from the repository root:

```powershell
docker compose -f deploy/docker-compose.yml up --build
```

Once the containers are running, open `http://localhost:8080` in a browser. Select
**Create an account** for the first account, then sign in. The first registered
account receives the `admin` role.

From the Inbox, enter a public web page URL and select **Add to inbox**. Wiki
Wrangler fetches the page, extracts readable text, and displays the resulting draft.
The API health check is available through the web service at
`http://localhost:8080/health`; the API itself is also exposed at
`http://localhost:8000/health`.

To stop the application, press `Ctrl+C` in the Compose terminal. The SQLite database
and captured files remain in the `wiki-wrangler-data` Docker volume. Do not use
`docker compose down -v` unless you intend to delete that data.

