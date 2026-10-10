# Database Schema

## 1. Engine Choice

SQLite, per the product brief, is used as the single-file embedded database for MVP.
It is well suited here because:

- Wiki Wrangler is single-tenant/self-hosted with modest write concurrency (one team's
  curation activity, plus a handful of background workers).
- It simplifies Docker deployment (one volume-mounted file, trivial backup = file copy).
- WAL mode (`PRAGMA journal_mode=WAL`) gives acceptable concurrent read/write behavior
  for the worker + API access pattern.

**Scaling note:** if multi-tenant or high-concurrency usage emerges, the data access
layer should be written against an ORM (SQLAlchemy) with migrations (Alembic) so a
later move to PostgreSQL is a connection-string + migration-dialect change, not a
rewrite. This is called out explicitly as a Post-MVP consideration in the
[Risk Analysis](./15-risk-analysis.md).

## 2. Schema (DDL)

```sql
-- Users & auth
CREATE TABLE users (
    id              TEXT PRIMARY KEY,              -- uuid
    display_name    TEXT NOT NULL,
    email           TEXT UNIQUE,
    auth_provider   TEXT NOT NULL CHECK (auth_provider IN ('local','entra','github')),
    external_id     TEXT,                          -- subject/oid from IdP, null for local
    password_hash   TEXT,                           -- null unless auth_provider='local'
    role            TEXT NOT NULL DEFAULT 'curator' CHECK (role IN ('admin','curator')),
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (auth_provider, external_id)
);

CREATE TABLE device_tokens (                        -- browser extension auth
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id),
    token_hash      TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL DEFAULT 'Browser Extension',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at    TEXT,
    revoked_at      TEXT
);

-- Connectors & submissions
CREATE TABLE source_connectors (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL CHECK (type IN
                        ('outlook','teams','teams_transcript','onedrive','sharepoint',
                         'planner','web','file','github','rss')),
    display_name    TEXT NOT NULL,
    config_json     TEXT NOT NULL DEFAULT '{}',     -- connector-specific settings
    credential_ref  TEXT,                           -- key into secrets store, not the secret itself
    enabled         INTEGER NOT NULL DEFAULT 1,
    last_synced_at  TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE source_submissions (
    id              TEXT PRIMARY KEY,
    connector_id    TEXT REFERENCES source_connectors(id),  -- null for manual upload
    external_ref    TEXT,                           -- Graph message id / URL / hash, for idempotency
    captured_by     TEXT REFERENCES users(id),       -- who triggered manual capture, if applicable
    raw_metadata_json TEXT NOT NULL DEFAULT '{}',
    captured_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (connector_id, external_ref)
);

-- Taxonomy
CREATE TABLE categories (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,                   -- display label, e.g. 'Wiki Wrangler'
    path            TEXT NOT NULL UNIQUE,            -- canonical relative path, e.g. 'projects/wiki-wrangler'
    parent_id       TEXT REFERENCES categories(id)
);

CREATE TABLE tags (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE
);

-- Core lifecycle entity
CREATE TABLE items (
    id                  TEXT PRIMARY KEY,
    submission_id       TEXT NOT NULL REFERENCES source_submissions(id),
    title               TEXT NOT NULL,
    summary             TEXT,
    status              TEXT NOT NULL DEFAULT 'inbox' CHECK (status IN
                            ('inbox','draft','review','approved','published','archived','error')),
    source_type         TEXT NOT NULL,
    source_ref          TEXT,                        -- human-readable source locator (URL, mailbox item id, etc.)
    author              TEXT,
    category_id         TEXT REFERENCES categories(id),
    raw_path            TEXT,                         -- path under raw/ once published, or staging path before
    curated_path        TEXT,                         -- path under curated/ once published
    markdown_generated  TEXT,                          -- immutable output of last successful conversion
    markdown_final      TEXT,                          -- user-edited draft, seeded from markdown_generated
    error_message       TEXT,
    version             INTEGER NOT NULL DEFAULT 1,
    captured_at         TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_at         TEXT,
    reviewed_by         TEXT REFERENCES users(id),
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_items_status ON items(status);
CREATE INDEX idx_items_category ON items(category_id);

CREATE TABLE item_tags (
    item_id         TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    tag_id          TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (item_id, tag_id)
);

CREATE TABLE attachments (
    id              TEXT PRIMARY KEY,
    item_id         TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    mime_type       TEXT,
    storage_path    TEXT NOT NULL,                   -- relative path in blob volume
    size_bytes      INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE conversion_runs (
    id              TEXT PRIMARY KEY,
    item_id         TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    tool            TEXT NOT NULL CHECK (tool IN ('markitdown','pandoc','docling','ai','manual')),
    status          TEXT NOT NULL CHECK (status IN ('running','succeeded','failed')),
    input_path      TEXT,
    output_path     TEXT,
    error_message   TEXT,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT
);

-- Publishing
CREATE TABLE repositories (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    remote_url      TEXT NOT NULL,
    default_branch  TEXT NOT NULL DEFAULT 'main',
    publish_mode    TEXT NOT NULL DEFAULT 'direct' CHECK (publish_mode IN ('direct','pull_request')),
    credential_ref  TEXT NOT NULL,                    -- key into secrets store
    raw_root        TEXT NOT NULL DEFAULT 'raw',
    curated_root    TEXT NOT NULL DEFAULT 'curated',
    is_default      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE publications (
    id              TEXT PRIMARY KEY,
    item_id         TEXT NOT NULL REFERENCES items(id),
    repository_id   TEXT NOT NULL REFERENCES repositories(id),
    commit_sha      TEXT,
    branch          TEXT,
    pr_url          TEXT,
    published_at    TEXT NOT NULL DEFAULT (datetime('now')),
    published_by    TEXT REFERENCES users(id),
    UNIQUE (item_id, repository_id)
);

-- Audit
CREATE TABLE audit_events (
    id              TEXT PRIMARY KEY,
    item_id         TEXT REFERENCES items(id),
    user_id         TEXT REFERENCES users(id),
    action          TEXT NOT NULL,                    -- e.g. 'item.captured','item.approved','item.published'
    details_json    TEXT NOT NULL DEFAULT '{}',
    occurred_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_audit_item ON audit_events(item_id);
CREATE INDEX idx_audit_occurred ON audit_events(occurred_at);
```

## 3. Design Notes

- **UUIDs as TEXT primary keys** are used throughout rather than autoincrement
  integers, so that ids can be generated client-side/worker-side before insertion
  (useful for idempotent job processing and for referencing an item in object storage
  paths before the DB row commits).
- **Secrets are never stored in this schema.** `credential_ref`/`credential_ref`-style
  columns are indirection keys into a secrets store (see
  [Security Model](./09-security-model.md)) — e.g. an environment-variable name, a
  Docker secret path, or a Vault key path.
- **`markdown_generated` vs `markdown_final`** directly mirrors the domain model
  invariant that system output and human-edited output are kept distinct, enabling a
  "diff against original conversion" view in the UI.
- **`conversion_runs` and `audit_events`** are append-only logs; nothing is ever
  updated in place, which keeps history trustworthy for debugging conversion quality
  and for compliance/traceability.
- **Soft lifecycle via `status` + `archived` is preferred over deletion.** Rows are
  not physically deleted on reject/archive so provenance and audit history remain
  intact; a separate retention/purge job (Post-MVP) can hard-delete beyond a configured
  age if required by data-retention policy.
