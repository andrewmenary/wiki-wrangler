from collections.abc import AsyncIterator

import httpx
import pytest

from app.main import create_app


@pytest.fixture
async def client(tmp_path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}")
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