from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def create_database_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def initialize_database(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_info (version INTEGER NOT NULL)"))
        connection.execute(text("PRAGMA journal_mode=WAL"))
        if connection.execute(text("SELECT COUNT(*) FROM schema_info")).scalar_one() == 0:
            connection.execute(text("INSERT INTO schema_info (version) VALUES (1)"))
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