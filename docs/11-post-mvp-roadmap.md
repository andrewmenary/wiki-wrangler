# Post-MVP Roadmap

Phases below assume the MVP in [MVP Roadmap](./10-mvp-roadmap.md) is complete and
deployed. Ordering reflects value vs. implementation complexity, not calendar
commitment.

## Phase 7 — Pull-Request Publish Mode

- `publish_mode = pull_request` support in the Publish Worker: create a branch per
  item (or batch), open a PR via the GitHub API, link the PR back to the `Publication`
  record.
- UI surfaces PR status (open/merged/closed) and lets the curator re-trigger on
  merge-conflict.
- GitLab merge-request equivalent, if GitLab remotes are supported (see
  [Technology Stack](./13-tech-stack.md) for Git-host abstraction).

## Phase 8 — First Microsoft Graph Connector: OneDrive/SharePoint

- Implement per [Microsoft Graph Integration](./07-ms-graph-integration.md) §8 (highest
  leverage, reuses existing file pipeline).
- Graph webhook subscription + renewal job; polling fallback.
- Settings UI for connecting a OneDrive/SharePoint folder to watch.

## Phase 9 — Outlook Mail Connector

- Delta-query based mail folder capture.
- HTML body → Markdown via existing conversion path; inline images as attachments.
- Per-folder enable/disable and "capture only flagged/categorized emails" filter
  option, to avoid inbox flooding.

## Phase 10 — Teams Chat & Channel Connector

- Thread-flattening formatter for chats and channel conversations.
- Admin-consent flow surfaced clearly in Settings (channel messages require tenant
  admin approval).

## Phase 11 — AI-Assisted Curation

- Pluggable AI Service abstraction (local model via Ollama, or hosted API),
  configurable per deployment.
- Title/summary/tag suggestion button on the Review screen (explicit trigger, not
  automatic, to control cost and avoid surprising users).
- Category suggestion based on existing repo taxonomy (embedding similarity against
  existing curated articles' categories).
- Duplicate detection: embedding-similarity search against already-curated content,
  surfaced as a warning banner in Review with a link to the likely duplicate.
- Related-document suggestions shown alongside the Review screen.

## Phase 12 — Meeting Transcripts & Planner

- Transcript capture triggered by calendar event webhook; VTT → Markdown speaker-
  labeled transcript.
- Planner task capture (title/notes/checklist → Markdown; due date/assignees → front
  matter).

## Phase 13 — Additional Connectors

- GitHub Issues/Discussions connector (useful for teams whose wiki repo lives
  alongside their code repo).
- RSS feed connector for external knowledge sources (vendor docs, blogs).

## Phase 14 — Knowledge Graph / Relationship Enhancements

- Explicit "related to" links between Items/curated articles, surfaced in front matter
  (`related:` list) so the downstream LLM/wiki can use them for retrieval context.
- Lightweight knowledge-graph view (nodes = articles, edges = related-to/tag overlap)
  as an exploratory UI, not a hard product requirement.

## Phase 15 — Scale-Out & Multi-Tenancy (if demand emerges)

- SQLite → PostgreSQL migration path (Alembic dialect swap, connection string change).
- Split worker pool into dedicated services per job type for independent scaling.
- Multi-repository / multi-team support with per-repository role scoping.

## Phase 16 — Compliance & Governance Extensions

- Configurable content-redaction rules (regex/NER) applied at normalization time.
- Data-retention/purge policy automation for archived items beyond a configured age.
- Per-category access control lists (building on the hierarchical `categories` model).

## Explicitly Out of Scope (even long-term)

- Wiki Wrangler will not become the LLM/search/chat front-end itself — it remains a
  curation/publishing layer feeding a separate wiki/RAG system, per the
  [PRD](./01-prd.md) non-goals.
