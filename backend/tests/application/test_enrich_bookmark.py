"""Unit tests for the enrich_bookmark use case, using in-memory fakes.

No database or HTTP involved — the fakes stand in for ContentFetcher and
BookmarkEnricherService the same way FakeBookmarkRepository stands in for
BookmarkRepository.
"""

import uuid
from collections.abc import Callable

import pytest

from app.application import bookmark_service
from app.application.enrich_bookmark import enrich_bookmark
from app.domain.exceptions import BookmarkNotFoundError, ContentFetchError, EnrichmentError
from app.domain.models import BookmarkType, ExtractedData, FetchedContent
from tests.fakes import FakeBookmarkRepository


class FakeContentFetcher:
    """Returns fixed content and records every URL it was asked to fetch."""

    def __init__(self, fetched: FetchedContent | None = None) -> None:
        self.fetched = fetched or FetchedContent(name="", description="", content="fetched content")
        self.requested_urls: list[str] = []

    async def fetch(self, url: str) -> FetchedContent:
        self.requested_urls.append(url)
        return self.fetched


class FailingContentFetcher:
    async def fetch(self, url: str) -> FetchedContent:
        raise ContentFetchError("boom")


class FakeEnricherService:
    """Returns fixed ExtractedData; records what it was called with.

    `on_call` lets a test inject a side effect (e.g. deleting the row) at the
    point the real LLM call would happen.
    """

    def __init__(
        self,
        data: ExtractedData = ExtractedData(description="generated", tags=["generated"]),
        on_call: Callable[[], None] | None = None,
    ) -> None:
        self.data = data
        self.on_call = on_call
        self.received: list[tuple[str, FetchedContent]] = []

    async def extract_data(self, *, url: str, fetched: FetchedContent) -> ExtractedData:
        self.received.append((url, fetched))
        if self.on_call is not None:
            self.on_call()
        return self.data


class FailingEnricherService:
    async def extract_data(self, *, url: str, fetched: FetchedContent) -> ExtractedData:
        raise EnrichmentError("boom")


@pytest.fixture()
def repo() -> FakeBookmarkRepository:
    return FakeBookmarkRepository()


async def _create(repo: FakeBookmarkRepository, **overrides: object):
    defaults = dict(
        name="A",
        url=f"https://{uuid.uuid4().hex}.com",
        description=None,
        tags=[],
        type=BookmarkType.POST,
    )
    defaults.update(overrides)
    return await bookmark_service.create_bookmark(repo, **defaults)


async def test_fetches_the_bookmark_url(repo: FakeBookmarkRepository) -> None:
    created = await _create(repo, url="https://a.com/article")
    fetcher = FakeContentFetcher()
    enricher = FakeEnricherService()

    await enrich_bookmark(created.id, repo=repo, fetcher=fetcher, enricher=enricher)

    assert fetcher.requested_urls == ["https://a.com/article"]


async def test_passes_fetched_content_to_enricher(repo: FakeBookmarkRepository) -> None:
    created = await _create(repo)
    fetched = FetchedContent(name="Page Title", description="a desc", content="some real content")
    fetcher = FakeContentFetcher(fetched)
    enricher = FakeEnricherService()

    await enrich_bookmark(created.id, repo=repo, fetcher=fetcher, enricher=enricher)

    assert enricher.received == [(created.url, fetched)]


async def test_applies_extracted_data_to_bookmark(repo: FakeBookmarkRepository) -> None:
    created = await _create(repo, description=None, tags=[])
    fetcher = FakeContentFetcher()
    enricher = FakeEnricherService(data=ExtractedData(description="a summary", tags=["python"]))

    result = await enrich_bookmark(created.id, repo=repo, fetcher=fetcher, enricher=enricher)

    assert result is not None
    assert result.description == "a summary"
    assert result.tags == ["python"]


async def test_persists_the_enriched_bookmark(repo: FakeBookmarkRepository) -> None:
    created = await _create(repo)
    fetcher = FakeContentFetcher()
    enricher = FakeEnricherService(data=ExtractedData(description="a summary", tags=["python"]))

    await enrich_bookmark(created.id, repo=repo, fetcher=fetcher, enricher=enricher)

    persisted = await repo.get(created.id)
    assert persisted is not None
    assert persisted.description == "a summary"
    assert persisted.tags == ["python"]


async def test_replaces_placeholder_name_with_fetched_title(
    repo: FakeBookmarkRepository,
) -> None:
    created = await _create(repo, name=None, url="https://www.example.com/article")
    assert created.name == "example.com"  # sanity check: still the URL-derived placeholder
    fetcher = FakeContentFetcher(FetchedContent(name="Real Title", description="", content=""))
    enricher = FakeEnricherService()

    result = await enrich_bookmark(created.id, repo=repo, fetcher=fetcher, enricher=enricher)

    assert result is not None
    assert result.name == "Real Title"


async def test_does_not_replace_a_user_provided_name(repo: FakeBookmarkRepository) -> None:
    created = await _create(repo, name="My chosen name", url="https://www.example.com/article")
    fetcher = FakeContentFetcher(FetchedContent(name="Real Title", description="", content=""))
    enricher = FakeEnricherService()

    result = await enrich_bookmark(created.id, repo=repo, fetcher=fetcher, enricher=enricher)

    assert result is not None
    assert result.name == "My chosen name"


async def test_does_not_replace_placeholder_name_when_fetch_yields_no_title(
    repo: FakeBookmarkRepository,
) -> None:
    created = await _create(repo, name=None, url="https://www.example.com/article")
    fetcher = FakeContentFetcher(FetchedContent(name="", description="", content=""))
    enricher = FakeEnricherService()

    result = await enrich_bookmark(created.id, repo=repo, fetcher=fetcher, enricher=enricher)

    assert result is not None
    assert result.name == "example.com"


async def test_returns_none_when_bookmark_does_not_exist(repo: FakeBookmarkRepository) -> None:
    fetcher = FakeContentFetcher()
    enricher = FakeEnricherService()

    result = await enrich_bookmark(uuid.uuid7(), repo=repo, fetcher=fetcher, enricher=enricher)

    assert result is None
    assert fetcher.requested_urls == []


async def test_returns_none_when_soft_deleted(repo: FakeBookmarkRepository) -> None:
    created = await _create(repo)
    await bookmark_service.delete_bookmark(repo, created.id)
    fetcher = FakeContentFetcher()
    enricher = FakeEnricherService()

    result = await enrich_bookmark(created.id, repo=repo, fetcher=fetcher, enricher=enricher)

    assert result is None
    assert fetcher.requested_urls == []


async def test_fetch_failure_propagates(repo: FakeBookmarkRepository) -> None:
    created = await _create(repo)
    fetcher = FailingContentFetcher()
    enricher = FakeEnricherService()

    with pytest.raises(ContentFetchError):
        await enrich_bookmark(created.id, repo=repo, fetcher=fetcher, enricher=enricher)

    assert enricher.received == []
    persisted = await repo.get(created.id)
    assert persisted is not None
    assert persisted.description is None


async def test_enricher_failure_propagates(repo: FakeBookmarkRepository) -> None:
    created = await _create(repo)
    fetcher = FakeContentFetcher()
    enricher = FailingEnricherService()

    with pytest.raises(EnrichmentError):
        await enrich_bookmark(created.id, repo=repo, fetcher=fetcher, enricher=enricher)

    persisted = await repo.get(created.id)
    assert persisted is not None
    assert persisted.description is None


async def test_raises_not_found_when_deleted_during_enrichment(
    repo: FakeBookmarkRepository,
) -> None:
    created = await _create(repo)
    fetcher = FakeContentFetcher()
    # Simulates the reachable race: a concurrent PUT/DELETE soft-deletes the
    # row (sets deleted_at, doesn't remove it) between the task's get() and
    # save() — repo.save() must not resurrect it.
    enricher = FakeEnricherService(on_call=lambda: repo._rows[created.id].delete())

    with pytest.raises(BookmarkNotFoundError):
        await enrich_bookmark(created.id, repo=repo, fetcher=fetcher, enricher=enricher)
