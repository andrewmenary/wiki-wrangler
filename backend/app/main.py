import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import create_session_token, hash_password, hash_session_token, verify_password
from app.converters.html import html_to_markdown
from app.converters.text import convert_to_markdown
from app.db import (
    create_database_engine,
    database_check,
    database_url_for_path,
    initialize_database,
)
from app.domain.items import ItemStatus, can_transition


class CaptureRequest(BaseModel):
    title: str
    source_type: str
    source_ref: str | None = None
    markdown: str | None = None


class RegisterRequest(BaseModel):
    display_name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ItemUpdateRequest(BaseModel):
    title: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    category_id: str | None = None
    markdown_final: str | None = None
    status: str | None = None


class CategoryRequest(BaseModel):
    name: str
    path: str
    parent_id: str | None = None


class CategoryUpdateRequest(BaseModel):
    name: str | None = None
    path: str | None = None
    parent_id: str | None = None


ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".docx", ".md", ".pdf", ".pptx", ".txt", ".xlsx"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_URL_SIZE = 10 * 1024 * 1024
SESSION_COOKIE = "wiki_wrangler_session"
SESSION_LIFETIME = timedelta(hours=12)


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

    @app.post("/api/auth/register", status_code=201)
    def register(request: RegisterRequest, response: Response) -> dict[str, object]:
        display_name = request.display_name.strip()
        email = request.email.strip().lower()
        if not display_name or "@" not in email or len(request.password) < 8:
            raise HTTPException(status_code=422, detail="Invalid registration details")

        user_id = str(uuid4())
        token = create_session_token()
        session_id = str(uuid4())
        expires_at = datetime.now(timezone.utc) + SESSION_LIFETIME
        with engine.begin() as connection:
            if connection.execute(text("SELECT 1 FROM users LIMIT 1")).first() is not None:
                role = "curator"
            else:
                role = "admin"
            try:
                connection.execute(
                    text("""
                        INSERT INTO users (id, display_name, email, password_hash, role)
                        VALUES (:id, :display_name, :email, :password_hash, :role)
                        """),
                    {
                        "id": user_id,
                        "display_name": display_name,
                        "email": email,
                        "password_hash": hash_password(request.password),
                        "role": role,
                    },
                )
            except Exception as error:
                if "UNIQUE constraint failed: users.email" in str(error):
                    raise HTTPException(
                        status_code=409, detail="Email is already registered"
                    ) from error
                raise
            connection.execute(
                text("""
                    INSERT INTO sessions (id, user_id, token_hash, expires_at)
                    VALUES (:id, :user_id, :token_hash, :expires_at)
                    """),
                {
                    "id": session_id,
                    "user_id": user_id,
                    "token_hash": hash_session_token(token),
                    "expires_at": expires_at.isoformat(),
                },
            )
        response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=43200)
        return {"id": user_id, "display_name": display_name, "email": email, "role": role}

    @app.post("/api/auth/login")
    def login(request: LoginRequest, response: Response) -> dict[str, object]:
        email = request.email.strip().lower()
        with engine.connect() as connection:
            user = connection.execute(
                text("""
                    SELECT id, display_name, email, password_hash, role
                    FROM users
                    WHERE email = :email AND auth_provider = 'local' AND is_active = 1
                    """),
                {"email": email},
            ).mappings().first()
        if user is None or not verify_password(request.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        token = create_session_token()
        expires_at = datetime.now(timezone.utc) + SESSION_LIFETIME
        with engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO sessions (id, user_id, token_hash, expires_at)
                    VALUES (:id, :user_id, :token_hash, :expires_at)
                    """),
                {
                    "id": str(uuid4()),
                    "user_id": user["id"],
                    "token_hash": hash_session_token(token),
                    "expires_at": expires_at.isoformat(),
                },
            )
        response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=43200)
        return {
            "id": user["id"],
            "display_name": user["display_name"],
            "email": user["email"],
            "role": user["role"],
        }

    @app.get("/api/auth/me")
    def current_user(
        session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, object]:
        if not session:
            raise HTTPException(status_code=401, detail="Authentication required")
        with engine.connect() as connection:
            user = connection.execute(
                text("""
                    SELECT users.id, users.display_name, users.email, users.role
                    FROM sessions JOIN users ON users.id = sessions.user_id
                    WHERE sessions.token_hash = :token_hash
                      AND sessions.expires_at > :now
                      AND users.is_active = 1
                    """),
                {
                    "token_hash": hash_session_token(session),
                    "now": datetime.now(timezone.utc).isoformat(),
                },
            ).mappings().first()
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return dict(user)

    def require_session(
        session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> None:
        current_user(session)

    @app.post("/api/auth/logout", status_code=204)
    def logout(
        response: Response,
        session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> None:
        if session:
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM sessions WHERE token_hash = :token_hash"),
                    {"token_hash": hash_session_token(session)},
                )
        response.delete_cookie(SESSION_COOKIE)

    @app.get("/api/categories", dependencies=[Depends(require_session)])
    def list_categories() -> list[dict[str, object]]:
        with engine.connect() as connection:
            rows = connection.execute(
                text("""
                    SELECT id, name, path, parent_id
                    FROM categories
                    ORDER BY path
                    """)
            ).mappings().all()
        return [dict(row) for row in rows]

    @app.post("/api/categories", status_code=201, dependencies=[Depends(require_session)])
    def create_category(request: CategoryRequest) -> dict[str, object]:
        name = request.name.strip()
        path = request.path.strip().strip("/")
        if not name or not path:
            raise HTTPException(status_code=422, detail="Category name and path are required")

        category_id = str(uuid4())
        with engine.begin() as connection:
            if request.parent_id is not None:
                parent = connection.execute(
                    text("SELECT id FROM categories WHERE id = :parent_id"),
                    {"parent_id": request.parent_id},
                ).first()
                if parent is None:
                    raise HTTPException(status_code=422, detail="Parent category not found")
            try:
                connection.execute(
                    text("""
                        INSERT INTO categories (id, name, path, parent_id)
                        VALUES (:id, :name, :path, :parent_id)
                        """),
                    {
                        "id": category_id,
                        "name": name,
                        "path": path,
                        "parent_id": request.parent_id,
                    },
                )
            except Exception as error:
                if "UNIQUE constraint failed: categories.path" in str(error):
                    raise HTTPException(
                        status_code=409, detail="Category path already exists"
                    ) from error
                raise
        return {"id": category_id, "name": name, "path": path, "parent_id": request.parent_id}

    @app.patch("/api/categories/{category_id}", dependencies=[Depends(require_session)])
    def update_category(
        category_id: str, request: CategoryUpdateRequest
    ) -> dict[str, object]:
        if not request.model_fields_set:
            raise HTTPException(status_code=422, detail="At least one category field is required")
        with engine.begin() as connection:
            category = connection.execute(
                text("SELECT id, name, path, parent_id FROM categories WHERE id = :category_id"),
                {"category_id": category_id},
            ).mappings().first()
            if category is None:
                raise HTTPException(status_code=404, detail="Category not found")
            if request.parent_id == category_id:
                raise HTTPException(status_code=422, detail="Category cannot be its own parent")
            if request.parent_id is not None:
                parent = connection.execute(
                    text("SELECT id FROM categories WHERE id = :parent_id"),
                    {"parent_id": request.parent_id},
                ).first()
                if parent is None:
                    raise HTTPException(status_code=422, detail="Parent category not found")
            name = request.name.strip() if request.name is not None else category["name"]
            path = request.path.strip().strip("/") if request.path is not None else category["path"]
            parent_id = (
                request.parent_id
                if "parent_id" in request.model_fields_set
                else category["parent_id"]
            )
            if parent_id is not None:
                ancestor_id = parent_id
                visited: set[str] = set()
                while ancestor_id is not None:
                    if ancestor_id == category_id or ancestor_id in visited:
                        raise HTTPException(
                            status_code=422,
                            detail="Category hierarchy cannot contain a cycle",
                        )
                    visited.add(ancestor_id)
                    ancestor = connection.execute(
                        text("SELECT parent_id FROM categories WHERE id = :category_id"),
                        {"category_id": ancestor_id},
                    ).first()
                    ancestor_id = ancestor[0] if ancestor is not None else None
            if not name or not path:
                raise HTTPException(status_code=422, detail="Category name and path are required")
            try:
                connection.execute(
                    text("""
                        UPDATE categories
                        SET name = :name, path = :path, parent_id = :parent_id
                        WHERE id = :category_id
                        """),
                    {
                        "category_id": category_id,
                        "name": name,
                        "path": path,
                        "parent_id": parent_id,
                    },
                )
            except Exception as error:
                if "UNIQUE constraint failed: categories.path" in str(error):
                    raise HTTPException(
                        status_code=409, detail="Category path already exists"
                    ) from error
                raise
        return {
            "id": category_id,
            "name": name,
            "path": path,
            "parent_id": parent_id,
        }

    @app.delete(
        "/api/categories/{category_id}",
        status_code=204,
        dependencies=[Depends(require_session)],
    )
    def delete_category(category_id: str) -> None:
        with engine.begin() as connection:
            category = connection.execute(
                text("SELECT id FROM categories WHERE id = :category_id"),
                {"category_id": category_id},
            ).first()
            if category is None:
                raise HTTPException(status_code=404, detail="Category not found")
            assigned = connection.execute(
                text("SELECT 1 FROM items WHERE category_id = :category_id LIMIT 1"),
                {"category_id": category_id},
            ).first()
            if assigned is not None:
                raise HTTPException(status_code=409, detail="Category is assigned to an item")
            child = connection.execute(
                text("SELECT 1 FROM categories WHERE parent_id = :category_id LIMIT 1"),
                {"category_id": category_id},
            ).first()
            if child is not None:
                raise HTTPException(status_code=409, detail="Category has child categories")
            connection.execute(
                text("DELETE FROM categories WHERE id = :category_id"),
                {"category_id": category_id},
            )

    @app.post("/api/items", status_code=201, dependencies=[Depends(require_session)])
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

    @app.get("/api/items", dependencies=[Depends(require_session)])
    def list_items(status: str | None = None) -> list[dict[str, object]]:
        query = """
            SELECT items.id, items.title, items.summary, items.tags_json, items.status,
                source_submissions.source_type, source_submissions.source_ref,
                items.created_at
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
        items = []
        for row in rows:
            item = dict(row)
            item["tags"] = json.loads(item.pop("tags_json") or "[]")
            items.append(item)
        return items

    @app.get("/api/items/{item_id}", dependencies=[Depends(require_session)])
    def get_item(item_id: str) -> dict[str, object]:
        with engine.connect() as connection:
            item = connection.execute(
                text(
                    """
                    SELECT items.id, items.submission_id, items.title, items.status,
                        items.markdown_generated, items.markdown_final,
                        items.summary, items.tags_json, items.category_id,
                        categories.name AS category_name, categories.path AS category_path,
                        items.created_at,
                        source_submissions.source_type, source_submissions.source_ref,
                        source_submissions.captured_at
                    FROM items
                    JOIN source_submissions ON source_submissions.id = items.submission_id
                    LEFT JOIN categories ON categories.id = items.category_id
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
        result["tags"] = json.loads(result.pop("tags_json") or "[]")
        result["attachments"] = [dict(attachment) for attachment in attachments]
        return result

    @app.patch("/api/items/{item_id}", dependencies=[Depends(require_session)])
    def update_item(item_id: str, request: ItemUpdateRequest) -> dict[str, object]:
        if not request.model_fields_set:
            raise HTTPException(status_code=422, detail="At least one item field is required")
        if request.title is not None and not request.title.strip():
            raise HTTPException(status_code=422, detail="Title cannot be empty")

        target_status: ItemStatus | None = None
        if request.status is not None:
            try:
                target_status = ItemStatus(request.status)
            except ValueError as error:
                raise HTTPException(status_code=422, detail="Unknown item status") from error

        with engine.begin() as connection:
            item = connection.execute(
                text("SELECT status FROM items WHERE id = :item_id"),
                {"item_id": item_id},
            ).mappings().first()
            if item is None:
                raise HTTPException(status_code=404, detail="Item not found")

            current_status = ItemStatus(item["status"])
            if current_status is ItemStatus.ARCHIVED and target_status is None:
                raise HTTPException(status_code=409, detail="Archived items cannot be changed")
            if target_status is not None and not can_transition(current_status, target_status):
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot transition item from {current_status} to {target_status}",
                )
            if request.category_id is not None:
                category = connection.execute(
                    text("SELECT id FROM categories WHERE id = :category_id"),
                    {"category_id": request.category_id},
                ).first()
                if category is None:
                    raise HTTPException(status_code=422, detail="Category not found")

            update_fields = {
                "title": request.title.strip() if request.title is not None else None,
                "summary": request.summary.strip() if request.summary is not None else None,
                "tags_json": json.dumps(
                    list(dict.fromkeys(tag.strip() for tag in request.tags if tag.strip()))
                )
                if request.tags is not None
                else None,
                "category_id": request.category_id,
                "markdown_final": request.markdown_final,
                "status": target_status.value if target_status is not None else None,
                "category_id_set": int("category_id" in request.model_fields_set),
            }
            connection.execute(
                text("""
                    UPDATE items
                    SET title = COALESCE(:title, title),
                        summary = COALESCE(:summary, summary),
                        tags_json = COALESCE(:tags_json, tags_json),
                        category_id = CASE
                            WHEN :category_id_set = 1 THEN :category_id
                            ELSE category_id
                        END,
                        markdown_final = COALESCE(:markdown_final, markdown_final),
                        status = COALESCE(:status, status)
                    WHERE id = :item_id
                    """
                ),
                {"item_id": item_id, **update_fields},
            )

        return {
            "id": item_id,
            "status": target_status.value if target_status else current_status.value,
        }

    @app.post("/api/items/{item_id}/convert", dependencies=[Depends(require_session)])
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

    @app.post(
        "/api/items/upload",
        status_code=201,
        dependencies=[Depends(require_session)],
    )
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

    @app.post(
        "/api/items/url",
        status_code=201,
        dependencies=[Depends(require_session)],
    )
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