"""Tests for the inbound HTTP adapter: the bookmarks CRUD API.

Runs through the real FastAPI app and a real (temporary) SQLite database,
since that's the only way to exercise routing, request/response schemas, and
dependency wiring together.

The app is driven with httpx's ASGITransport rather than TestClient: the routes
are async, and ASGITransport calls them on the test's own event loop, so the
overridden session shares that loop instead of TestClient's worker thread.
"""

import os
import tempfile
import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.outbound.database import Base, get_db
from app.adapters.outbound.orm import BookmarkRow
from app.main import app


@pytest.fixture()
async def db_session() -> AsyncGenerator[AsyncSession]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        async with TestingSessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        await session.close()
        app.dependency_overrides.clear()
        await engine.dispose()
        os.remove(path)


@pytest.fixture()
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        yield async_client


def make_payload(**overrides: object) -> dict:
    payload = {
        "name": "Some article",
        "url": "https://example.com",
        "description": "an article",
        "tags": ["python", "web"],
        "type": "post",
    }
    payload.update(overrides)
    return payload


# --- CRUD round trip ---


async def test_create_returns_201_with_id_and_created_at(client: AsyncClient) -> None:
    resp = await client.post("/bookmarks", json=make_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert "created_at" in body
    assert body["created_at"] is not None
    assert body["name"] == "Some article"
    assert body["url"] == "https://example.com"
    assert body["description"] == "an article"
    assert body["tags"] == ["python", "web"]
    assert body["type"] == "post"
    assert "deleted_at" not in body


async def test_get_by_id(client: AsyncClient) -> None:
    created = (await client.post("/bookmarks", json=make_payload())).json()
    resp = await client.get(f"/bookmarks/{created['id']}")
    assert resp.status_code == 200
    assert resp.json() == created


async def test_update_via_put(client: AsyncClient) -> None:
    created = (await client.post("/bookmarks", json=make_payload())).json()
    update_payload = make_payload(name="Updated name", tags=["updated"], type="video")
    resp = await client.put(f"/bookmarks/{created['id']}", json=update_payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == created["id"]
    assert body["name"] == "Updated name"
    assert body["tags"] == ["updated"]
    assert body["type"] == "video"
    # id and created_at are not client-settable / should be unchanged
    assert body["created_at"] == created["created_at"]


async def test_list(client: AsyncClient) -> None:
    await client.post("/bookmarks", json=make_payload(name="A"))
    await client.post("/bookmarks", json=make_payload(name="B"))
    resp = await client.get("/bookmarks")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    names = {b["name"] for b in body}
    assert names == {"A", "B"}


# --- Not found ---


async def test_get_unknown_id_404(client: AsyncClient) -> None:
    resp = await client.get(f"/bookmarks/{uuid.uuid7()}")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Bookmark not found"}


async def test_put_unknown_id_404(client: AsyncClient) -> None:
    resp = await client.put(f"/bookmarks/{uuid.uuid7()}", json=make_payload())
    assert resp.status_code == 404


async def test_delete_unknown_id_404(client: AsyncClient) -> None:
    resp = await client.delete(f"/bookmarks/{uuid.uuid7()}")
    assert resp.status_code == 404


# --- Soft delete ---


async def test_delete_is_soft(client: AsyncClient, db_session: AsyncSession) -> None:
    created = (await client.post("/bookmarks", json=make_payload())).json()
    bookmark_id = created["id"]

    resp = await client.delete(f"/bookmarks/{bookmark_id}")
    assert resp.status_code == 204
    assert resp.content == b""

    get_resp = await client.get(f"/bookmarks/{bookmark_id}")
    assert get_resp.status_code == 404

    list_resp = await client.get("/bookmarks")
    assert list_resp.json() == []

    # Querying the DB directly shows the row still exists with deleted_at set.
    row = await db_session.get(BookmarkRow, uuid.UUID(bookmark_id))
    assert row is not None
    assert row.deleted_at is not None


# --- Filtering ---


async def test_filter_by_tag(client: AsyncClient) -> None:
    await client.post("/bookmarks", json=make_payload(name="A", tags=["python"]))
    await client.post("/bookmarks", json=make_payload(name="B", tags=["ruby"]))
    resp = await client.get("/bookmarks", params={"tag": "python"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "A"


async def test_filter_by_type(client: AsyncClient) -> None:
    await client.post("/bookmarks", json=make_payload(name="A", type="post"))
    await client.post("/bookmarks", json=make_payload(name="B", type="video"))
    resp = await client.get("/bookmarks", params={"type": "video"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "B"


async def test_filter_by_tag_and_type_combined(client: AsyncClient) -> None:
    await client.post("/bookmarks", json=make_payload(name="A", tags=["python"], type="post"))
    await client.post("/bookmarks", json=make_payload(name="B", tags=["python"], type="video"))
    await client.post("/bookmarks", json=make_payload(name="C", tags=["ruby"], type="post"))
    resp = await client.get("/bookmarks", params={"tag": "python", "type": "post"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "A"


async def test_filter_no_match_returns_empty_list(client: AsyncClient) -> None:
    await client.post("/bookmarks", json=make_payload(tags=["python"]))
    resp = await client.get("/bookmarks", params={"tag": "nonexistent"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_tag_filter_is_exact_not_substring(client: AsyncClient) -> None:
    """Regression test: LIKE '%py%' would incorrectly match 'python'. Must be exact."""
    await client.post("/bookmarks", json=make_payload(tags=["python"]))
    resp = await client.get("/bookmarks", params={"tag": "py"})
    assert resp.status_code == 200
    assert resp.json() == []


# --- Validation ---


async def test_invalid_type_on_post_body_422(client: AsyncClient) -> None:
    resp = await client.post("/bookmarks", json=make_payload(type="invalid-type"))
    assert resp.status_code == 422


async def test_invalid_type_on_query_param_422(client: AsyncClient) -> None:
    await client.post("/bookmarks", json=make_payload())
    resp = await client.get("/bookmarks", params={"type": "invalid-type"})
    assert resp.status_code == 422


async def test_tags_omitted_defaults_to_empty_list(client: AsyncClient) -> None:
    payload = make_payload()
    del payload["tags"]
    resp = await client.post("/bookmarks", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["tags"] == []
    assert body["tags"] is not None
