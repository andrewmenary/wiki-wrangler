# Microsoft Graph Integration Strategy

## 1. Scope

Covers ingestion from Outlook, Teams (chats/channels/transcripts), Planner, OneDrive,
and SharePoint via Microsoft Graph. This is **Post-MVP (Phase 2/3)** functionality; the
strategy is specified now so the domain model and connector interface accommodate it
without rework.

## 2. App Registration & Permission Model

- A single multi-tenant-capable **Entra ID App Registration** is created for Wiki
  Wrangler (same app can also serve as the Entra ID login provider for the web UI,
  using separate scopes).
- Use **delegated permissions** (acting as the signed-in curator) as the default model,
  since content capture is inherently tied to a specific user's mailbox/Teams
  membership and keeps the permission footprint minimal and consent-friendly:
  - `Mail.Read` (Outlook)
  - `Chat.Read` (Teams chats)
  - `ChannelMessage.Read.All` (Teams channel messages; requires admin consent)
  - `OnlineMeetingTranscript.Read.All` (meeting transcripts; requires admin consent)
  - `Tasks.Read` (Planner)
  - `Files.Read.All` (OneDrive/SharePoint)
- **Application permissions** (app-only, no signed-in user) are offered as an
  admin-opt-in alternative for organization-wide SharePoint/OneDrive folder watching,
  since that use case is naturally tenant-wide rather than per-user.
- Tokens are acquired via **OAuth2 Authorization Code flow with PKCE** for delegated
  access (the same Entra login the user already performs for the web UI can incrementally
  request these additional scopes), and the **Client Credentials flow** for the
  application-permission connectors. Refresh tokens are stored encrypted (see
  [Security Model](./09-security-model.md)) and refreshed by the Connector Sync worker.

## 3. Per-Source Connector Design

All connectors implement the same interface used by file/web connectors:

```
Connector.list_new_items(cursor) -> (items: List[RawSubmission], next_cursor)
Connector.fetch_content(raw_submission) -> ConvertibleContent
```

| Source | Graph API | Sync mechanism | Notes |
|---|---|---|---|
| Outlook | `GET /me/mailFolders/{id}/messages/delta` | Delta query, polled every N minutes | User selects which folder(s) to watch in Settings; HTML body converted via MarkItDown/Pandoc; attachments captured as item `Attachment`s |
| Teams chat | `GET /chats/{id}/messages/delta` | Delta query | Thread flattened into a single Markdown doc with `**Author** (timestamp): message` formatting; reactions/mentions summarized, not rendered verbatim |
| Teams channel | `GET /teams/{id}/channels/{id}/messages/delta` | Delta query | Requires admin-consented `ChannelMessage.Read.All`; one Item per thread (root message + replies) |
| Meeting transcript | `GET /me/onlineMeetings/{id}/transcripts` | Triggered by calendar webhook (`Event` change notification) → fetch transcript once meeting ends | Transcript VTT converted to Markdown with speaker labels and timestamps |
| Planner | `GET /planner/plans/{id}/tasks` | Delta polling (Planner has limited delta support; fall back to full re-list + diff by `id`+`modified`) | Task title/notes/checklist become the Markdown body; due date/assignees become front matter |
| OneDrive / SharePoint | `GET /drives/{id}/root/delta` | **Preferred:** Graph **webhook subscriptions** (`/subscriptions`) for near-real-time change notification; falls back to delta-query polling where webhooks aren't reachable (e.g. no public endpoint) | Office files in the watched folder are captured as submissions and routed through MarkItDown/Docling like a manual upload |

## 4. Webhooks vs. Polling

- Where Wiki Wrangler is reachable on a public/reverse-proxied HTTPS endpoint, Graph
  **change notification webhooks** are preferred (lower latency, lower API quota
  usage). The `api` service exposes a `/webhooks/graph` endpoint that validates the
  Graph validation token handshake and enqueues a lightweight "something changed, go
  fetch delta" job — it never trusts webhook payload content directly, only treats it
  as a signal to re-poll via delta query (Graph's documented best practice).
- Where no public endpoint exists (fully offline/behind-NAT deployments), the
  Scheduler falls back to interval polling per connector (configurable, default 5–15
  minutes), using the stored `deltaLink`/cursor to avoid refetching unchanged data.
- Webhook subscriptions expire (max ~3 days for most resources) and must be renewed by
  a periodic job; this renewal job is part of the Connector Sync worker's
  responsibilities.

## 5. Idempotency & Deduplication

- Every Graph item has a stable `id` (message id, chat id + message id, task id,
  driveItem id). This is stored as `source_submissions.external_ref`, combined with
  `connector_id` in a unique constraint, so re-processing a delta page never creates
  duplicate `Item`s — an existing submission is updated in place (e.g. an edited Teams
  message updates `raw_metadata_json` and, if already published, flags the Item for
  re-review rather than silently republishing).

## 6. Content Handling Specifics

- **HTML email bodies**: sanitized, then converted via MarkItDown's HTML path (falling
  back to Pandoc for edge cases); inline images extracted as `Attachment`s and
  rewritten as relative Markdown image links.
- **Teams rich text**: Graph returns HTML-ish `body.content`; same HTML→Markdown path
  applies, with a thread-aware formatter for multi-message captures.
- **Transcripts**: Graph returns WebVTT; a small parser converts cues into a Markdown
  transcript with `HH:MM:SS — Speaker: text` lines, collapsing consecutive same-speaker
  cues for readability.

## 7. Rate Limiting & Resilience

- All Graph calls go through a shared client with exponential backoff honoring
  `Retry-After` headers (Graph throttling, HTTP 429).
- Batch requests (`$batch`) are used where multiple resources need fetching per sync
  cycle (e.g. message + attachments) to reduce round trips and quota consumption.
- Connector Sync job failures are logged as `audit_events` with action
  `connector.sync_failed` and surfaced in the Settings UI with last-error detail, so an
  expired consent/refresh token is immediately visible to the admin.

## 8. Minimal Viable Slice (first Graph connector to ship)

Recommended order given value vs. complexity:
1. **OneDrive/SharePoint folder watch** — reuses the existing file-conversion pipeline
   almost unchanged; highest leverage for least new code.
2. **Outlook mail folder capture** — second highest value, moderate HTML-conversion
   complexity.
3. **Teams chat/channel capture** — requires thread-flattening logic and (for channels)
   admin consent.
4. **Meeting transcripts** and **Planner** — lowest initial demand signal; deferred to
   Phase 3.
