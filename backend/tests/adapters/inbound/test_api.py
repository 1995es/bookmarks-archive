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

from app.adapters.inbound.background import EnrichmentRunner, get_enrichment_runner
from app.adapters.outbound.database import Base, get_db
from app.adapters.outbound.orm import BookmarkRow
from app.adapters.outbound.sqlalchemy_repository import SqlAlchemyBookmarkRepository
from app.application.enrich_bookmark import enrich_bookmark
from app.domain.models import ExtractedData, FetchedContent
from app.domain.ports import BookmarkEnricherService, ContentFetcher
from app.main import app


async def _noop_runner(bookmark_id: uuid.UUID) -> None:
    pass


@pytest.fixture()
async def db_engine() -> AsyncGenerator[tuple[async_sessionmaker[AsyncSession], str]]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield TestingSessionLocal, path
    finally:
        await engine.dispose()
        os.remove(path)


@pytest.fixture()
async def db_session(
    db_engine: tuple[async_sessionmaker[AsyncSession], str],
) -> AsyncGenerator[AsyncSession]:
    TestingSessionLocal, _ = db_engine

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        async with TestingSessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    # Default to a no-op enrichment runner so CRUD tests never hit real HTTP/LLM
    # adapters; tests that care about the runner override it again themselves.
    app.dependency_overrides[get_enrichment_runner] = lambda: _noop_runner

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        await session.close()
        app.dependency_overrides.clear()


@pytest.fixture()
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    # raise_app_exceptions=False mirrors real deployments: BackgroundTasks run
    # after the HTTP response bytes are already sent, so a background failure
    # can no longer affect a response the client already received. Without this,
    # ASGITransport re-raises even post-completion background exceptions, which
    # a real server socket has no way to do.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


def make_real_enrichment_runner(
    session_factory: async_sessionmaker[AsyncSession],
    fetcher: ContentFetcher,
    enricher: BookmarkEnricherService,
) -> EnrichmentRunner:
    """Builds a runner backed by the test's real (temp-file) database but fake
    fetcher/enricher — the shape production's run_enrichment has, minus the
    real HTTP/LLM adapters, so it can prove the background task's own session
    writes where the request's session reads."""

    async def runner(bookmark_id: uuid.UUID) -> None:
        async with session_factory() as db:
            repo = SqlAlchemyBookmarkRepository(db)
            await enrich_bookmark(bookmark_id, repo=repo, fetcher=fetcher, enricher=enricher)

    return runner


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


async def test_list_defaults_to_newest_first(client: AsyncClient) -> None:
    await client.post("/bookmarks", json=make_payload(name="First"))
    await client.post("/bookmarks", json=make_payload(name="Second"))

    resp = await client.get("/bookmarks")

    assert [b["name"] for b in resp.json()] == ["Second", "First"]


async def test_list_sort_by_name_ascending(client: AsyncClient) -> None:
    await client.post("/bookmarks", json=make_payload(name="Banana"))
    await client.post("/bookmarks", json=make_payload(name="Apple"))

    resp = await client.get("/bookmarks", params={"sort_by": "name", "sort_order": "asc"})

    assert [b["name"] for b in resp.json()] == ["Apple", "Banana"]


async def test_list_pagination(client: AsyncClient) -> None:
    await client.post("/bookmarks", json=make_payload(name="Apple"))
    await client.post("/bookmarks", json=make_payload(name="Banana"))
    await client.post("/bookmarks", json=make_payload(name="Cherry"))

    resp = await client.get(
        "/bookmarks",
        params={"sort_by": "name", "sort_order": "asc", "limit": 1, "offset": 1},
    )

    assert resp.status_code == 200
    assert [b["name"] for b in resp.json()] == ["Banana"]
    assert resp.headers["X-Total-Count"] == "3"


async def test_list_total_count_header_reflects_filters_not_pagination(
    client: AsyncClient,
) -> None:
    await client.post("/bookmarks", json=make_payload(name="A", tags=["python"]))
    await client.post("/bookmarks", json=make_payload(name="B", tags=["ruby"]))

    resp = await client.get("/bookmarks", params={"tag": "python", "limit": 1})

    assert resp.headers["X-Total-Count"] == "1"


async def test_list_rejects_invalid_sort_by(client: AsyncClient) -> None:
    resp = await client.get("/bookmarks", params={"sort_by": "url"})
    assert resp.status_code == 422


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


# --- Fast path: url is the only required field ---


async def test_create_with_only_url_derives_name_and_defaults_type(client: AsyncClient) -> None:
    resp = await client.post("/bookmarks", json={"url": "https://www.example.com/article"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "example.com"
    assert body["type"] == "post"
    assert body["description"] is None
    assert body["tags"] == []


async def test_create_with_blank_name_derives_name_from_url(client: AsyncClient) -> None:
    resp = await client.post("/bookmarks", json=make_payload(name="   "))
    assert resp.status_code == 201
    assert resp.json()["name"] == "example.com"


async def test_create_without_url_422(client: AsyncClient) -> None:
    resp = await client.post("/bookmarks", json={"name": "A"})
    assert resp.status_code == 422


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


# --- Background enrichment ---


class RunnerSpy:
    def __init__(self) -> None:
        self.calls: list[uuid.UUID] = []

    async def __call__(self, bookmark_id: uuid.UUID) -> None:
        self.calls.append(bookmark_id)


class FailingRunnerSpy:
    async def __call__(self, bookmark_id: uuid.UUID) -> None:
        raise RuntimeError("enrichment blew up")


async def test_create_schedules_enrichment_task(client: AsyncClient) -> None:
    spy = RunnerSpy()
    app.dependency_overrides[get_enrichment_runner] = lambda: spy

    resp = await client.post("/bookmarks", json=make_payload())

    assert resp.status_code == 201
    assert len(spy.calls) == 1


async def test_enrichment_receives_the_created_bookmark_id(client: AsyncClient) -> None:
    spy = RunnerSpy()
    app.dependency_overrides[get_enrichment_runner] = lambda: spy

    resp = await client.post("/bookmarks", json=make_payload())

    body = resp.json()
    assert spy.calls == [uuid.UUID(body["id"])]


async def test_create_returns_201_before_enrichment_completes(
    client: AsyncClient, db_engine: tuple[async_sessionmaker[AsyncSession], str]
) -> None:
    session_factory, _ = db_engine
    fetcher = _FixedContentFetcher()
    enricher = _FixedEnricherService()
    app.dependency_overrides[get_enrichment_runner] = lambda: make_real_enrichment_runner(
        session_factory, fetcher, enricher
    )

    resp = await client.post("/bookmarks", json=make_payload(description="original"))

    body = resp.json()
    assert body["description"] == "original"


async def test_failing_enrichment_does_not_affect_response(client: AsyncClient) -> None:
    app.dependency_overrides[get_enrichment_runner] = lambda: FailingRunnerSpy()

    resp = await client.post("/bookmarks", json=make_payload())

    assert resp.status_code == 201


async def test_other_endpoints_do_not_schedule_enrichment(client: AsyncClient) -> None:
    spy = RunnerSpy()
    created = (await client.post("/bookmarks", json=make_payload())).json()
    app.dependency_overrides[get_enrichment_runner] = lambda: spy

    await client.put(f"/bookmarks/{created['id']}", json=make_payload(name="Updated"))
    await client.delete(f"/bookmarks/{created['id']}")

    assert spy.calls == []


# --- Background enrichment: end-to-end ---


class _FixedContentFetcher:
    async def fetch(self, url: str) -> FetchedContent:
        return FetchedContent(name="", description="", content="fetched content")


class _FixedEnricherService:
    async def extract_data(self, *, url: str, fetched: FetchedContent) -> ExtractedData:
        return ExtractedData(description="generated summary", tags=["python"])


async def test_enrichment_writes_are_visible_through_the_api(
    client: AsyncClient, db_engine: tuple[async_sessionmaker[AsyncSession], str]
) -> None:
    """Proves the background task's own session commits where the request's
    session (and later requests) read — the one thing fakes alone can't show."""
    session_factory, _ = db_engine
    fetcher = _FixedContentFetcher()
    enricher = _FixedEnricherService()
    app.dependency_overrides[get_enrichment_runner] = lambda: make_real_enrichment_runner(
        session_factory, fetcher, enricher
    )

    created = (await client.post("/bookmarks", json=make_payload(description="original"))).json()

    resp = await client.get(f"/bookmarks/{created['id']}")
    body = resp.json()
    assert "generated summary" in body["description"]
    assert "python" in body["tags"]


async def test_enrichment_replaces_placeholder_name_with_fetched_title(
    client: AsyncClient, db_engine: tuple[async_sessionmaker[AsyncSession], str]
) -> None:
    session_factory, _ = db_engine

    class _TitledContentFetcher:
        async def fetch(self, url: str) -> FetchedContent:
            return FetchedContent(name="Real Page Title", description="", content="content")

    app.dependency_overrides[get_enrichment_runner] = lambda: make_real_enrichment_runner(
        session_factory, _TitledContentFetcher(), _FixedEnricherService()
    )

    created = (await client.post("/bookmarks", json={"url": "https://www.example.com"})).json()
    assert created["name"] == "example.com"

    resp = await client.get(f"/bookmarks/{created['id']}")
    assert resp.json()["name"] == "Real Page Title"
