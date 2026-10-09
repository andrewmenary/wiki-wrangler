from collections.abc import AsyncIterator

import httpx
import pytest

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