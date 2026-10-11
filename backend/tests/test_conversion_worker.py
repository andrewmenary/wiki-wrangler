from pathlib import Path

from sqlalchemy import text

from app.conversion_worker import run_next_conversion
from app.db import create_database_engine, initialize_database


def _create_conversion_fixture(tmp_path: Path, filename: str, content: bytes) -> tuple[str, str]:
    database_path = tmp_path / "conversion.sqlite3"
    engine = create_database_engine(f"sqlite:///{database_path.as_posix()}")
    initialize_database(engine)
    item_id = "item-conversion"
    run_id = "run-conversion"
    storage_path = Path("uploads") / filename
    (tmp_path / "storage" / storage_path.parent).mkdir(parents=True)
    (tmp_path / "storage" / storage_path).write_bytes(content)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO source_submissions (id, source_type) VALUES ('submission', 'upload')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO items (id, submission_id, title, status) "
                "VALUES (:id, 'submission', 'Conversion item', 'inbox')"
            ),
            {"id": item_id},
        )
        connection.execute(
            text(
                "INSERT INTO attachments "
                "(id, item_id, filename, storage_path, size_bytes) "
                "VALUES ('attachment', :item_id, :filename, :storage_path, :size_bytes)"
            ),
            {
                "item_id": item_id,
                "filename": filename,
                "storage_path": str(storage_path),
                "size_bytes": len(content),
            },
        )
        connection.execute(
            text(
                "INSERT INTO conversion_runs (id, item_id, tool, status) "
                "VALUES (:id, :item_id, 'builtin-text', 'queued')"
            ),
            {"id": run_id, "item_id": item_id},
        )
    engine.dispose()
    return f"sqlite:///{database_path.as_posix()}", run_id


def test_conversion_worker_persists_success(tmp_path: Path) -> None:
    database_url, run_id = _create_conversion_fixture(tmp_path, "notes.txt", b"# Notes")

    assert run_next_conversion(database_url, tmp_path / "storage") is True

    engine = create_database_engine(database_url)
    with engine.connect() as connection:
        run = connection.execute(
            text("SELECT status FROM conversion_runs WHERE id = :id"), {"id": run_id}
        ).scalar_one()
        item = connection.execute(
            text("SELECT status, markdown_generated FROM items WHERE id = 'item-conversion'")
        ).one()
    assert run == "succeeded"
    assert item == ("draft", "# Notes")


def test_conversion_worker_persists_failure(tmp_path: Path) -> None:
    database_url, run_id = _create_conversion_fixture(tmp_path, "notes.unknown", b"notes")

    assert run_next_conversion(database_url, tmp_path / "storage") is True

    engine = create_database_engine(database_url)
    with engine.connect() as connection:
        run = connection.execute(
            text("SELECT status, error_message FROM conversion_runs WHERE id = :id"),
            {"id": run_id},
        ).one()
        item_status = connection.execute(
            text("SELECT status FROM items WHERE id = 'item-conversion'")
        ).scalar_one()
    assert run[0] == "failed"
    assert "No converter" in run[1]
    assert item_status == "error"
