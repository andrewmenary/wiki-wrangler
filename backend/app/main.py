from contextlib import asynccontextmanager
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text

from app.db import create_database_engine, database_check, database_url_for_path, initialize_database


class CaptureRequest(BaseModel):
    title: str
    source_type: str
    source_ref: str | None = None
    markdown: str | None = None


ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".docx", ".md", ".pdf", ".pptx", ".txt", ".xlsx"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


def create_app(database_url: str | None = None, storage_path: Path | None = None) -> FastAPI:
    resolved_url = database_url or os.getenv("WIKI_WRANGLER_DATABASE_URL")
    if resolved_url is None:
        resolved_url = database_url_for_path(Path(__file__).resolve().parents[2] / "data" / "wiki-wrangler.sqlite3")
    engine = create_database_engine(resolved_url)
    initialize_database(engine)
    storage_root = storage_path or Path(os.getenv("WIKI_WRANGLER_STORAGE_PATH", "data/storage"))
    storage_root.mkdir(parents=True, exist_ok=True)

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

    @app.post("/api/items/upload", status_code=201)
    async def upload_item(
        file: UploadFile = File(...),
        title: str | None = Form(default=None),
    ) -> dict[str, str | int]:
        filename = Path(file.filename or "").name
        extension = Path(filename).suffix.lower()
        if not filename or extension not in ALLOWED_UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=415, detail="Unsupported file type")

        content = await file.read(MAX_UPLOAD_SIZE + 1)
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File exceeds the 10 MB limit")

        submission_id = str(uuid4())
        item_id = str(uuid4())
        attachment_id = str(uuid4())
        item_directory = storage_root / item_id
        item_directory.mkdir(parents=True, exist_ok=False)
        stored_path = item_directory / filename
        stored_path.write_bytes(content)

        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO source_submissions (id, source_type, source_ref)
                        VALUES (:id, 'file', :source_ref)
                        """
                    ),
                    {"id": submission_id, "source_ref": filename},
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO items (id, submission_id, title)
                        VALUES (:id, :submission_id, :title)
                        """
                    ),
                    {"id": item_id, "submission_id": submission_id, "title": title or Path(filename).stem},
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO attachments (id, item_id, filename, mime_type, storage_path, size_bytes)
                        VALUES (:id, :item_id, :filename, :mime_type, :storage_path, :size_bytes)
                        """
                    ),
                    {
                        "id": attachment_id,
                        "item_id": item_id,
                        "filename": filename,
                        "mime_type": file.content_type,
                        "storage_path": str(stored_path.relative_to(storage_root)),
                        "size_bytes": len(content),
                    },
                )
        except Exception:
            stored_path.unlink(missing_ok=True)
            item_directory.rmdir()
            raise

        return {
            "id": item_id,
            "submission_id": submission_id,
            "attachment_id": attachment_id,
            "status": "inbox",
            "size_bytes": len(content),
        }

    return app


app = create_app()