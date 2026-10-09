from contextlib import asynccontextmanager
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import text

from app.db import create_database_engine, database_check, database_url_for_path, initialize_database


class CaptureRequest(BaseModel):
    title: str
    source_type: str
    source_ref: str | None = None
    markdown: str | None = None


def create_app(database_url: str | None = None) -> FastAPI:
    resolved_url = database_url or os.getenv("WIKI_WRANGLER_DATABASE_URL")
    if resolved_url is None:
        resolved_url = database_url_for_path(Path(__file__).resolve().parents[2] / "data" / "wiki-wrangler.sqlite3")
    engine = create_database_engine(resolved_url)
    initialize_database(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        initialize_database(engine)
        yield
        engine.dispose()

    app = FastAPI(title="Wiki Wrangler API", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "database": "ok" if database_check(engine) else "error"}

    @app.post("/api/items", status_code=201)
    def capture_item(request: CaptureRequest) -> dict[str, str]:
        submission_id = str(uuid4())
        item_id = str(uuid4())
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO source_submissions (id, source_type, source_ref)
                    VALUES (:id, :source_type, :source_ref)
                    """
                ),
                {"id": submission_id, "source_type": request.source_type, "source_ref": request.source_ref},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO items (id, submission_id, title, markdown_final)
                    VALUES (:id, :submission_id, :title, :markdown)
                    """
                ),
                {
                    "id": item_id,
                    "submission_id": submission_id,
                    "title": request.title,
                    "markdown": request.markdown,
                },
            )
        return {"id": item_id, "submission_id": submission_id, "status": "inbox"}

    return app


app = create_app()