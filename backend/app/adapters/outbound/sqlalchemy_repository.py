"""SQLAlchemy adapter implementing the BookmarkRepository port."""

import uuid

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.outbound.database import get_db
from app.adapters.outbound.orm import BookmarkRow
from app.domain.exceptions import BookmarkNotFoundError
from app.domain.models import Bookmark, BookmarkType
from app.domain.ports import BookmarkRepository, SortField, SortOrder

_SORT_COLUMNS = {"name": BookmarkRow.name, "created_at": BookmarkRow.created_at}


def _to_domain(row: BookmarkRow) -> Bookmark:
    return Bookmark(
        id=row.id,
        name=row.name,
        url=row.url,
        description=row.description,
        tags=list(row.tags),
        type=row.type,
        created_at=row.created_at,
        deleted_at=row.deleted_at,
    )


def _apply_filters(stmt, *, name: str | None, type: BookmarkType | None, tag: str | None):
    stmt = stmt.where(BookmarkRow.deleted_at.is_(None))
    if name is not None:
        stmt = stmt.where(BookmarkRow.name.ilike(f"%{name}%"))
    if type is not None:
        stmt = stmt.where(BookmarkRow.type == type)
    if tag is not None:
        tag_value = func.json_each(BookmarkRow.tags).table_valued("value")
        stmt = stmt.where(select(1).select_from(tag_value).where(tag_value.c.value == tag).exists())
    return stmt


def _copy_into_row(bookmark: Bookmark, row: BookmarkRow) -> None:
    row.id = bookmark.id
    row.name = bookmark.name
    row.url = bookmark.url
    row.description = bookmark.description
    row.tags = bookmark.tags
    row.type = bookmark.type
    row.created_at = bookmark.created_at
    row.deleted_at = bookmark.deleted_at


class SqlAlchemyBookmarkRepository(BookmarkRepository):
    """Outbound adapter: implements BookmarkRepository against SQLite via SQLAlchemy asyncio."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list(
        self,
        *,
        name: str | None = None,
        type: BookmarkType | None = None,
        tag: str | None = None,
        sort_by: SortField = "created_at",
        sort_order: SortOrder = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Bookmark]:
        stmt = _apply_filters(select(BookmarkRow), name=name, type=type, tag=tag)
        column = _SORT_COLUMNS[sort_by]
        stmt = stmt.order_by(column.desc() if sort_order == "desc" else column.asc())
        stmt = stmt.limit(limit).offset(offset)
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_to_domain(row) for row in rows]

    async def count(
        self,
        *,
        name: str | None = None,
        type: BookmarkType | None = None,
        tag: str | None = None,
    ) -> int:
        stmt = _apply_filters(
            select(func.count()).select_from(BookmarkRow), name=name, type=type, tag=tag
        )
        return (await self._db.execute(stmt)).scalar_one()

    async def get(self, bookmark_id: uuid.UUID) -> Bookmark | None:
        stmt = select(BookmarkRow).where(
            BookmarkRow.id == bookmark_id, BookmarkRow.deleted_at.is_(None)
        )
        row = (await self._db.execute(stmt)).scalars().first()
        return _to_domain(row) if row is not None else None

    async def add(self, bookmark: Bookmark) -> Bookmark:
        row = BookmarkRow()
        _copy_into_row(bookmark, row)
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return _to_domain(row)

    async def save(self, bookmark: Bookmark) -> Bookmark:
        row = await self._db.get(BookmarkRow, bookmark.id)
        if row is None:
            raise BookmarkNotFoundError(bookmark.id)
        if row.deleted_at is not None and not bookmark.is_deleted:
            # Soft-deleted concurrently since this bookmark was read (e.g. a
            # background enrichment racing a DELETE): treat like a missing row
            # rather than silently resurrecting it.
            raise BookmarkNotFoundError(bookmark.id)
        _copy_into_row(bookmark, row)
        await self._db.commit()
        await self._db.refresh(row)
        return _to_domain(row)


def get_repository(db: AsyncSession = Depends(get_db)) -> BookmarkRepository:
    return SqlAlchemyBookmarkRepository(db)
