# Sequence Diagrams for Major Workflows

## 1. Manual File Upload → Publish (Core Loop)

```mermaid
sequenceDiagram
    actor U as Curator
    participant W as Web UI
    participant A as API
    participant Q as Job Queue
    participant CW as Conversion Worker
    participant DB as SQLite
    participant PW as Publish Worker
    participant G as Git Repo

    U->>W: Upload DOCX
    W->>A: POST /items (multipart)
    A->>DB: insert source_submission + item(status=inbox)
    A->>Q: enqueue conversion job
    A-->>W: 201 {item_id}
    Q->>CW: deliver job
    CW->>CW: run MarkItDown
    CW->>DB: update item(markdown_generated, status=draft)
    U->>W: Open item in Review
    W->>A: GET /items/{id}
    A->>DB: read item
    A-->>W: item detail
    U->>W: Edit draft, set category/tags
    W->>A: PATCH /items/{id} (markdown_final, category, tags)
    A->>DB: update item(status=review, version+1)
    U->>W: Click Approve
    W->>A: POST /items/{id}/approve
    A->>DB: update item(status=approved)
    A->>Q: enqueue publish job
    Q->>PW: deliver job
    PW->>G: write raw/ + curated/ files, commit, push
    PW->>DB: insert publication(commit_sha), update item(status=published)
    A-->>W: (poll/SSE) status=published + commit link
    W-->>U: Show "Published" with commit link
```

## 2. URL / Browser Extension Capture

```mermaid
sequenceDiagram
    actor U as User
    participant Ext as Browser Extension
    participant A as API
    participant Q as Job Queue
    participant CW as Conversion Worker
    participant DB as SQLite

    U->>Ext: Click "Save to Wiki Wrangler"
    Ext->>Ext: read page HTML via content script
    Ext->>A: POST /api/v1/capture (Bearer device token)
    A->>A: validate device token scope = capture:write
    A->>DB: upsert source_submission (external_ref=sha256(url))
    A->>DB: insert item(status=inbox, source_type=web)
    A->>Q: enqueue conversion job
    A-->>Ext: 201 {item_id}
    Ext-->>U: "Saved" + deep link to item
    Q->>CW: deliver job
    CW->>CW: sanitize HTML, extract main content, MarkItDown/Pandoc
    CW->>DB: update item(markdown_generated, status=draft)
```

(Review/Approve/Publish continue exactly as in Diagram 1.)

## 3. Microsoft Graph Connector Sync (e.g. Outlook)

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant Q as Job Queue
    participant CS as Connector Sync Worker
    participant Graph as Microsoft Graph
    participant DB as SQLite
    participant CQ as Conversion Queue

    S->>Q: enqueue sync job (connector=outlook, every N min)
    Q->>CS: deliver job
    CS->>DB: read stored deltaLink/cursor
    CS->>Graph: GET /me/mailFolders/{id}/messages/delta?token=...
    Graph-->>CS: changed messages + new deltaLink
    loop for each new/changed message
        CS->>DB: upsert source_submission (external_ref=message.id)
        alt new submission
            CS->>DB: insert item(status=inbox, source_type=outlook)
            CS->>CQ: enqueue conversion job
        else existing, already published
            CS->>DB: flag item for re-review (content changed)
        end
    end
    CS->>DB: store new deltaLink
```

## 4. Graph Webhook-Triggered Sync (OneDrive/SharePoint)

```mermaid
sequenceDiagram
    participant Graph as Microsoft Graph
    participant A as API (/webhooks/graph)
    participant Q as Job Queue
    participant CS as Connector Sync Worker

    Graph->>A: POST /webhooks/graph (validationToken, on subscribe)
    A-->>Graph: 200 echo validationToken
    Note over Graph,A: Subscription active
    Graph->>A: POST /webhooks/graph (change notification, resourceData only)
    A->>A: verify clientState matches subscription
    A->>Q: enqueue "resync connector X" job (no payload trusted)
    Q->>CS: deliver job
    CS->>Graph: GET delta query for drive
    Graph-->>CS: changed driveItems + new deltaLink
    CS->>CS: create submissions/items, enqueue conversions (as in Diagram 3)
```

## 5. AI-Assisted Metadata Suggestion (Post-MVP)

```mermaid
sequenceDiagram
    actor U as Curator
    participant W as Web UI
    participant A as API
    participant Q as Job Queue
    participant AIW as AI Worker
    participant AI as AI Service (LLM)
    participant DB as SQLite

    U->>W: Click "Suggest metadata" on Review screen
    W->>A: POST /items/{id}/suggest-metadata
    A->>Q: enqueue AI enrichment job
    A-->>W: 202 Accepted (job queued)
    Q->>AIW: deliver job
    AIW->>DB: read item markdown_final
    AIW->>AI: prompt for title/summary/tags/category
    AI-->>AIW: suggestions
    AIW->>DB: store suggestions (not auto-applied)
    W->>A: GET /items/{id}/suggestions (poll)
    A-->>W: suggestions ready
    U->>W: Accept/edit/discard suggestions
    W->>A: PATCH /items/{id} (final values)
```

## 6. Rejected / Archived Item

```mermaid
sequenceDiagram
    actor U as Curator
    participant W as Web UI
    participant A as API
    participant DB as SQLite

    U->>W: Open item in Review
    U->>W: Click "Reject"
    W->>A: POST /items/{id}/reject
    A->>DB: update item(status=archived)
    A->>DB: insert audit_event(action=item.rejected)
    A-->>W: 200 OK
    W-->>U: Item removed from active Inbox view
```
