"""Shared behavioral contract for BookmarkRepository implementations.

The 'soft-deleted bookmarks are invisible to list()/get()' rule is part of the
BookmarkRepository port's contract (see app/domain/ports.py) but each adapter
implements the filtering itself. Importing these test functions into an
adapter's own test module (pytest collects imported test_* functions in the
module they're imported into, binding them to that module's `repo` fixture)
means every adapter's test suite proves it honors the rule, instead of the
rule being duplicated and unguarded per adapter.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.domain.exceptions import BookmarkNotFoundError, BookmarkUrlConflictError
from app.domain.models import Bookmark, BookmarkType


def make_bookmark(**overrides: object) -> Bookmark:
    defaults: dict[str, object] = dict(
        id=uuid.uuid7(),
        name="A",
        # Unique by default so tests that add several bookmarks don't trip the
        # url-uniqueness contract; pass url= explicitly when it's under test.
        url=f"https://{uuid.uuid4().hex}.com",
        description=None,
        tags=[],
        type=BookmarkType.POST,
    )
    defaults.update(overrides)
    return Bookmark(**defaults)


async def test_get_returns_none_for_unknown_id(repo) -> None:
    assert await repo.get(uuid.uuid7()) is None


async def test_add_then_get_returns_the_bookmark(repo) -> None:
    added = await repo.add(make_bookmark(name="A"))

    assert await repo.get(added.id) == added


async def test_list_excludes_soft_deleted(repo) -> None:
    kept = await repo.add(make_bookmark(name="Kept"))
    deleted = await repo.add(make_bookmark(name="Deleted"))
    deleted.delete()
    await repo.save(deleted)

    result = await repo.list()

    assert [b.name for b in result] == [kept.name]


async def test_get_returns_none_for_soft_deleted(repo) -> None:
    added = await repo.add(make_bookmark())
    added.delete()
    await repo.save(added)

    assert await repo.get(added.id) is None


async def test_list_defaults_to_created_at_descending(repo) -> None:
    first = await repo.add(make_bookmark(name="First", created_at=datetime(2024, 1, 1, tzinfo=UTC)))
    second = await repo.add(
        make_bookmark(name="Second", created_at=datetime(2024, 1, 2, tzinfo=UTC))
    )

    result = await repo.list()

    assert [b.id for b in result] == [second.id, first.id]


async def test_list_sorts_by_name_ascending(repo) -> None:
    await repo.add(make_bookmark(name="Banana"))
    await repo.add(make_bookmark(name="Apple"))

    result = await repo.list(sort_by="name", sort_order="asc")

    assert [b.name for b in result] == ["Apple", "Banana"]


async def test_list_respects_limit_and_offset(repo) -> None:
    await repo.add(make_bookmark(name="Apple"))
    await repo.add(make_bookmark(name="Banana"))
    await repo.add(make_bookmark(name="Cherry"))

    page = await repo.list(sort_by="name", sort_order="asc", limit=1, offset=1)

    assert [b.name for b in page] == ["Banana"]


async def test_count_ignores_limit_and_offset_but_respects_filters(repo) -> None:
    await repo.add(make_bookmark(name="A", tags=["python"]))
    await repo.add(make_bookmark(name="B", tags=["ruby"]))

    assert await repo.count() == 2
    assert await repo.count(tag="python") == 1


async def test_count_excludes_soft_deleted(repo) -> None:
    kept = await repo.add(make_bookmark(name="Kept"))
    deleted = await repo.add(make_bookmark(name="Deleted"))
    deleted.delete()
    await repo.save(deleted)

    assert await repo.count() == 1
    assert kept.name == "Kept"


async def test_add_rejects_duplicate_live_url(repo) -> None:
    await repo.add(make_bookmark(url="https://dup.com"))

    with pytest.raises(BookmarkUrlConflictError):
        await repo.add(make_bookmark(url="https://dup.com"))


async def test_add_allows_reusing_a_soft_deleted_url(repo) -> None:
    first = await repo.add(make_bookmark(url="https://reuse.com"))
    first.delete()
    await repo.save(first)

    revived = await repo.add(make_bookmark(url="https://reuse.com"))

    assert revived.url == "https://reuse.com"
    assert await repo.get(revived.id) is not None


async def test_save_rejects_updating_url_to_another_live_url(repo) -> None:
    await repo.add(make_bookmark(url="https://taken.com"))
    other = await repo.add(make_bookmark(url="https://free.com"))
    other.update(
        name=other.name,
        url="https://taken.com",
        description=None,
        tags=[],
        type=BookmarkType.POST,
    )

    with pytest.raises(BookmarkUrlConflictError):
        await repo.save(other)


async def test_save_raises_not_found_when_deleted_concurrently(repo) -> None:
    """A save() based on a pre-delete read must not resurrect a soft-deleted row.

    `stale` stands in for a bookmark instance read before a concurrent delete
    (e.g. by a background task) — same id, but built fresh so it doesn't alias
    `added` the way a second repo.get() would on an in-memory fake.
    """
    added = await repo.add(make_bookmark())
    stale = make_bookmark(id=added.id)
    added.delete()
    await repo.save(added)

    with pytest.raises(BookmarkNotFoundError):
        await repo.save(stale)
