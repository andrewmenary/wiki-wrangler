import sqlite3
import subprocess
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app import main
from app.main import create_app
from app.publisher import PublishResult


@pytest.fixture
async def client(tmp_path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}",
        storage_path=tmp_path / "storage",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
async def authenticated_client(client: httpx.AsyncClient) -> httpx.AsyncClient:
    response = await client.post(
        "/api/auth/register",
        json={
            "display_name": "API Test User",
            "email": "api-test@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 201
    return client


async def test_health_reports_database_status(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_publishing_tables_are_initialized(client: httpx.AsyncClient, tmp_path) -> None:
    with sqlite3.connect(tmp_path / "test.sqlite3") as database:
        tables = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {"publications", "audit_events"}.issubset(tables)


async def test_item_routes_require_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/items")

    assert response.status_code == 401


async def test_first_user_can_register_and_use_session_cookie(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={
            "display_name": "Admin User",
            "email": "ADMIN@example.com",
            "password": "correct horse",
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "admin"
    assert "wiki_wrangler_session" in response.cookies

    current_user = await client.get("/api/auth/me")
    assert current_user.status_code == 200
    assert current_user.json()["email"] == "admin@example.com"

    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_expired_session_is_rejected(client: httpx.AsyncClient, tmp_path) -> None:
    response = await client.post(
        "/api/auth/register",
        json={
            "display_name": "Expired User",
            "email": "expired@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 201

    expired_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with sqlite3.connect(tmp_path / "test.sqlite3") as database:
        database.execute("UPDATE sessions SET expires_at = ?", (expired_at,))
        database.commit()

    assert (await client.get("/api/auth/me")).status_code == 401


async def test_registered_user_can_log_in_but_invalid_password_is_rejected(
    client: httpx.AsyncClient,
) -> None:
    await client.post(
        "/api/auth/register",
        json={"display_name": "Curator", "email": "curator@example.com", "password": "password123"},
    )
    client.cookies.clear()

    invalid = await client.post(
        "/api/auth/login",
        json={"email": "curator@example.com", "password": "wrong-password"},
    )
    assert invalid.status_code == 401

    login = await client.post(
        "/api/auth/login",
        json={"email": "curator@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "admin"


async def test_repository_configuration_requires_admin(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register",
        json={"display_name": "Admin", "email": "admin@example.com", "password": "password123"},
    )
    await client.post(
        "/api/auth/register",
        json={"display_name": "Curator", "email": "curator@example.com", "password": "password123"},
    )

    response = await client.get("/api/repositories")

    assert response.status_code == 403


async def test_admin_can_promote_curator_but_not_demote_last_admin(
    client: httpx.AsyncClient,
) -> None:
    admin_registration = await client.post(
        "/api/auth/register",
        json={"display_name": "Admin", "email": "admin@example.com", "password": "password123"},
    )
    admin_id = admin_registration.json()["id"]
    client.cookies.clear()
    curator_registration = await client.post(
        "/api/auth/register",
        json={"display_name": "Curator", "email": "curator@example.com", "password": "password123"},
    )
    curator_id = curator_registration.json()["id"]
    client.cookies.clear()
    await client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )

    promoted = await client.patch(
        f"/api/users/{curator_id}/role", json={"role": "admin"}
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    demoted = await client.patch(
        f"/api/users/{admin_id}/role", json={"role": "curator"}
    )
    assert demoted.status_code == 200

    client.cookies.clear()
    await client.post(
        "/api/auth/login",
        json={"email": "curator@example.com", "password": "password123"},
    )
    disabled = await client.patch(
        f"/api/users/{admin_id}/status", json={"is_active": False}
    )
    assert disabled.status_code == 200
    enabled = await client.patch(
        f"/api/users/{admin_id}/status", json={"is_active": True}
    )
    assert enabled.status_code == 200
    last_admin = await client.patch(
        f"/api/users/{curator_id}/role", json={"role": "curator"}
    )
    assert last_admin.status_code == 409


async def test_admin_can_manage_repository_configuration(
    authenticated_client: httpx.AsyncClient,
) -> None:
    created = await authenticated_client.post(
        "/api/repositories",
        json={
            "name": "Work Wiki",
            "remote_url": "https://github.com/example/work-wiki.git",
            "credential_ref": "github-work",
            "raw_root": "sources",
            "curated_root": "knowledge",
            "is_default": True,
        },
    )
    assert created.status_code == 201
    repository = created.json()
    assert repository["curated_root"] == "knowledge"
    assert repository["raw_root"] == "sources"

    invalid = await authenticated_client.patch(
        f"/api/repositories/{repository['id']}",
        json={"curated_root": "../outside"},
    )
    assert invalid.status_code == 422

    updated = await authenticated_client.patch(
        f"/api/repositories/{repository['id']}",
        json={"curated_root": "published"},
    )
    assert updated.status_code == 200
    assert updated.json()["curated_root"] == "published"

    default_delete = await authenticated_client.delete(f"/api/repositories/{repository['id']}")
    assert default_delete.status_code == 409

    secondary = await authenticated_client.post(
        "/api/repositories",
        json={
            "name": "Personal Wiki",
            "remote_url": "git@github.com:example/personal-wiki.git",
            "credential_ref": "github-personal",
        },
    )
    assert secondary.status_code == 201
    deleted = await authenticated_client.delete(f"/api/repositories/{secondary.json()['id']}")
    assert deleted.status_code == 204


async def test_approved_item_resolves_repository_publication_paths(
    authenticated_client: httpx.AsyncClient,
) -> None:
    repository = await authenticated_client.post(
        "/api/repositories",
        json={
            "name": "Work Wiki",
            "remote_url": "https://github.com/example/work-wiki.git",
            "credential_ref": "github-work",
            "raw_root": "sources",
            "curated_root": "knowledge",
            "is_default": True,
        },
    )
    category = await authenticated_client.post(
        "/api/categories",
        json={"name": "Runbooks", "path": "runbooks"},
    )
    upload = await authenticated_client.post(
        "/api/items/upload",
        files={"file": ("notes.txt", b"Restart steps", "text/plain")},
        data={"title": "Service Guide"},
    )
    item_id = upload.json()["id"]
    await authenticated_client.post(f"/api/items/{item_id}/convert")
    await authenticated_client.patch(
        f"/api/items/{item_id}",
        json={"category_id": category.json()["id"], "status": "review"},
    )
    await authenticated_client.patch(
        f"/api/items/{item_id}", json={"status": "approved"}
    )

    preview = await authenticated_client.get(f"/api/items/{item_id}/publication-preview")

    assert repository.status_code == 201
    assert preview.status_code == 200
    assert preview.json()["raw_path"] == f"sources/file/{item_id}/notes.txt"
    assert preview.json()["curated_path"] == "knowledge/runbooks/service-guide.md"


async def test_approved_item_can_be_published_and_recorded(
    authenticated_client: httpx.AsyncClient,
    monkeypatch,
) -> None:
    repository = await authenticated_client.post(
        "/api/repositories",
        json={
            "name": "Work Wiki",
            "remote_url": "https://github.com/example/work-wiki.git",
            "credential_ref": "github-work",
            "is_default": True,
        },
    )
    category = await authenticated_client.post(
        "/api/categories",
        json={"name": "Runbooks", "path": "runbooks"},
    )
    upload = await authenticated_client.post(
        "/api/items/upload",
        files={"file": ("notes.txt", b"Restart steps", "text/plain")},
        data={"title": "Service Guide"},
    )
    item_id = upload.json()["id"]
    await authenticated_client.post(f"/api/items/{item_id}/convert")
    await authenticated_client.patch(
        f"/api/items/{item_id}",
        json={"category_id": category.json()["id"], "status": "review"},
    )
    await authenticated_client.patch(
        f"/api/items/{item_id}", json={"status": "approved"}
    )

    def failing_publish(*args, **kwargs):
        raise RuntimeError("remote unavailable")

    monkeypatch.setattr(main, "publish_remote", failing_publish)
    failed = await authenticated_client.post(f"/api/items/{item_id}/publish")
    assert failed.status_code == 502
    detail = await authenticated_client.get(f"/api/items/{item_id}")
    assert detail.json()["status"] == "approved"

    def fake_publish(*args, **kwargs):
        return PublishResult(commit_sha="abc123", changed=True)

    monkeypatch.setattr(main, "publish_remote", fake_publish)
    published = await authenticated_client.post(f"/api/items/{item_id}/publish")

    assert repository.status_code == 201
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["commit_sha"] == "abc123"
    assert published.json()["commit_url"] == "https://github.com/example/work-wiki/commit/abc123"
    publication = await authenticated_client.get(f"/api/items/{item_id}/publication")
    assert publication.status_code == 200
    assert publication.json()["commit_sha"] == "abc123"
    assert publication.json()["commit_url"] == "https://github.com/example/work-wiki/commit/abc123"
    assert publication.json()["curated_path"] == "curated/runbooks/service-guide.md"
    audit = await authenticated_client.get(f"/api/audit?item_id={item_id}")
    assert any(event["action"] == "item.published" for event in audit.json())


async def test_public_repository_requires_public_item_and_omits_raw_path(
    authenticated_client: httpx.AsyncClient,
    monkeypatch,
) -> None:
    repository = await authenticated_client.post(
        "/api/repositories",
        json={
            "name": "Public Wiki",
            "remote_url": "https://github.com/example/public-wiki.git",
            "credential_ref": "github-public",
            "visibility": "public",
            "is_default": True,
        },
    )
    category = await authenticated_client.post(
        "/api/categories",
        json={"name": "Public Notes", "path": "public-notes"},
    )
    item = await authenticated_client.post(
        "/api/items",
        json={"title": "Public Guide", "source_type": "manual", "markdown": "Content"},
    )
    item_id = item.json()["id"]
    await authenticated_client.patch(
        f"/api/items/{item_id}",
        json={
            "category_id": category.json()["id"],
            "visibility": "public",
            "status": "draft",
        },
    )
    await authenticated_client.patch(
        f"/api/items/{item_id}", json={"status": "review"}
    )
    await authenticated_client.patch(
        f"/api/items/{item_id}", json={"status": "approved"}
    )

    preview = await authenticated_client.get(f"/api/items/{item_id}/publication-preview")

    assert repository.status_code == 201
    assert preview.status_code == 200
    assert preview.json()["raw_path"] is None

    unconfirmed = await authenticated_client.post(f"/api/items/{item_id}/publish")
    assert unconfirmed.status_code == 409

    def fake_publish(*args, **kwargs):
        return PublishResult(commit_sha="public123", changed=True)

    monkeypatch.setattr(main, "publish_remote", fake_publish)
    published = await authenticated_client.post(
        f"/api/items/{item_id}/publish", json={"confirm_public": True}
    )
    assert published.status_code == 200
    assert published.json()["raw_path"] is None


async def test_publish_endpoint_pushes_to_local_git_remote(
    authenticated_client: httpx.AsyncClient,
    monkeypatch,
    tmp_path,
) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(seed)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(seed), "config", "user.name", "Wiki Wrangler"], check=True)
    subprocess.run(
        ["git", "-C", str(seed), "config", "user.email", "wiki@example.com"], check=True
    )
    (seed / "README.md").write_text("Wiki", encoding="utf-8")
    subprocess.run(["git", "-C", str(seed), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(seed), "commit", "-m", "Initial"], check=True)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(seed), "remote", "add", "origin", str(remote)], check=True
    )
    subprocess.run(
        ["git", "-C", str(seed), "push", "origin", "main"],
        check=True,
        capture_output=True,
    )
    monkeypatch.setenv("WIKI_WRANGLER_PUBLISH_WORKSPACE", str(tmp_path / "workspace"))

    repository = await authenticated_client.post(
        "/api/repositories",
        json={
            "name": "Local Wiki",
            "remote_url": remote.as_uri(),
            "credential_ref": "local-test",
            "is_default": True,
        },
    )
    category = await authenticated_client.post(
        "/api/categories",
        json={"name": "Runbooks", "path": "runbooks"},
    )
    upload = await authenticated_client.post(
        "/api/items/upload",
        files={"file": ("notes.txt", b"Restart steps", "text/plain")},
        data={"title": "Service Guide"},
    )
    item_id = upload.json()["id"]
    await authenticated_client.post(f"/api/items/{item_id}/convert")
    await authenticated_client.patch(
        f"/api/items/{item_id}",
        json={"category_id": category.json()["id"], "status": "review"},
    )
    await authenticated_client.patch(
        f"/api/items/{item_id}", json={"status": "approved"}
    )

    published = await authenticated_client.post(f"/api/items/{item_id}/publish")

    assert repository.status_code == 201
    assert published.status_code == 200
    verification = tmp_path / "verification"
    subprocess.run(
        ["git", "clone", "--branch", "main", str(remote), str(verification)],
        check=True,
        capture_output=True,
    )
    assert (verification / "curated/runbooks/service-guide.md").exists()


async def test_capture_creates_inbox_item(authenticated_client: httpx.AsyncClient) -> None:
    response = await authenticated_client.post(
        "/api/items",
        json={"title": "Requirements", "source_type": "file", "source_ref": "requirements.txt"},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "inbox"
    assert response.json()["id"]
    assert response.json()["submission_id"]

    item_id = response.json()["id"]
    detail = await authenticated_client.get(f"/api/items/{item_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Requirements"
    assert detail.json()["source_type"] == "file"


async def test_items_can_be_filtered_by_status(authenticated_client: httpx.AsyncClient) -> None:
    await authenticated_client.post(
        "/api/items",
        json={"title": "Inbox item", "source_type": "manual"},
    )

    response = await authenticated_client.get("/api/items?status=inbox")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Inbox item"


async def test_missing_item_returns_not_found(authenticated_client: httpx.AsyncClient) -> None:
    response = await authenticated_client.get("/api/items/missing")

    assert response.status_code == 404


async def test_upload_stores_raw_file_as_inbox_item(
    authenticated_client: httpx.AsyncClient, tmp_path
) -> None:
    response = await authenticated_client.post(
        "/api/items/upload",
        files={"file": ("notes.txt", b"Meeting notes", "text/plain")},
        data={"title": "Meeting notes"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "inbox"
    assert body["size_bytes"] == len(b"Meeting notes")
    stored_files = list((tmp_path / "storage").rglob("notes.txt"))
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == b"Meeting notes"

    source = await authenticated_client.get(f"/api/items/{response.json()['id']}/source")
    assert source.status_code == 200
    assert source.json()["filename"] == "notes.txt"
    assert source.json()["content"] == "Meeting notes"


async def test_upload_rejects_unsupported_file_type(
    authenticated_client: httpx.AsyncClient,
) -> None:
    response = await authenticated_client.post(
        "/api/items/upload",
        files={"file": ("script.exe", b"not allowed", "application/octet-stream")},
    )

    assert response.status_code == 415


async def test_text_upload_can_be_converted_to_draft(
    authenticated_client: httpx.AsyncClient,
) -> None:
    upload = await authenticated_client.post(
        "/api/items/upload",
        files={"file": ("notes.txt", b"# Meeting notes", "text/plain")},
    )
    item_id = upload.json()["id"]

    response = await authenticated_client.post(f"/api/items/{item_id}/convert")

    assert response.status_code == 200
    assert response.json()["status"] == "draft"
    detail = await authenticated_client.get(f"/api/items/{item_id}")
    assert detail.json()["status"] == "draft"
    assert detail.json()["markdown_generated"] == "# Meeting notes"
    assert detail.json()["markdown_final"] == "# Meeting notes"


async def test_csv_upload_can_be_converted_to_markdown_table(
    authenticated_client: httpx.AsyncClient,
) -> None:
    upload = await authenticated_client.post(
        "/api/items/upload",
        files={"file": ("inventory.csv", b"Name,Status\nWiki,Ready", "text/csv")},
    )
    item_id = upload.json()["id"]

    response = await authenticated_client.post(f"/api/items/{item_id}/convert")

    assert response.status_code == 200
    detail = await authenticated_client.get(f"/api/items/{item_id}")
    assert detail.json()["markdown_generated"] == (
        "| Name | Status |\n| --- | --- |\n| Wiki | Ready |"
    )


async def test_item_can_be_reviewed_edited_and_approved(
    authenticated_client: httpx.AsyncClient,
    tmp_path,
) -> None:
    upload = await authenticated_client.post(
        "/api/items/upload",
        files={"file": ("notes.txt", b"Original notes", "text/plain")},
    )
    item_id = upload.json()["id"]
    await authenticated_client.post(f"/api/items/{item_id}/convert")

    review = await authenticated_client.patch(
        f"/api/items/{item_id}",
        json={
            "summary": "A concise summary",
            "tags": ["meeting", "planning", "meeting"],
            "markdown_final": "Edited notes",
            "status": "review",
        },
    )
    assert review.status_code == 200
    assert review.json()["status"] == "review"

    approved = await authenticated_client.patch(
        f"/api/items/{item_id}",
        json={"status": "approved"},
    )
    assert approved.status_code == 200
    detail = await authenticated_client.get(f"/api/items/{item_id}")
    assert detail.json()["status"] == "approved"
    assert detail.json()["markdown_final"] == "Edited notes"
    assert detail.json()["summary"] == "A concise summary"
    assert detail.json()["tags"] == ["meeting", "planning"]

    with sqlite3.connect(tmp_path / "test.sqlite3") as database:
        actions = [
            row[0]
            for row in database.execute(
                "SELECT action FROM audit_events WHERE item_id = ? ORDER BY occurred_at",
                (item_id,),
            )
        ]
    assert "item.approved" in actions

    audit = await authenticated_client.get(f"/api/audit?item_id={item_id}")
    assert audit.status_code == 200
    approval_event = next(event for event in audit.json() if event["action"] == "item.approved")
    assert approval_event["item_title"] == "notes"
    assert "status" in approval_event["details"]["fields"]

    listed = await authenticated_client.get("/api/items")
    listed_item = next(item for item in listed.json() if item["id"] == item_id)
    assert listed_item["tags"] == ["meeting", "planning"]
    assert "tags_json" not in listed_item


async def test_categories_support_hierarchy_and_item_assignment(
    authenticated_client: httpx.AsyncClient,
) -> None:
    parent = await authenticated_client.post(
        "/api/categories",
        json={"name": "Processes", "path": "processes"},
    )
    assert parent.status_code == 201
    invalid_slug = await authenticated_client.post(
        "/api/categories",
        json={"name": "Invalid", "path": "Process_Notes"},
    )
    assert invalid_slug.status_code == 422
    child = await authenticated_client.post(
        "/api/categories",
        json={
            "name": "Onboarding",
            "path": "onboarding",
            "parent_id": parent.json()["id"],
        },
    )
    assert child.status_code == 201

    capture = await authenticated_client.post(
        "/api/items",
        json={"title": "Guide", "source_type": "manual", "markdown": "Text"},
    )
    item_id = capture.json()["id"]
    assignment = await authenticated_client.patch(
        f"/api/items/{item_id}",
        json={"category_id": child.json()["id"]},
    )
    assert assignment.status_code == 200
    detail = await authenticated_client.get(f"/api/items/{item_id}")
    assert detail.json()["category_path"] == "processes/onboarding"

    duplicate = await authenticated_client.post(
        "/api/categories",
        json={"name": "Other", "path": "onboarding", "parent_id": parent.json()["id"]},
    )
    assert duplicate.status_code == 409

    cleared_assignment = await authenticated_client.patch(
        f"/api/items/{item_id}",
        json={"category_id": None},
    )
    assert cleared_assignment.status_code == 200
    detail = await authenticated_client.get(f"/api/items/{item_id}")
    assert detail.json()["category_id"] is None
    assert detail.json()["category_path"] is None

    cleared_parent = await authenticated_client.patch(
        f"/api/categories/{child.json()['id']}",
        json={"parent_id": None},
    )
    assert cleared_parent.status_code == 200
    assert cleared_parent.json()["parent_id"] is None

    reassigned = await authenticated_client.patch(
        f"/api/items/{item_id}",
        json={"category_id": child.json()["id"]},
    )
    assert reassigned.status_code == 200

    edited = await authenticated_client.patch(
        f"/api/categories/{child.json()['id']}",
        json={"name": "New Hire Onboarding", "path": "new-hire-onboarding"},
    )
    assert edited.status_code == 200
    assert edited.json()["path"] == "new-hire-onboarding"

    assigned_delete = await authenticated_client.delete(f"/api/categories/{edited.json()['id']}")
    assert assigned_delete.status_code == 409

    removable = await authenticated_client.post(
        "/api/categories",
        json={"name": "Temporary", "path": "temporary"},
    )
    assert (
        await authenticated_client.delete(f"/api/categories/{removable.json()['id']}")
    ).status_code == 204


async def test_category_updates_reject_ancestry_cycles(
    authenticated_client: httpx.AsyncClient,
) -> None:
    root = await authenticated_client.post(
        "/api/categories", json={"name": "Root", "path": "root"}
    )
    middle = await authenticated_client.post(
        "/api/categories",
        json={"name": "Middle", "path": "middle", "parent_id": root.json()["id"]},
    )
    leaf = await authenticated_client.post(
        "/api/categories",
        json={"name": "Leaf", "path": "leaf", "parent_id": middle.json()["id"]},
    )

    moved = await authenticated_client.patch(
        f"/api/categories/{middle.json()['id']}",
        json={"path": "renamed"},
    )
    assert moved.status_code == 200
    assert moved.json()["path"] == "root/renamed"
    descendants = await authenticated_client.get("/api/categories")
    leaf_record = next(entry for entry in descendants.json() if entry["id"] == leaf.json()["id"])
    assert leaf_record["path"] == "root/renamed/leaf"

    response = await authenticated_client.patch(
        f"/api/categories/{root.json()['id']}",
        json={"parent_id": leaf.json()["id"]},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Category hierarchy cannot contain a cycle"


async def test_draft_can_be_archived_without_hard_deleting_it(
    authenticated_client: httpx.AsyncClient,
) -> None:
    capture = await authenticated_client.post(
        "/api/items",
        json={"title": "Discard me", "source_type": "manual", "markdown": "Text"},
    )

    response = await authenticated_client.patch(
        f"/api/items/{capture.json()['id']}",
        json={"status": "archived"},
    )

    assert response.status_code == 200
    detail = await authenticated_client.get(f"/api/items/{capture.json()['id']}")
    assert detail.json()["status"] == "archived"

    edit = await authenticated_client.patch(
        f"/api/items/{capture.json()['id']}",
        json={"summary": "Should remain unchanged"},
    )
    assert edit.status_code == 409
    assert edit.json()["detail"] == "Archived items cannot be changed"


async def test_invalid_item_transition_is_rejected(
    authenticated_client: httpx.AsyncClient,
) -> None:
    capture = await authenticated_client.post(
        "/api/items",
        json={"title": "Draft", "source_type": "manual", "markdown": "Text"},
    )

    response = await authenticated_client.patch(
        f"/api/items/{capture.json()['id']}",
        json={"status": "approved"},
    )

    assert response.status_code == 409


async def test_pdf_upload_can_be_converted_by_markitdown(
    authenticated_client: httpx.AsyncClient,
) -> None:
    upload = await authenticated_client.post(
        "/api/items/upload",
        files={"file": ("notes.pdf", b"PDF text content", "application/pdf")},
    )
    item_id = upload.json()["id"]

    response = await authenticated_client.post(f"/api/items/{item_id}/convert")

    assert response.status_code == 200
    detail = await authenticated_client.get(f"/api/items/{item_id}")
    assert detail.json()["status"] == "draft"


async def test_url_capture_extracts_text_and_preserves_source(
    authenticated_client: httpx.AsyncClient, monkeypatch
) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit: int) -> bytes:
            return (
                b"<html><head><title>Useful page</title><script>ignored()</script>"
                b"</head><body><h1>Heading</h1><p><strong>Body</strong> text</p>"
                b"<ul><li>First</li><li><a href='https://example.com'>Second</a></li></ul>"
                b"</body></html>"
            )

    monkeypatch.setattr(main, "urlopen", lambda request, timeout: FakeResponse())

    response = await authenticated_client.post(
        "/api/items/url",
        params={"url": "https://example.com/page"},
    )

    assert response.status_code == 201
    item = (await authenticated_client.get(f"/api/items/{response.json()['id']}")).json()
    assert item["status"] == "draft"
    assert item["title"] == "Useful page"
    assert item["markdown_final"] == (
        "# Heading\n\n**Body** text\n\n- First\n\n- [Second](https://example.com)"
    )
    assert item["attachments"][0]["filename"] == "source.html"


async def test_url_capture_preserves_document_for_markitdown_conversion(
    authenticated_client: httpx.AsyncClient, monkeypatch
) -> None:
    class FakeHeaders:
        def get_content_type(self) -> str:
            return "application/pdf"

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit: int) -> bytes:
            return b"PDF text content"

    monkeypatch.setattr(main, "urlopen", lambda request, timeout: FakeResponse())

    response = await authenticated_client.post(
        "/api/items/url",
        params={"url": "https://example.com/download"},
    )

    assert response.status_code == 201
    item_id = response.json()["id"]
    detail = await authenticated_client.get(f"/api/items/{item_id}")
    assert detail.json()["status"] == "inbox"
    assert detail.json()["attachments"][0]["filename"] == "source.pdf"
    conversion = await authenticated_client.post(f"/api/items/{item_id}/convert")
    assert conversion.status_code == 200