"""Unit tests for background.py's own retry/failure bookkeeping.

Exercises run_enrichment directly (rather than through the API, like
test_api.py's enrichment tests) since the retry-then-fail behavior being
tested here lives entirely inside background.py, not enrich_bookmark(). The
module-level SessionLocal/HttpContentFetcher/LLMBookmarkEnricherService that
run_enrichment composes internally are monkeypatched to a temp-file database
and fakes, so this never touches the real bookmarks.db or the network.
"""

import os
import tempfile
import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tenacity import wait_none

from app.adapters.inbound import background
from app.adapters.outbound.database import Base
from app.adapters.outbound.sqlalchemy_repository import SqlAlchemyBookmarkRepository
from app.domain.exceptions import ContentFetchError
from app.domain.models import (
    Bookmark,
    BookmarkType,
    EnrichmentStatus,
    ExtractedData,
    FetchedContent,
)
from app.domain.ports import ContentFetcher


class _FailingFetcher:
    """Raises ContentFetchError on every call, counting attempts."""

    def __init__(self) -> None:
        self.calls = 0

    async def __aenter__(self) -> ContentFetcher:
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass

    async def fetch(self, url: str) -> FetchedContent:
        self.calls += 1
        raise ContentFetchError("rate limited")


class _FlakyFetcher:
    """Fails `fail_times` times, then succeeds — proves a transient failure
    that clears within the retry budget still ends in DONE."""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    async def __aenter__(self) -> ContentFetcher:
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass

    async def fetch(self, url: str) -> FetchedContent:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ContentFetchError("transient")
        return FetchedContent(name="", description="", content="fetched content")


class _FixedEnricherService:
    async def extract_data(self, *, url: str, fetched: FetchedContent) -> ExtractedData:
        return ExtractedData(description="generated", tags=["generated"])


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


@pytest.fixture(autouse=True)
def _no_real_backoff() -> None:
    """Retries still happen (proving the attempt count), just without sleeping."""
    original_wait = background.enrich_bookmark_with_retry.retry.wait
    background.enrich_bookmark_with_retry.retry.wait = wait_none()
    yield
    background.enrich_bookmark_with_retry.retry.wait = original_wait


async def _seed_bookmark(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    bookmark = Bookmark(
        id=uuid.uuid4(),
        name="Example",
        url="https://example.com",
        description=None,
        tags=[],
        type=BookmarkType.SITE,
    )
    async with session_factory() as db:
        await SqlAlchemyBookmarkRepository(db).add(bookmark)
    return bookmark.id


async def test_run_enrichment_retries_and_marks_failed_after_exhausting_attempts(
    db_engine: tuple[async_sessionmaker[AsyncSession], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory, _ = db_engine
    monkeypatch.setattr(background, "SessionLocal", session_factory)
    fetcher = _FailingFetcher()
    monkeypatch.setattr(background, "HttpContentFetcher", lambda: fetcher)
    monkeypatch.setattr(
        background, "LLMBookmarkEnricherService", lambda model: _FixedEnricherService()
    )

    bookmark_id = await _seed_bookmark(session_factory)

    await background.run_enrichment(bookmark_id)

    assert fetcher.calls == background._MAX_ENRICHMENT_ATTEMPTS
    async with session_factory() as db:
        saved = await SqlAlchemyBookmarkRepository(db).get(bookmark_id)
    assert saved is not None
    assert saved.enrichment_status == EnrichmentStatus.FAILED
    assert saved.description is None


async def test_run_enrichment_succeeds_after_transient_failures(
    db_engine: tuple[async_sessionmaker[AsyncSession], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory, _ = db_engine
    monkeypatch.setattr(background, "SessionLocal", session_factory)
    fetcher = _FlakyFetcher(fail_times=background._MAX_ENRICHMENT_ATTEMPTS - 1)
    monkeypatch.setattr(background, "HttpContentFetcher", lambda: fetcher)
    monkeypatch.setattr(
        background, "LLMBookmarkEnricherService", lambda model: _FixedEnricherService()
    )

    bookmark_id = await _seed_bookmark(session_factory)

    await background.run_enrichment(bookmark_id)

    assert fetcher.calls == background._MAX_ENRICHMENT_ATTEMPTS
    async with session_factory() as db:
        saved = await SqlAlchemyBookmarkRepository(db).get(bookmark_id)
    assert saved is not None
    assert saved.enrichment_status == EnrichmentStatus.DONE
    assert saved.description == "generated"
