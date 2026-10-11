from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def create_database_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def initialize_database(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE IF NOT EXISTS schema_info (version INTEGER NOT NULL)")
        )
        connection.execute(text("PRAGMA journal_mode=WAL"))
        if connection.execute(text("SELECT COUNT(*) FROM schema_info")).scalar_one() == 0:
            connection.execute(text("INSERT INTO schema_info (version) VALUES (1)"))
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    auth_provider TEXT NOT NULL DEFAULT 'local',
                    external_id TEXT,
                    password_hash TEXT,
                    role TEXT NOT NULL DEFAULT 'curator',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (auth_provider, external_id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS source_submissions (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_ref TEXT,
                    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS categories (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    parent_id TEXT REFERENCES categories(id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS repositories (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    remote_url TEXT NOT NULL,
                    default_branch TEXT NOT NULL DEFAULT 'main',
                    publish_mode TEXT NOT NULL DEFAULT 'direct'
                        CHECK (publish_mode IN ('direct', 'pull_request')),
                    credential_ref TEXT NOT NULL,
                    raw_root TEXT NOT NULL DEFAULT 'raw',
                    curated_root TEXT NOT NULL DEFAULT 'curated',
                    is_default INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        repository_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(repositories)")).all()
        }
        if "visibility" not in repository_columns:
            connection.execute(
                text(
                    "ALTER TABLE repositories "
                    "ADD COLUMN visibility TEXT NOT NULL DEFAULT 'private'"
                )
            )
        if "publish_raw" not in repository_columns:
            connection.execute(
                text("ALTER TABLE repositories ADD COLUMN publish_raw INTEGER NOT NULL DEFAULT 1")
            )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS publications (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL UNIQUE REFERENCES items(id),
                    repository_id TEXT NOT NULL REFERENCES repositories(id),
                    raw_path TEXT NOT NULL,
                    curated_path TEXT NOT NULL,
                    commit_sha TEXT,
                    branch TEXT,
                    pr_url TEXT,
                    published_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    published_by TEXT REFERENCES users(id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    item_id TEXT REFERENCES items(id),
                    user_id TEXT REFERENCES users(id),
                    action TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL REFERENCES source_submissions(id),
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'inbox',
                    markdown_final TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL REFERENCES items(id),
                    filename TEXT NOT NULL,
                    mime_type TEXT,
                    storage_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        item_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(items)")).all()
        }
        if "markdown_generated" not in item_columns:
            connection.execute(text("ALTER TABLE items ADD COLUMN markdown_generated TEXT"))
        if "summary" not in item_columns:
            connection.execute(text("ALTER TABLE items ADD COLUMN summary TEXT"))
        if "tags_json" not in item_columns:
            connection.execute(
                text("ALTER TABLE items ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'")
            )
        if "category_id" not in item_columns:
            connection.execute(text("ALTER TABLE items ADD COLUMN category_id TEXT"))
        if "visibility" not in item_columns:
            connection.execute(
                text("ALTER TABLE items ADD COLUMN visibility TEXT NOT NULL DEFAULT 'private'")
            )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS conversion_runs (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL REFERENCES items(id),
                    tool TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output_path TEXT,
                    error_message TEXT,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS publish_jobs (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL REFERENCES items(id),
                    repository_id TEXT NOT NULL REFERENCES repositories(id),
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    commit_sha TEXT,
                    raw_path TEXT,
                    curated_path TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT
                )
                """
            )
        )


def database_url_for_path(database_path: Path) -> str:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{database_path.as_posix()}"


def database_check(engine: Engine) -> bool:
    with engine.connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one() == 1


def dispose_database(engine: Engine) -> Generator[None, None, None]:
    try:
        yield
    finally:
        engine.dispose()