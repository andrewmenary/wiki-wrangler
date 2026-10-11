import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
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
from app.publisher import build_curated_document, publish_remote


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
    visibility: str | None = None


class CategoryRequest(BaseModel):
    name: str
    path: str
    parent_id: str | None = None


class CategoryUpdateRequest(BaseModel):
    name: str | None = None
    path: str | None = None
    parent_id: str | None = None


class RepositoryRequest(BaseModel):
    name: str
    remote_url: str
    default_branch: str = "main"
    publish_mode: str = "direct"
    credential_ref: str
    raw_root: str = "raw"
    curated_root: str = "curated"
    is_default: bool = False
    visibility: str = "private"
    publish_raw: bool = True


class RepositoryUpdateRequest(BaseModel):
    name: str | None = None
    remote_url: str | None = None
    default_branch: str | None = None
    publish_mode: str | None = None
    credential_ref: str | None = None
    raw_root: str | None = None
    curated_root: str | None = None
    is_default: bool | None = None
    visibility: str | None = None
    publish_raw: bool | None = None


class UserRoleUpdateRequest(BaseModel):
    role: str


class UserStatusUpdateRequest(BaseModel):
    is_active: bool


ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".docx", ".md", ".pdf", ".pptx", ".txt", ".xlsx"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_URL_SIZE = 10 * 1024 * 1024
MAX_SOURCE_PREVIEW_SIZE = 200_000
SESSION_COOKIE = "wiki_wrangler_session"
SESSION_LIFETIME = timedelta(hours=12)
CATEGORY_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_category_slug(value: str) -> str:
    slug = value.strip().strip("/")
    if not CATEGORY_SLUG_PATTERN.fullmatch(slug):
        raise HTTPException(
            status_code=422,
            detail="Category path must be a lowercase hyphenated slug",
        )
    return slug


def normalize_repository_root(value: str) -> str:
    root = value.strip().strip("/")
    if not CATEGORY_SLUG_PATTERN.fullmatch(root):
        raise HTTPException(
            status_code=422,
            detail="Repository roots must be lowercase hyphenated folder names",
        )
    return root


def slugify_publication_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


def validate_relative_publication_path(value: str) -> str:
    segments = value.split("/")
    if not segments or any(not CATEGORY_SLUG_PATTERN.fullmatch(segment) for segment in segments):
        raise HTTPException(status_code=422, detail="Category path cannot be published safely")
    return "/".join(segments)


def git_commit_url(remote_url: str, commit_sha: str | None) -> str | None:
    if not commit_sha:
        return None
    if remote_url.startswith("https://github.com/"):
        repository = remote_url.removeprefix("https://github.com/")
    elif remote_url.startswith("git@github.com:"):
        repository = remote_url.removeprefix("git@github.com:")
    else:
        return None
    return f"https://github.com/{repository.removesuffix('.git').strip('/')}/commit/{commit_sha}"


def validate_repository_values(
    request: RepositoryRequest | RepositoryUpdateRequest,
) -> dict[str, object]:
    values = request.model_dump(exclude_unset=not isinstance(request, RepositoryRequest))
    if "name" in values:
        values["name"] = str(values["name"]).strip()
        if not values["name"]:
            raise HTTPException(status_code=422, detail="Repository name is required")
    if "remote_url" in values:
        remote_url = str(values["remote_url"]).strip()
        if not remote_url.startswith(("https://", "http://", "ssh://", "git@", "file://")):
            raise HTTPException(status_code=422, detail="Unsupported repository URL")
        values["remote_url"] = remote_url
    if "default_branch" in values:
        values["default_branch"] = str(values["default_branch"]).strip()
        if not values["default_branch"]:
            raise HTTPException(status_code=422, detail="Default branch is required")
    if "publish_mode" in values and values["publish_mode"] not in {"direct", "pull_request"}:
        raise HTTPException(status_code=422, detail="Unknown publish mode")
    for visibility_name in ("visibility",):
        if visibility_name in values and values[visibility_name] not in {"private", "public"}:
            raise HTTPException(status_code=422, detail="Unknown visibility")
    if "credential_ref" in values:
        values["credential_ref"] = str(values["credential_ref"]).strip()
        if not values["credential_ref"]:
            raise HTTPException(status_code=422, detail="Credential reference is required")
    for root_name in ("raw_root", "curated_root"):
        if root_name in values:
            values[root_name] = normalize_repository_root(str(values[root_name]))
    return values


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

    def require_admin(
        session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> None:
        user = current_user(session)
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Administrator access required")

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
        categories = []
        for row in rows:
            category = dict(row)
            category["slug"] = category["path"].rsplit("/", maxsplit=1)[-1]
            categories.append(category)
        return categories

    @app.post("/api/categories", status_code=201, dependencies=[Depends(require_session)])
    def create_category(request: CategoryRequest) -> dict[str, object]:
        name = request.name.strip()
        if not name or not request.path.strip():
            raise HTTPException(status_code=422, detail="Category name and path are required")

        category_id = str(uuid4())
        with engine.begin() as connection:
            parent_path = None
            if request.parent_id is not None:
                parent = connection.execute(
                    text("SELECT id, path FROM categories WHERE id = :parent_id"),
                    {"parent_id": request.parent_id},
                ).mappings().first()
                if parent is None:
                    raise HTTPException(status_code=422, detail="Parent category not found")
                parent_path = parent["path"]
            slug = normalize_category_slug(request.path)
            path = f"{parent_path}/{slug}" if parent_path else slug
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
        return {
            "id": category_id,
            "name": name,
            "slug": slug,
            "path": path,
            "parent_id": request.parent_id,
        }

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
            name = request.name.strip() if request.name is not None else category["name"]
            parent_id = (
                request.parent_id
                if "parent_id" in request.model_fields_set
                else category["parent_id"]
            )
            parent_path = None
            if parent_id is not None:
                parent = connection.execute(
                    text("SELECT id, path FROM categories WHERE id = :parent_id"),
                    {"parent_id": parent_id},
                ).mappings().first()
                if parent is None:
                    raise HTTPException(status_code=422, detail="Parent category not found")
                parent_path = parent["path"]
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
            slug = (
                normalize_category_slug(request.path)
                if request.path is not None
                else category["path"].rsplit("/", maxsplit=1)[-1]
            )
            path = f"{parent_path}/{slug}" if parent_path else slug
            if not name:
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
                if path != category["path"]:
                    descendants = connection.execute(
                        text(
                            "SELECT id, path FROM categories "
                            "WHERE path LIKE :path_prefix"
                        ),
                        {"path_prefix": f"{category['path']}/%"},
                    ).mappings().all()
                    for descendant in descendants:
                        descendant_path = descendant["path"].replace(
                            f"{category['path']}/", f"{path}/", 1
                        )
                        connection.execute(
                            text("UPDATE categories SET path = :path WHERE id = :id"),
                            {"id": descendant["id"], "path": descendant_path},
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
            "slug": slug,
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

    @app.get("/api/repositories", dependencies=[Depends(require_admin)])
    def list_repositories() -> list[dict[str, object]]:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT id, name, remote_url, default_branch, publish_mode,
                        credential_ref, raw_root, curated_root, is_default,
                        visibility, publish_raw, created_at
                    FROM repositories
                    ORDER BY name
                    """
                )
            ).mappings().all()
        return [dict(row) for row in rows]

    @app.post("/api/repositories", status_code=201, dependencies=[Depends(require_admin)])
    def create_repository(request: RepositoryRequest) -> dict[str, object]:
        values = validate_repository_values(request)
        repository_id = str(uuid4())
        with engine.begin() as connection:
            if values.get("is_default"):
                connection.execute(text("UPDATE repositories SET is_default = 0"))
            connection.execute(
                text(
                    """
                    INSERT INTO repositories
                        (id, name, remote_url, default_branch, publish_mode,
                         credential_ref, raw_root, curated_root, is_default,
                         visibility, publish_raw)
                    VALUES
                        (:id, :name, :remote_url, :default_branch, :publish_mode,
                         :credential_ref, :raw_root, :curated_root, :is_default,
                         :visibility, :publish_raw)
                    """
                ),
                {"id": repository_id, **values},
            )
            row = connection.execute(
                text("SELECT * FROM repositories WHERE id = :id"), {"id": repository_id}
            ).mappings().one()
        return dict(row)

    @app.patch("/api/repositories/{repository_id}", dependencies=[Depends(require_admin)])
    def update_repository(
        repository_id: str, request: RepositoryUpdateRequest
    ) -> dict[str, object]:
        if not request.model_fields_set:
            raise HTTPException(status_code=422, detail="At least one repository field is required")
        values = validate_repository_values(request)
        with engine.begin() as connection:
            existing = connection.execute(
                text("SELECT id FROM repositories WHERE id = :id"), {"id": repository_id}
            ).first()
            if existing is None:
                raise HTTPException(status_code=404, detail="Repository not found")
            if values.get("is_default"):
                connection.execute(text("UPDATE repositories SET is_default = 0"))
            assignments = ", ".join(f"{field} = :{field}" for field in values)
            connection.execute(
                text(f"UPDATE repositories SET {assignments} WHERE id = :id"),
                {"id": repository_id, **values},
            )
            row = connection.execute(
                text("SELECT * FROM repositories WHERE id = :id"), {"id": repository_id}
            ).mappings().one()
        return dict(row)

    @app.delete(
        "/api/repositories/{repository_id}",
        status_code=204,
        dependencies=[Depends(require_admin)],
    )
    def delete_repository(repository_id: str) -> None:
        with engine.begin() as connection:
            repository = connection.execute(
                text("SELECT is_default FROM repositories WHERE id = :id"),
                {"id": repository_id},
            ).first()
            if repository is None:
                raise HTTPException(status_code=404, detail="Repository not found")
            if repository[0]:
                raise HTTPException(
                    status_code=409, detail="The default repository cannot be deleted"
                )
            connection.execute(
                text("DELETE FROM repositories WHERE id = :id"), {"id": repository_id}
            )

    @app.get("/api/audit", dependencies=[Depends(require_admin)])
    def list_audit_events(item_id: str | None = None) -> list[dict[str, object]]:
        query = """
            SELECT audit_events.id, audit_events.item_id, audit_events.action,
                audit_events.details_json, audit_events.occurred_at,
                users.display_name AS user_display_name,
                items.title AS item_title
            FROM audit_events
            LEFT JOIN users ON users.id = audit_events.user_id
            LEFT JOIN items ON items.id = audit_events.item_id
        """
        parameters: dict[str, str] = {}
        if item_id is not None:
            query += " WHERE audit_events.item_id = :item_id"
            parameters["item_id"] = item_id
        query += " ORDER BY audit_events.occurred_at DESC"
        with engine.connect() as connection:
            rows = connection.execute(text(query), parameters).mappings().all()
        events = []
        for row in rows:
            event = dict(row)
            event["details"] = json.loads(event.pop("details_json") or "{}")
            events.append(event)
        return events

    @app.get("/api/users", dependencies=[Depends(require_admin)])
    def list_users() -> list[dict[str, object]]:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT id, display_name, email, role, is_active, created_at
                    FROM users
                    ORDER BY display_name
                    """
                )
            ).mappings().all()
        return [dict(row) for row in rows]

    @app.patch("/api/users/{user_id}/role", dependencies=[Depends(require_admin)])
    def update_user_role(
        user_id: str,
        request: UserRoleUpdateRequest,
        admin: dict[str, object] = Depends(current_user),
    ) -> dict[str, object]:
        if request.role not in {"admin", "curator"}:
            raise HTTPException(status_code=422, detail="Unknown user role")
        with engine.begin() as connection:
            target = connection.execute(
                text("SELECT id, display_name, role FROM users WHERE id = :id"),
                {"id": user_id},
            ).mappings().first()
            if target is None:
                raise HTTPException(status_code=404, detail="User not found")
            if target["role"] == "admin" and request.role == "curator":
                admin_count = connection.execute(
                    text("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1")
                ).scalar_one()
                if admin_count <= 1:
                    raise HTTPException(
                        status_code=409,
                        detail="The last administrator cannot be demoted",
                    )
            connection.execute(
                text("UPDATE users SET role = :role WHERE id = :id"),
                {"id": user_id, "role": request.role},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events (id, user_id, action, details_json)
                    VALUES (:id, :user_id, 'user.role_changed', :details_json)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "user_id": admin["id"],
                    "details_json": json.dumps(
                        {"target_user_id": user_id, "role": request.role}
                    ),
                },
            )
        return {"id": user_id, "display_name": target["display_name"], "role": request.role}

    @app.patch("/api/users/{user_id}/status", dependencies=[Depends(require_admin)])
    def update_user_status(
        user_id: str,
        request: UserStatusUpdateRequest,
        admin: dict[str, object] = Depends(current_user),
    ) -> dict[str, object]:
        with engine.begin() as connection:
            target = connection.execute(
                text("SELECT id, display_name, role, is_active FROM users WHERE id = :id"),
                {"id": user_id},
            ).mappings().first()
            if target is None:
                raise HTTPException(status_code=404, detail="User not found")
            if not request.is_active and target["role"] == "admin" and target["is_active"]:
                admin_count = connection.execute(
                    text("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1")
                ).scalar_one()
                if admin_count <= 1:
                    raise HTTPException(
                        status_code=409,
                        detail="The last administrator cannot be disabled",
                    )
            connection.execute(
                text("UPDATE users SET is_active = :is_active WHERE id = :id"),
                {"id": user_id, "is_active": int(request.is_active)},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events (id, user_id, action, details_json)
                    VALUES (:id, :user_id, 'user.status_changed', :details_json)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "user_id": admin["id"],
                    "details_json": json.dumps(
                        {"target_user_id": user_id, "is_active": request.is_active}
                    ),
                },
            )
        return {
            "id": user_id,
            "display_name": target["display_name"],
            "is_active": request.is_active,
        }

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

    @app.get("/api/items/{item_id}/publication-preview", dependencies=[Depends(require_session)])
    def publication_preview(
        item_id: str, repository_id: str | None = None
    ) -> dict[str, object]:
        with engine.connect() as connection:
            item = connection.execute(
                text(
                    """
                    SELECT items.status, items.title, items.visibility,
                        categories.path AS category_path,
                        source_submissions.source_type, attachments.filename
                    FROM items
                    JOIN source_submissions ON source_submissions.id = items.submission_id
                    LEFT JOIN categories ON categories.id = items.category_id
                    LEFT JOIN attachments ON attachments.item_id = items.id
                    WHERE items.id = :item_id
                    ORDER BY attachments.created_at
                    LIMIT 1
                    """
                ),
                {"item_id": item_id},
            ).mappings().first()
            if item is None:
                raise HTTPException(status_code=404, detail="Item not found")
            if item["status"] != ItemStatus.APPROVED.value:
                raise HTTPException(status_code=409, detail="Only approved items can be published")
            if item["category_path"] is None:
                raise HTTPException(
                    status_code=422,
                    detail="Item must have a category before publishing",
                )
            repository_query = (
                "SELECT id, name, raw_root, curated_root, visibility, publish_raw "
                "FROM repositories WHERE id = :repository_id"
                if repository_id
                else "SELECT id, name, raw_root, curated_root, visibility, publish_raw "
                "FROM repositories WHERE is_default = 1 ORDER BY created_at LIMIT 1"
            )
            repository = connection.execute(
                text(repository_query), {"repository_id": repository_id} if repository_id else {}
            ).mappings().first()
        if repository is None:
            raise HTTPException(status_code=422, detail="No target repository is configured")
        if repository["visibility"] == "public" and item["visibility"] != "public":
            raise HTTPException(
                status_code=409,
                detail="Private items cannot be published to a public repository",
            )

        category_path = validate_relative_publication_path(item["category_path"])
        source_type = slugify_publication_name(item["source_type"])
        filename = Path(item["filename"] or f"{source_type}.source").name
        title_slug = slugify_publication_name(item["title"])
        return {
            "repository_id": repository["id"],
            "repository_name": repository["name"],
            "raw_path": (
                f"{repository['raw_root']}/{source_type}/{item_id}/{filename}"
                if repository["publish_raw"] and repository["visibility"] != "public"
                else None
            ),
            "curated_path": f"{repository['curated_root']}/{category_path}/{title_slug}.md",
        }

    @app.post("/api/items/{item_id}/publish", dependencies=[Depends(require_session)])
    def publish_item(
        item_id: str,
        repository_id: str | None = None,
        user: dict[str, object] = Depends(current_user),
    ) -> dict[str, object]:
        preview = publication_preview(item_id, repository_id)
        with engine.connect() as connection:
            item = connection.execute(
                text(
                    """
                    SELECT items.title, items.markdown_final, attachments.storage_path,
                        items.summary, source_submissions.source_ref,
                        repositories.remote_url, repositories.default_branch
                    FROM items
                    JOIN source_submissions ON source_submissions.id = items.submission_id
                    JOIN repositories ON repositories.id = :repository_id
                    LEFT JOIN attachments ON attachments.item_id = items.id
                    WHERE items.id = :item_id
                    ORDER BY attachments.created_at
                    LIMIT 1
                    """
                ),
                {"item_id": item_id, "repository_id": preview["repository_id"]},
            ).mappings().first()
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")
        workspace_root = Path(
            os.getenv("WIKI_WRANGLER_PUBLISH_WORKSPACE", "data/publish-workspaces")
        )
        workspace = workspace_root / str(preview["repository_id"])
        raw_source = (
            storage_root / item["storage_path"]
            if preview["raw_path"] and item["storage_path"]
            else None
        )
        try:
            result = publish_remote(
                item["remote_url"],
                workspace,
                item["default_branch"],
                raw_source,
                preview["raw_path"],
                preview["curated_path"],
                build_curated_document(
                    item["title"],
                    item["summary"],
                    item["source_ref"],
                    preview["raw_path"],
                    item["markdown_final"] or "",
                ),
                f"Publish {item['title']}",
            )
        except Exception as error:
            raise HTTPException(status_code=502, detail=f"Git publish failed: {error}") from error

        publication_id = str(uuid4())
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE items SET status = 'published' WHERE id = :item_id"),
                {"item_id": item_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO publications
                        (id, item_id, repository_id, raw_path, curated_path,
                         commit_sha, branch, published_by)
                    VALUES
                        (:id, :item_id, :repository_id, :raw_path, :curated_path,
                         :commit_sha, :branch, :published_by)
                    """
                ),
                {
                    "id": publication_id,
                    "item_id": item_id,
                    "repository_id": preview["repository_id"],
                    "raw_path": preview["raw_path"] or "",
                    "curated_path": preview["curated_path"],
                    "commit_sha": result.commit_sha,
                    "branch": item["default_branch"],
                    "published_by": user["id"],
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events (id, item_id, user_id, action, details_json)
                    VALUES (:id, :item_id, :user_id, 'item.published', :details_json)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "item_id": item_id,
                    "user_id": user["id"],
                    "details_json": json.dumps(
                        {"repository_id": preview["repository_id"], "commit_sha": result.commit_sha}
                    ),
                },
            )
        return {
            "id": publication_id,
            "status": "published",
            "commit_sha": result.commit_sha,
            "commit_url": git_commit_url(item["remote_url"], result.commit_sha),
            "raw_path": preview["raw_path"],
            "curated_path": preview["curated_path"],
        }

    @app.get("/api/items/{item_id}/publication", dependencies=[Depends(require_session)])
    def get_publication(item_id: str) -> dict[str, object]:
        with engine.connect() as connection:
            publication = connection.execute(
                text(
                    """
                    SELECT publications.id, publications.item_id, publications.repository_id,
                        publications.raw_path, publications.curated_path,
                        publications.commit_sha, publications.branch,
                        publications.pr_url, publications.published_at,
                        repositories.name AS repository_name, repositories.remote_url
                    FROM publications
                    JOIN repositories ON repositories.id = publications.repository_id
                    WHERE publications.item_id = :item_id
                    """
                ),
                {"item_id": item_id},
            ).mappings().first()
        if publication is None:
            raise HTTPException(status_code=404, detail="Publication not found")
        result = dict(publication)
        result["commit_url"] = git_commit_url(result.pop("remote_url"), result["commit_sha"])
        return result

    @app.get("/api/items/{item_id}/source", dependencies=[Depends(require_session)])
    def get_item_source(item_id: str) -> dict[str, object]:
        with engine.connect() as connection:
            attachment = connection.execute(
                text(
                    """
                    SELECT attachments.filename, attachments.mime_type, attachments.storage_path
                    FROM attachments
                    JOIN items ON items.id = attachments.item_id
                    WHERE attachments.item_id = :item_id
                    ORDER BY attachments.created_at
                    LIMIT 1
                    """
                ),
                {"item_id": item_id},
            ).mappings().first()
        if attachment is None:
            raise HTTPException(status_code=404, detail="Source not found")

        filename = attachment["filename"]
        mime_type = attachment["mime_type"] or "application/octet-stream"
        previewable = (
            mime_type.startswith("text/")
            or Path(filename).suffix.lower() in {".html", ".md", ".txt"}
        )
        if not previewable:
            return {
                "filename": filename,
                "mime_type": mime_type,
                "preview_available": False,
                "content": None,
            }

        try:
            with (storage_root / attachment["storage_path"]).open("rb") as source_file:
                content = source_file.read(MAX_SOURCE_PREVIEW_SIZE + 1)
            truncated = len(content) > MAX_SOURCE_PREVIEW_SIZE
            if truncated:
                content = content[:MAX_SOURCE_PREVIEW_SIZE]
            text_content = content.decode("utf-8", errors="replace")
        except OSError as error:
            raise HTTPException(status_code=404, detail="Source file unavailable") from error
        return {
            "filename": filename,
            "mime_type": mime_type,
            "preview_available": True,
            "truncated": truncated,
            "content": text_content,
        }

    @app.patch("/api/items/{item_id}", dependencies=[Depends(require_session)])
    def update_item(
        item_id: str,
        request: ItemUpdateRequest,
        user: dict[str, object] = Depends(current_user),
    ) -> dict[str, object]:
        if not request.model_fields_set:
            raise HTTPException(status_code=422, detail="At least one item field is required")
        if request.title is not None and not request.title.strip():
            raise HTTPException(status_code=422, detail="Title cannot be empty")
        if request.visibility is not None and request.visibility not in {"private", "public"}:
            raise HTTPException(status_code=422, detail="Unknown visibility")

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
                "visibility": request.visibility,
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
                        status = COALESCE(:status, status),
                        visibility = COALESCE(:visibility, visibility)
                    WHERE id = :item_id
                    """
                ),
                {"item_id": item_id, **update_fields},
            )
            action = (
                "item.approved"
                if target_status is ItemStatus.APPROVED
                else "item.status_changed"
                if target_status is not None
                else "item.edited"
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events (id, item_id, user_id, action, details_json)
                    VALUES (:id, :item_id, :user_id, :action, :details_json)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "item_id": item_id,
                    "user_id": user["id"],
                    "action": action,
                    "details_json": json.dumps({"fields": sorted(request.model_fields_set)}),
                },
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
                response_headers = getattr(response, "headers", None)
                content_type = (
                    response_headers.get_content_type()
                    if response_headers is not None
                    and hasattr(response_headers, "get_content_type")
                    else None
                )
                content = response.read(MAX_URL_SIZE + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise HTTPException(status_code=422, detail=f"Unable to fetch URL: {error}") from error

        if len(content) > MAX_URL_SIZE:
            raise HTTPException(status_code=413, detail="URL response exceeds the 10 MB limit")

        url_path = urlparse(url).path
        url_extension = Path(url_path).suffix.lower()
        document_extensions = {
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        }
        document_extension = document_extensions.get(content_type or "") or url_extension
        if document_extension in {".docx", ".pdf", ".pptx", ".xlsx"}:
            source_filename = Path(url_path).name or f"source{document_extension}"
            if Path(source_filename).suffix.lower() != document_extension:
                source_filename = f"source{document_extension}"
            submission_id = str(uuid4())
            item_id = str(uuid4())
            attachment_id = str(uuid4())
            item_directory = storage_root / item_id
            item_directory.mkdir(parents=True, exist_ok=False)
            stored_path = item_directory / source_filename
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
                            INSERT INTO items (id, submission_id, title)
                            VALUES (:id, :submission_id, :title)
                            """),
                        {
                            "id": item_id,
                            "submission_id": submission_id,
                            "title": title or Path(source_filename).stem,
                        },
                    )
                    connection.execute(
                        text("""
                            INSERT INTO attachments
                                (id, item_id, filename, mime_type, storage_path, size_bytes)
                            VALUES
                                (:id, :item_id, :filename, :mime_type, :storage_path, :size_bytes)
                            """),
                        {
                            "id": attachment_id,
                            "item_id": item_id,
                            "filename": source_filename,
                            "mime_type": content_type or "application/octet-stream",
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