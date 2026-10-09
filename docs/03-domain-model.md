# Domain Model

## 1. Overview

Wiki Wrangler's domain centers on a single lifecycle entity, the **Item**, which
represents one piece of captured knowledge as it moves from raw capture to published
wiki content. Everything else (Source, Connector, Conversion, Attachment, Publication,
User, AuditEvent) supports that lifecycle.

## 2. Entity-Relationship Diagram

```mermaid
erDiagram
    USER ||--o{ ITEM : "captures/reviews"
    SOURCE_CONNECTOR ||--o{ SOURCE_SUBMISSION : produces
    SOURCE_SUBMISSION ||--|| ITEM : "creates"
    ITEM ||--o{ ATTACHMENT : has
    ITEM ||--o{ CONVERSION_RUN : "has"
    ITEM ||--o| PUBLICATION : "results in"
    ITEM ||--o{ AUDIT_EVENT : "generates"
    ITEM }o--o{ TAG : "tagged with"
    ITEM }o--|| CATEGORY : "assigned to"
    PUBLICATION }o--|| REPOSITORY : "targets"
    USER ||--o{ AUDIT_EVENT : performs

    USER {
        uuid id PK
        string display_name
        string email
        string auth_provider
        string external_id
        string role
    }

    SOURCE_CONNECTOR {
        uuid id PK
        string type "outlook|teams|onedrive|sharepoint|planner|web|file|github|rss"
        string display_name
        json config
        bool enabled
    }

    SOURCE_SUBMISSION {
        uuid id PK
        uuid connector_id FK
        string external_ref "e.g. Graph message id, URL"
        datetime captured_at
        json raw_metadata
    }

    ITEM {
        uuid id PK
        uuid submission_id FK
        string title
        string summary
        string status "inbox|draft|review|approved|published|archived|error"
        string source_type
        string source_ref
        string author
        datetime captured_at
        datetime reviewed_at
        uuid reviewed_by FK
        uuid category_id FK
        string raw_path
        string curated_path
        string markdown_generated
        string markdown_final
        int version
    }

    ATTACHMENT {
        uuid id PK
        uuid item_id FK
        string filename
        string mime_type
        string storage_path
        int size_bytes
    }

    CONVERSION_RUN {
        uuid id PK
        uuid item_id FK
        string tool "markitdown|pandoc|docling|custom"
        string status "succeeded|failed"
        string input_path
        string output_path
        string error_message
        datetime started_at
        datetime finished_at
    }

    CATEGORY {
        uuid id PK
        string name
        string path "e.g. curated/processes"
        uuid parent_id FK
    }

    TAG {
        uuid id PK
        string name
    }

    PUBLICATION {
        uuid id PK
        uuid item_id FK
        uuid repository_id FK
        string commit_sha
        string branch
        string pr_url
        datetime published_at
        uuid published_by FK
    }

    REPOSITORY {
        uuid id PK
        string name
        string remote_url
        string default_branch
        string publish_mode "direct|pull_request"
        uuid credential_id FK
    }

    AUDIT_EVENT {
        uuid id PK
        uuid item_id FK
        uuid user_id FK
        string action
        json details
        datetime occurred_at
    }
```

## 3. Entity Descriptions

### User
A person who can log in. Has a role (`Admin` or `Curator`) and an auth provider
(`local`, `entra`, `github`).

### SourceConnector
A configured integration instance (e.g. "My Outlook", "Team Docs SharePoint Site").
Connectors are configuration + credentials + polling/webhook state; they are the
things an admin enables/disables/configures.

### SourceSubmission
A single inbound unit of content from a connector or manual entry (one email, one
Teams message/thread, one uploaded file, one URL submission, one browser-extension
capture). A submission always results in exactly one Item.

### Item
The central entity. Represents one piece of knowledge moving through the pipeline.
Tracks:
- Lifecycle `status` (state machine, see below).
- Both the system-generated Markdown (`markdown_generated`, immutable per conversion
  run) and the user-edited final Markdown (`markdown_final`).
- Paths into the target Git repo for both the raw artifact and the curated article.
- A `version` counter incremented on every edit, to support optimistic concurrency and
  history within the review UI (independent of Git history, which starts at publish).

### Attachment
Binary assets associated with an Item (the original uploaded file, extracted images
from a DOCX/PDF, etc.). Stored in object/blob storage (filesystem volume in MVP).

### ConversionRun
An auditable record of one conversion attempt (tool used, input/output paths,
success/failure, error). An Item can have multiple ConversionRuns (e.g. retried with
a different tool, or re-run after a Docling upgrade).

### Category
A node in the curation taxonomy, mapped to a folder path under `curated/` in the
target repository. Hierarchical (supports nested categories).

### Tag
A free-form label, many-to-many with Item, used for cross-cutting discovery
independent of folder-based categorization.

### Publication
The record of an Item actually being committed/pushed (and optionally PR'd) to a
Repository. One Item has at most one active Publication per Repository; republishing
after an edit creates a new commit but updates the same Publication record (keeping
`commit_sha` as the latest).

### Repository
A configured Git target (remote URL, default branch, publish mode, which credential to
use). Wiki Wrangler can be configured with more than one Repository (e.g. a work KB and
a personal KB) though MVP ships with single-repository configuration as the default
path.

### AuditEvent
An immutable log row for any state-changing action (capture, edit, approve, reject,
publish, connector config change), capturing who did what and when.

## 4. Item Lifecycle (State Machine)

```mermaid
stateDiagram-v2
    [*] --> Inbox: captured
    Inbox --> Draft: conversion succeeds
    Inbox --> Error: conversion fails
    Error --> Draft: retry succeeds
    Draft --> Review: user opens for review
    Review --> Draft: user edits / saves
    Review --> Approved: user approves
    Review --> Archived: user rejects
    Approved --> Published: publish job succeeds
    Approved --> Review: publish job fails, returned for fix
    Published --> Archived: user archives
    Archived --> [*]
```

Notes:
- **Inbox**: raw submission received, conversion queued or in progress.
- **Error**: conversion failed; raw content is retained and visible; user can retry or
  manually transcribe.
- **Draft**: Markdown generated, not yet opened for review (or saved after an edit).
- **Review**: actively being reviewed; this is the state the review UI operates on.
- **Approved**: reviewer has approved; queued for publish job.
- **Published**: a Publication record exists with a commit the user can trace.
- **Archived**: terminal "will not publish" state (from rejection or post-publish
  retirement). Archived items remain queryable for audit/history.

## 5. Key Invariants

- Every `Item` has traceable provenance: `source_type` + `source_ref` always resolve
  back to the originating `SourceSubmission`, and `raw_path` always points to a file
  under `raw/` in the target repository (or object storage before first publish).
- `markdown_generated` is never edited in place; user edits live in `markdown_final`.
  This preserves the ability to diff "what the converter produced" vs. "what the human
  approved."
- An `Item` cannot transition to `Published` without an associated `Publication` row
  referencing a real commit SHA.
- Deleting a `Category` that still has `Item`s assigned is disallowed; items must be
  re-categorized first.
