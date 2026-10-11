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

## Browser Tests

With Node.js installed, install the test dependencies from the repository root:

```powershell
npm ci
npx playwright install chromium
```

Run Playwright against the disposable test stack:

```powershell
docker compose -f deploy/docker-compose.test.yml up -d --build --wait
npm run test:ui
docker compose -f deploy/docker-compose.test.yml down
```

The test UI uses `http://127.0.0.1:8081`. Its database and attachments are stored in
temporary container memory, not the normal application's `wiki-wrangler-data` volume.
Stopping the test containers discards their data. The normal app on port 8080 can
remain running while browser tests run. Tests also run against this isolated stack
in GitHub Actions.

## Git Publishing Identity

Git publishing uses the account configured for the target repository. The commit
author identity is supplied at deployment time and is not stored in source code:

```powershell
$env:WIKI_WRANGLER_GIT_AUTHOR_NAME = "Wiki Wrangler"
$env:WIKI_WRANGLER_GIT_AUTHOR_EMAIL = "your-publishing-address@example.com"
docker compose -f deploy/docker-compose.yml up --build
```

The same values can be placed in a local `.env` file for Compose. Do not commit that
file or any Git credentials. The actual approver remains recorded by Wiki Wrangler's
audit and publication metadata.

For an HTTPS GitHub repository, set a fine-grained personal access token before
starting Compose:

```powershell
$env:WIKI_WRANGLER_GIT_TOKEN = "github_pat_..."
docker compose -f deploy/docker-compose.yml up --build
```

The token is passed to Git through an environment-only authorization header and is
not stored in SQLite or committed to the wiki. For permission-restricted web pages,
copy the content from your authenticated browser session and use **Capture copied
content** in the Inbox.

