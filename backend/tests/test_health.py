from collections.abc import AsyncIterator

import httpx
import pytest

from app import main
from app.main import create_app


@pytest.fixture
async def client(tmp_path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}",
        storage_path=tmp_path / "storage",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def test_health_reports_database_status(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


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


async def test_capture_creates_inbox_item(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/items",
        json={"title": "Requirements", "source_type": "file", "source_ref": "requirements.txt"},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "inbox"
    assert response.json()["id"]
    assert response.json()["submission_id"]

    item_id = response.json()["id"]
    detail = await client.get(f"/api/items/{item_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Requirements"
    assert detail.json()["source_type"] == "file"


async def test_items_can_be_filtered_by_status(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/items",
        json={"title": "Inbox item", "source_type": "manual"},
    )

    response = await client.get("/api/items?status=inbox")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Inbox item"


async def test_missing_item_returns_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/items/missing")

    assert response.status_code == 404


async def test_upload_stores_raw_file_as_inbox_item(client: httpx.AsyncClient, tmp_path) -> None:
    response = await client.post(
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


async def test_upload_rejects_unsupported_file_type(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/items/upload",
        files={"file": ("script.exe", b"not allowed", "application/octet-stream")},
    )

    assert response.status_code == 415


async def test_text_upload_can_be_converted_to_draft(client: httpx.AsyncClient) -> None:
    upload = await client.post(
        "/api/items/upload",
        files={"file": ("notes.txt", b"# Meeting notes", "text/plain")},
    )
    item_id = upload.json()["id"]

    response = await client.post(f"/api/items/{item_id}/convert")

    assert response.status_code == 200
    assert response.json()["status"] == "draft"
    detail = await client.get(f"/api/items/{item_id}")
    assert detail.json()["status"] == "draft"
    assert detail.json()["markdown_generated"] == "# Meeting notes"
    assert detail.json()["markdown_final"] == "# Meeting notes"


async def test_item_can_be_reviewed_edited_and_approved(client: httpx.AsyncClient) -> None:
    upload = await client.post(
        "/api/items/upload",
        files={"file": ("notes.txt", b"Original notes", "text/plain")},
    )
    item_id = upload.json()["id"]
    await client.post(f"/api/items/{item_id}/convert")

    review = await client.patch(
        f"/api/items/{item_id}",
        json={"markdown_final": "Edited notes", "status": "review"},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "review"

    approved = await client.patch(
        f"/api/items/{item_id}",
        json={"status": "approved"},
    )
    assert approved.status_code == 200
    detail = await client.get(f"/api/items/{item_id}")
    assert detail.json()["status"] == "approved"
    assert detail.json()["markdown_final"] == "Edited notes"


async def test_invalid_item_transition_is_rejected(client: httpx.AsyncClient) -> None:
    capture = await client.post(
        "/api/items",
        json={"title": "Draft", "source_type": "manual", "markdown": "Text"},
    )

    response = await client.patch(
        f"/api/items/{capture.json()['id']}",
        json={"status": "approved"},
    )

    assert response.status_code == 409


async def test_unsupported_conversion_marks_item_as_error(client: httpx.AsyncClient) -> None:
    upload = await client.post(
        "/api/items/upload",
        files={"file": ("notes.csv", b"name,value\nitem,1", "text/csv")},
    )
    item_id = upload.json()["id"]

    response = await client.post(f"/api/items/{item_id}/convert")

    assert response.status_code == 422
    detail = await client.get(f"/api/items/{item_id}")
    assert detail.json()["status"] == "error"


async def test_url_capture_extracts_text_and_preserves_source(
    client: httpx.AsyncClient, monkeypatch
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

    response = await client.post(
        "/api/items/url",
        params={"url": "https://example.com/page"},
    )

    assert response.status_code == 201
    item = (await client.get(f"/api/items/{response.json()['id']}")).json()
    assert item["status"] == "draft"
    assert item["title"] == "Useful page"
    assert item["markdown_final"] == (
        "# Heading\n\n**Body** text\n\n- First\n\n- [Second](https://example.com)"
    )
    assert item["attachments"][0]["filename"] == "source.html"