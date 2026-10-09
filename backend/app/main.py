import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text

from app.converters.html import html_to_markdown
from app.converters.text import convert_to_markdown
from app.db import (
    create_database_engine,
    database_check,
    database_url_for_path,
    initialize_database,
)


class CaptureRequest(BaseModel):
    title: str
    source_type: str
    source_ref: str | None = None
    markdown: str | None = None


ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".docx", ".md", ".pdf", ".pptx", ".txt", ".xlsx"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_URL_SIZE = 10 * 1024 * 1024


def create_app(database_url: str | None = None, storage_path: Path | None = None) -> FastAPI:
    resolved_url = database_url or os.getenv("WIKI_WRANGLER_DATABASE_URL")
    if resolved_url is None:
        resolved_url = database_url_for_path(
            Path(__file__).resolve().parents[2] / "data" / "wiki-wrangler.sqlite3"
        )
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
                {
                    "id": submission_id,
                    "source_type": request.source_type,
                    "source_ref": request.source_ref,
                },
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

    @app.get("/api/items")
    def list_items(status: str | None = None) -> list[dict[str, object]]:
        query = """
            SELECT items.id, items.title, items.status, source_submissions.source_type,
                   source_submissions.source_ref, items.created_at
            FROM items
            JOIN source_submissions ON source_submissions.id = items.submission_id
        """
        parameters: dict[str, str] = {}
        if status is not None:
            query += " WHERE items.status = :status"
            parameters["status"] = status
        query += " ORDER BY items.created_at DESC"

        with engine.connect() as connection:
            rows = connection.execute(text(query), parameters).mappings().all()
        return [dict(row) for row in rows]

    @app.get("/api/items/{item_id}")
    def get_item(item_id: str) -> dict[str, object]:
        with engine.connect() as connection:
            item = connection.execute(
                text(
                    """
                    SELECT items.id, items.submission_id, items.title, items.status,
                              items.markdown_generated, items.markdown_final, items.created_at,
                           source_submissions.source_type, source_submissions.source_ref,
                           source_submissions.captured_at
                    FROM items
                    JOIN source_submissions ON source_submissions.id = items.submission_id
                    WHERE items.id = :item_id
                    """
                ),
                {"item_id": item_id},
            ).mappings().first()
            if item is None:
                raise HTTPException(status_code=404, detail="Item not found")

            attachments = connection.execute(
                text(
                    """
                    SELECT id, filename, mime_type, storage_path, size_bytes, created_at
                    FROM attachments
                    WHERE item_id = :item_id
                    ORDER BY created_at
                    """
                ),
                {"item_id": item_id},
            ).mappings().all()

        result = dict(item)
        result["attachments"] = [dict(attachment) for attachment in attachments]
        return result

    @app.post("/api/items/{item_id}/convert")
    def convert_item(item_id: str) -> dict[str, object]:
        run_id = str(uuid4())
        conversion_error: str | None = None
        with engine.begin() as connection:
            item = connection.execute(
                text("SELECT id, status FROM items WHERE id = :item_id"),
                {"item_id": item_id},
            ).mappings().first()
            if item is None:
                raise HTTPException(status_code=404, detail="Item not found")

            attachment = connection.execute(
                text(
                    """
                    SELECT filename, storage_path
                    FROM attachments
                    WHERE item_id = :item_id
                    ORDER BY created_at
                    LIMIT 1
                    """
                ),
                {"item_id": item_id},
            ).mappings().first()
            if attachment is None:
                raise HTTPException(status_code=422, detail="Item has no uploaded attachment")

            connection.execute(
                text("""
                    INSERT INTO conversion_runs (id, item_id, tool, status)
                    VALUES (:id, :item_id, 'builtin-text', 'running')
                    """),
                {"id": run_id, "item_id": item_id},
            )

            try:
                content = (storage_root / attachment["storage_path"]).read_bytes()
                markdown = convert_to_markdown(attachment["filename"], content)
            except (OSError, ValueError, UnicodeError) as error:
                conversion_error = str(error)
                connection.execute(
                    text("""
                        UPDATE items SET status = 'error' WHERE id = :item_id
                        """),
                    {"item_id": item_id},
                )
                connection.execute(
                    text("""
                        UPDATE conversion_runs
                        SET status = 'failed', error_message = :error,
                            finished_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """),
                    {"id": run_id, "error": conversion_error},
                )
            else:
                connection.execute(
                    text("""
                        UPDATE items
                        SET status = 'draft', markdown_generated = :markdown,
                            markdown_final = :markdown
                        WHERE id = :item_id
                        """),
                    {"item_id": item_id, "markdown": markdown},
                )
                connection.execute(
                    text("""
                        UPDATE conversion_runs
                        SET status = 'succeeded', finished_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """),
                    {"id": run_id},
                )

        if conversion_error is not None:
            raise HTTPException(status_code=422, detail=conversion_error)

        return {"id": item_id, "status": "draft", "conversion_run_id": run_id}

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
                    {
                        "id": item_id,
                        "submission_id": submission_id,
                        "title": title or Path(filename).stem,
                    },
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO attachments
                            (id, item_id, filename, mime_type, storage_path, size_bytes)
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

    @app.post("/api/items/url", status_code=201)
    def capture_url(url: str, title: str | None = None) -> dict[str, str | int]:
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail="URL must use http or https")

        try:
            request = Request(url, headers={"User-Agent": "Wiki-Wrangler/0.1"})
            with urlopen(request, timeout=10) as response:
                content = response.read(MAX_URL_SIZE + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise HTTPException(status_code=422, detail=f"Unable to fetch URL: {error}") from error

        if len(content) > MAX_URL_SIZE:
            raise HTTPException(status_code=413, detail="URL response exceeds the 10 MB limit")
        try:
            extracted_title, markdown = html_to_markdown(content)
        except (UnicodeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        submission_id = str(uuid4())
        item_id = str(uuid4())
        attachment_id = str(uuid4())
        item_directory = storage_root / item_id
        item_directory.mkdir(parents=True, exist_ok=False)
        stored_path = item_directory / "source.html"
        stored_path.write_bytes(content)

        try:
            with engine.begin() as connection:
                connection.execute(
                    text("""
                        INSERT INTO source_submissions (id, source_type, source_ref)
                        VALUES (:id, 'url', :source_ref)
                        """),
                    {"id": submission_id, "source_ref": url},
                )
                connection.execute(
                    text("""
                        INSERT INTO items
                            (id, submission_id, title, status, markdown_generated, markdown_final)
                        VALUES (:id, :submission_id, :title, 'draft', :markdown, :markdown)
                        """),
                    {
                        "id": item_id,
                        "submission_id": submission_id,
                        "title": title or extracted_title or url,
                        "markdown": markdown,
                    },
                )
                connection.execute(
                    text("""
                        INSERT INTO attachments
                            (id, item_id, filename, mime_type, storage_path, size_bytes)
                        VALUES
                            (:id, :item_id, 'source.html', 'text/html', :storage_path, :size_bytes)
                        """),
                    {
                        "id": attachment_id,
                        "item_id": item_id,
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
            "status": "draft",
            "size_bytes": len(content),
        }

    return app


app = create_app()