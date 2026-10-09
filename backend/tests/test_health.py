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