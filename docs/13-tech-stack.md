# Recommended Technology Stack

## 1. Backend

| Concern | Choice | Rationale |
|---|---|---|
| Web framework | **FastAPI** (Python 3.12) | Async-native, OpenAPI out of the box, matches the prompt's proposed stack, strong ecosystem overlap with MarkItDown/Docling (both Python libraries) |
| ORM / migrations | **SQLAlchemy 2.x + Alembic** | Keeps a clean migration path to PostgreSQL later without rewriting data access code |
| Job queue | **arq** (Redis-backed, asyncio-native) for MVP; **Celery** if richer scheduling/retry semantics are needed later | arq is lightweight and async, fitting FastAPI's async model better than Celery's sync worker model; Redis dependency is small and well understood |
| Document conversion | **MarkItDown** (primary), **Docling** (rich PDF/table/OCR), **Pandoc** (CLI, cleanup/reformatting pass) | Exactly the tools called out in the brief; routed by a converter-selection policy per [Architecture](./04-architecture.md) §3.6 |
| Web/HTML extraction | **trafilatura** or **readability-lxml** ahead of MarkItDown's HTML path | Strips nav/ads/boilerplate before conversion, improving Markdown quality from captured pages |
| Auth | **Authlib** (OIDC/OAuth2 client for Entra ID + GitHub), **Argon2** (local password hashing via `argon2-cffi`) | Well-maintained, framework-agnostic OIDC/OAuth client |
| Microsoft Graph client | **msgraph-sdk** (official Python SDK) or direct `httpx` calls against Graph REST | Official SDK reduces boilerplate for delta queries and batching |
| Git operations | **GitPython** or direct `git` CLI invocation from the Publish Worker; **PyGithub** for PR creation | GitPython is sufficient for clone/add/commit/push; CLI fallback for operations GitPython handles awkwardly (e.g. credential helpers) |
| AI/LLM access | Abstracted provider interface; default to **OpenAI-compatible HTTP client** usable against hosted APIs or local servers (Ollama/vLLM) | Keeps AI features optional and provider-agnostic, per [PRD](./01-prd.md) secondary goals |

## 2. Frontend

| Concern | Choice | Rationale |
|---|---|---|
| Framework | **React 18 + TypeScript** | Matches the prompt's proposed stack; large ecosystem for Markdown rendering/diff components |
| Build tool | **Vite** | Fast dev server, simple multi-target build (web app reuses config patterns with the extension build) |
| Data fetching/cache | **TanStack Query** | Clean handling of polling job status (conversion/publish progress) and optimistic UI for approve/reject actions |
| Markdown rendering | **react-markdown** + `remark-gfm`, sanitized | Matches the sanitized-rendering requirement in [Security Model](./09-security-model.md) §7 |
| Styling/components | **Tailwind CSS** + a headless component kit (e.g. Radix UI) | Fast to build a clean Inbox/Review/Settings UI without heavy design-system overhead |
| Diff view | **`diff-match-patch`**-based or `react-diff-viewer` | Used in Review screen to show generated vs. edited Markdown |

## 3. Browser Extension

| Concern | Choice | Rationale |
|---|---|---|
| Platform | **Manifest V3**, TypeScript | Runs on Edge and Chrome from one codebase, per [Edge Extension Architecture](./08-edge-extension-architecture.md) |
| Bundling | **Vite** with a web-extension plugin | Reuses frontend tooling conventions |

## 4. Data & Infrastructure

| Concern | Choice | Rationale |
|---|---|---|
| Database | **SQLite** (MVP) → **PostgreSQL** (scale-out path) | Per [Database Schema](./05-database-schema.md) §1 |
| Cache/queue broker | **Redis** | Backs `arq`; also usable as a short-TTL cache for Graph delta cursors |
| Object/blob storage | **Local Docker volume** (MVP) → pluggable **S3-compatible** backend (MinIO/AWS S3) for larger deployments | Keeps MVP dependency-free while leaving a clear extension point |
| Container runtime | **Docker / Docker Compose** | Explicit deployment requirement |
| Reverse proxy / TLS | **nginx** (bundled) or **Caddy** (simpler automatic TLS) as an alternative documented option | Caddy's automatic HTTPS is attractive for self-hosters exposing Graph webhooks publicly |

## 5. Tooling & Quality

| Concern | Choice | Rationale |
|---|---|---|
| Backend lint/format | **ruff**, **black**, **mypy** | Fast, widely adopted, single-tool lint+format with ruff |
| Backend tests | **pytest**, **pytest-asyncio**, **httpx**'s `ASGITransport` for API tests | Standard, async-friendly |
| Frontend lint/format | **ESLint**, **Prettier**, **TypeScript strict mode** | Standard |
| Frontend tests | **Vitest** + **React Testing Library**; **Playwright** for E2E (capture→review→publish happy path) | Playwright can also exercise the extension in a real browser context |
| CI | **GitHub Actions** | Matches GitHub-centric publish target; first-class Docker build/push support |
| Image scanning | **Trivy** (or Docker Scout) in CI | Supply-chain hygiene per [Security Model](./09-security-model.md) §10 |

## 6. Alternatives Considered

- **Node/NestJS backend instead of FastAPI** — rejected because MarkItDown and Docling
  are Python-native; a Python backend avoids cross-language subprocess overhead for the
  core conversion path.
- **Celery instead of arq** — kept as a documented fallback rather than default, since
  Celery's heavier operational footprint (separate beat scheduler, broader
  configuration surface) isn't justified until job volume/complexity grows beyond
  MVP needs.
- **Next.js instead of plain React+Vite** — rejected for MVP; Wiki Wrangler's UI is a
  pure authenticated SPA behind the API with no SEO/SSR requirement, so Vite's
  simplicity wins.
