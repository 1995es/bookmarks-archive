"""Tests for the SQLAlchemy adapter implementing the BookmarkRepository port.

Exercises the outbound (driven) adapter directly against a real SQLite
database, without going through the HTTP layer.
"""

import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.outbound.database import Base
from app.adapters.outbound.orm import BookmarkRow
from app.adapters.outbound.sqlalchemy_repository import SqlAlchemyBookmarkRepository
from app.domain.exceptions import BookmarkNotFoundError
from app.domain.models import Bookmark, BookmarkType
from tests.repository_contract import (  # noqa: F401 - collected as tests in this module
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
)


@pytest.fixture()
async def session() -> AsyncGenerator[AsyncSession]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}", connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    TestingSessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        await db.close()
        await engine.dispose()
        os.remove(path)


@pytest.fixture()
def repo(session: AsyncSession) -> SqlAlchemyBookmarkRepository:
    return SqlAlchemyBookmarkRepository(session)


def _bookmark(**overrides: object) -> Bookmark:
    defaults = dict(
        id=uuid.uuid7(),
        name="A",
        url="https://a.com",
        description=None,
        tags=[],
        type=BookmarkType.POST,
    )
    defaults.update(overrides)
    return Bookmark(**defaults)


async def test_add_persists_and_returns_bookmark_with_created_at(
    repo: SqlAlchemyBookmarkRepository,
) -> None:
    added = await repo.add(_bookmark(name="A"))

    assert added.name == "A"
    assert isinstance(added.created_at, datetime)


async def test_get_returns_persisted_bookmark(repo: SqlAlchemyBookmarkRepository) -> None:
    added = await repo.add(_bookmark(name="A", tags=["python"]))

    fetched = await repo.get(added.id)

    assert fetched is not None
    assert fetched.name == "A"
    assert fetched.tags == ["python"]


async def test_list_filters_by_type(repo: SqlAlchemyBookmarkRepository) -> None:
    await repo.add(_bookmark(name="A", type=BookmarkType.POST))
    await repo.add(_bookmark(name="B", type=BookmarkType.VIDEO))

    result = await repo.list(type=BookmarkType.VIDEO)

    assert [b.name for b in result] == ["B"]


async def test_list_filters_by_name_case_insensitive_substring(
    repo: SqlAlchemyBookmarkRepository,
) -> None:
    await repo.add(_bookmark(name="Python Tutorial"))
    await repo.add(_bookmark(name="Ruby Guide"))

    result = await repo.list(name="python")

    assert [b.name for b in result] == ["Python Tutorial"]


async def test_list_filters_by_tag_exact_not_substring(repo: SqlAlchemyBookmarkRepository) -> None:
    await repo.add(_bookmark(name="A", tags=["python"]))
    await repo.add(_bookmark(name="B", tags=["py"]))

    result = await repo.list(tag="python")

    assert [b.name for b in result] == ["A"]


async def test_list_combines_name_type_and_tag_filters(repo: SqlAlchemyBookmarkRepository) -> None:
    await repo.add(_bookmark(name="Python Tutorial", type=BookmarkType.VIDEO, tags=["python"]))
    await repo.add(_bookmark(name="Python Article", type=BookmarkType.POST, tags=["python"]))
    await repo.add(_bookmark(name="Python Tutorial", type=BookmarkType.VIDEO, tags=["ruby"]))
    await repo.add(_bookmark(name="Ruby Tutorial", type=BookmarkType.VIDEO, tags=["python"]))

    result = await repo.list(name="python", type=BookmarkType.VIDEO, tag="python")

    assert len(result) == 1
    assert result[0].name == "Python Tutorial"
    assert result[0].type == BookmarkType.VIDEO
    assert result[0].tags == ["python"]


async def test_save_updates_existing_row(repo: SqlAlchemyBookmarkRepository) -> None:
    added = await repo.add(_bookmark(name="A"))
    added.update(
        name="B",
        url="https://b.com",
        description=None,
        tags=["x"],
        type=BookmarkType.SITE,
    )

    saved = await repo.save(added)

    assert saved.name == "B"
    assert saved.tags == ["x"]
    assert saved.type == BookmarkType.SITE
    refetched = await repo.get(added.id)
    assert refetched is not None
    assert refetched.name == "B"


async def test_save_unknown_id_raises(repo: SqlAlchemyBookmarkRepository) -> None:
    with pytest.raises(BookmarkNotFoundError, match="does not exist"):
        await repo.save(_bookmark())


async def test_soft_deleted_row_still_exists_in_database(
    repo: SqlAlchemyBookmarkRepository, session: AsyncSession
) -> None:
    """repo.get()/list() hide soft-deleted bookmarks, but the row is never removed."""
    added = await repo.add(_bookmark())
    added.delete()
    await repo.save(added)

    assert await repo.get(added.id) is None
    row = await session.get(BookmarkRow, added.id)
    assert row is not None
    assert row.deleted_at is not None


async def test_sqlite_returns_naive_created_at(repo: SqlAlchemyBookmarkRepository) -> None:
    """SQLite has no real timezone storage: a DateTime(timezone=True) column round-trips
    as a naive datetime even though it was written as UTC. The inbound schema layer
    (BookmarkRead.serialize_created_at) is what compensates for this."""
    added = await repo.add(_bookmark())

    fetched = await repo.get(added.id)

    assert fetched is not None
    assert fetched.created_at is not None
    assert fetched.created_at.tzinfo is None
