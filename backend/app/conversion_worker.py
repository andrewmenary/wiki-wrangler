from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from sqlalchemy import text

from app.converters.text import convert_to_markdown
from app.db import create_database_engine


def run_next_conversion(database_url: str, storage_root: Path) -> bool:
    engine = create_database_engine(database_url)
    try:
        with engine.begin() as connection:
            run = connection.execute(
                text(
                    """
                    SELECT conversion_runs.id, conversion_runs.item_id,
                        attachments.filename, attachments.storage_path
                    FROM conversion_runs
                    JOIN attachments ON attachments.item_id = conversion_runs.item_id
                    WHERE conversion_runs.status = 'queued'
                    ORDER BY conversion_runs.started_at, conversion_runs.id
                    LIMIT 1
                    """
                )
            ).mappings().first()
            if run is None:
                return False
            connection.execute(
                text(
                    """
                    UPDATE conversion_runs
                    SET status = 'running', started_at = CURRENT_TIMESTAMP
                    WHERE id = :id AND status = 'queued'
                    """
                ),
                {"id": run["id"]},
            )

        try:
            content = (storage_root / run["storage_path"]).read_bytes()
            markdown = convert_to_markdown(run["filename"], content)
        except (OSError, ValueError, UnicodeError) as error:
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE items SET status = 'error' WHERE id = :item_id"),
                    {"item_id": run["item_id"]},
                )
                connection.execute(
                    text(
                        """
                        UPDATE conversion_runs
                        SET status = 'failed', error_message = :error,
                            finished_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {"id": run["id"], "error": str(error)},
                )
        else:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE items
                        SET status = 'draft', markdown_generated = :markdown,
                            markdown_final = :markdown
                        WHERE id = :item_id
                        """
                    ),
                    {"item_id": run["item_id"], "markdown": markdown},
                )
                connection.execute(
                    text(
                        """
                        UPDATE conversion_runs
                        SET status = 'succeeded', finished_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {"id": run["id"]},
                )
        return True
    finally:
        engine.dispose()


async def run_conversion_worker(
    database_url: str,
    storage_root: Path,
    *,
    poll_interval: float = 1.0,
    max_jobs: int | None = None,
) -> int:
    processed = 0
    while max_jobs is None or processed < max_jobs:
        if run_next_conversion(database_url, storage_root):
            processed += 1
            continue
        await asyncio.sleep(poll_interval)
    return processed


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run the Wiki Wrangler conversion worker")
    parser.add_argument(
        "--database-url",
        default=os.getenv("WIKI_WRANGLER_DATABASE_URL", "sqlite:////data/wiki-wrangler.sqlite3"),
    )
    parser.add_argument(
        "--storage-path",
        default=os.getenv("WIKI_WRANGLER_STORAGE_PATH", "/data/storage"),
    )
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--max-jobs", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(
        run_conversion_worker(
            args.database_url,
            Path(args.storage_path),
            poll_interval=args.poll_interval,
            max_jobs=args.max_jobs,
        )
    )


if __name__ == "__main__":
    _main()
