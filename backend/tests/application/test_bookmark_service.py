"""Unit tests for the application layer, using an in-memory fake repository.

No database or FastAPI involved — this is the payoff of depending on a port:
business orchestration (e.g. tag filtering) is testable in isolation.
"""

import uuid

import pytest

from app.application import bookmark_service
from app.domain.exceptions import BookmarkEnrichmentNotFailedError
from app.domain.models import Bookmark, BookmarkType, EnrichmentStatus
from tests.fakes import FakeBookmarkRepository
from tests.repository_contract import (  # noqa: F401 - collected as tests in this module
    test_add_allows_reusing_a_soft_deleted_url,
    test_add_rejects_duplicate_live_url,
    test_add_then_get_returns_the_bookmark,
    test_count_excludes_soft_deleted,
    test_count_ignores_limit_and_offset_but_respects_filters,
    test_get_returns_none_for_soft_deleted,
    test_get_returns_none_for_unknown_id,
    test_list_defaults_to_created_at_descending,
    test_list_excludes_soft_deleted,
    test_list_respects_limit_and_offset,
    test_list_sorts_by_name_ascending,
    test_save_raises_not_found_when_deleted_concurrently,
    test_save_rejects_updating_url_to_another_live_url,
)


@pytest.fixture()
def repo() -> FakeBookmarkRepository:
    return FakeBookmarkRepository()


async def _create(repo: FakeBookmarkRepository, **overrides: object) -> Bookmark:
    defaults = dict(
        name="A",
        url=f"https://{uuid.uuid4().hex}.com",
        description=None,
        tags=[],
        type=BookmarkType.POST,
    )
    defaults.update(overrides)
    return await bookmark_service.create_bookmark(repo, **defaults)


async def test_list_filters_by_exact_tag(repo: FakeBookmarkRepository) -> None:
    await _create(repo, name="A", tags=["python"])
    await _create(repo, name="B", tags=["ruby"])

    result = await bookmark_service.list_bookmarks(repo, tag="python")

    assert [b.name for b in result] == ["A"]


async def test_list_tag_filter_is_exact_not_substring(repo: FakeBookmarkRepository) -> None:
    await _create(repo, name="A", tags=["python"])

    result = await bookmark_service.list_bookmarks(repo, tag="py")

    assert result == []


async def test_create_delegates_to_repository(repo: FakeBookmarkRepository) -> None:
    bookmark = await _create(repo, name="A", type=BookmarkType.SITE)

    assert isinstance(bookmark.id, uuid.UUID)
    assert bookmark.id.version == 7
    assert await repo.get(bookmark.id) == bookmark


async def test_create_rejects_empty_name(repo: FakeBookmarkRepository) -> None:
    with pytest.raises(ValueError, match="name"):
        await _create(repo, name="")


async def test_create_without_name_derives_it_from_url_host(
    repo: FakeBookmarkRepository,
) -> None:
    bookmark = await _create(repo, name=None, url="https://www.example.com/article")

    assert bookmark.name == "example.com"


async def test_create_without_type_defaults_to_post(repo: FakeBookmarkRepository) -> None:
    bookmark = await bookmark_service.create_bookmark(
        repo, url="https://a.com", description=None, tags=[]
    )

    assert bookmark.type == BookmarkType.POST
    assert bookmark.name == "a.com"


async def test_update_acts_on_fetched_domain_object(repo: FakeBookmarkRepository) -> None:
    created = await _create(repo, name="A", tags=["python"], type=BookmarkType.POST)

    updated = await bookmark_service.update_bookmark(
        repo,
        created.id,
        name="B",
        url="https://b.com",
        description="updated",
        tags=["ruby"],
        type=BookmarkType.VIDEO,
    )

    assert updated.name == "B"
    assert updated.tags == ["ruby"]
    assert updated.type == BookmarkType.VIDEO
    assert updated.id == created.id


async def test_update_unknown_id_returns_none(repo: FakeBookmarkRepository) -> None:
    result = await bookmark_service.update_bookmark(
        repo,
        uuid.uuid7(),
        name="A",
        url="https://a.com",
        description=None,
        tags=[],
        type=BookmarkType.POST,
    )
    assert result is None


async def test_delete_sets_deleted_at_via_domain_object(repo: FakeBookmarkRepository) -> None:
    created = await _create(repo)

    assert await bookmark_service.delete_bookmark(repo, created.id) is True

    stored = repo._rows[created.id]
    assert stored.is_deleted
    assert stored.deleted_at is not None


async def test_delete_unknown_id_returns_false(repo: FakeBookmarkRepository) -> None:
    assert await bookmark_service.delete_bookmark(repo, uuid.uuid7()) is False


async def test_retry_enrichment_resets_failed_bookmark_to_pending(
    repo: FakeBookmarkRepository,
) -> None:
    created = await _create(repo)
    stored = repo._rows[created.id]
    stored.mark_enrichment_failed()

    result = await bookmark_service.retry_enrichment(repo, created.id)

    assert result is not None
    assert result.enrichment_status == EnrichmentStatus.PENDING


async def test_retry_enrichment_rejects_non_failed_bookmark(
    repo: FakeBookmarkRepository,
) -> None:
    created = await _create(repo)

    with pytest.raises(BookmarkEnrichmentNotFailedError):
        await bookmark_service.retry_enrichment(repo, created.id)


async def test_retry_enrichment_unknown_id_returns_none(repo: FakeBookmarkRepository) -> None:
    assert await bookmark_service.retry_enrichment(repo, uuid.uuid7()) is None
