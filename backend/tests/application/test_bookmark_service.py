"""Unit tests for the application layer, using an in-memory fake repository.

No database or FastAPI involved — this is the payoff of depending on a port:
business orchestration (e.g. tag filtering) is testable in isolation.
"""

import uuid

import pytest

from app.application import bookmark_service
from app.domain.models import Bookmark, BookmarkType
from tests.repository_contract import (  # noqa: F401 - collected as tests in this module
    test_add_then_get_returns_the_bookmark,
    test_get_returns_none_for_soft_deleted,
    test_get_returns_none_for_unknown_id,
    test_list_excludes_soft_deleted,
)


class FakeBookmarkRepository:
    """In-memory BookmarkRepository implementation for tests."""

    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, Bookmark] = {}

    async def list(
        self,
        *,
        name: str | None = None,
        type: BookmarkType | None = None,
        tag: str | None = None,
    ) -> list[Bookmark]:
        rows = [b for b in self._rows.values() if not b.is_deleted]
        if name is not None:
            rows = [b for b in rows if name.lower() in b.name.lower()]
        if type is not None:
            rows = [b for b in rows if b.type == type]
        if tag is not None:
            rows = [b for b in rows if tag in b.tags]
        return rows

    async def get(self, bookmark_id: uuid.UUID) -> Bookmark | None:
        bookmark = self._rows.get(bookmark_id)
        if bookmark is None or bookmark.is_deleted:
            return None
        return bookmark

    async def add(self, bookmark: Bookmark) -> Bookmark:
        self._rows[bookmark.id] = bookmark
        return bookmark

    async def save(self, bookmark: Bookmark) -> Bookmark:
        self._rows[bookmark.id] = bookmark
        return bookmark


@pytest.fixture()
def repo() -> FakeBookmarkRepository:
    return FakeBookmarkRepository()


async def _create(repo: FakeBookmarkRepository, **overrides: object) -> Bookmark:
    defaults = dict(
        name="A", url="https://a.com", description=None, tags=[], type=BookmarkType.POST
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
