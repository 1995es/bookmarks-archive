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

from app.domain.models import Bookmark, BookmarkType


def make_bookmark(**overrides: object) -> Bookmark:
    defaults: dict[str, object] = dict(
        id=uuid.uuid7(),
        name="A",
        url="https://a.com",
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
