"""Shared in-memory fakes for application-layer tests. No database, no FastAPI."""

import copy
import uuid

from app.domain.exceptions import BookmarkNotFoundError, BookmarkUrlConflictError
from app.domain.models import Bookmark, BookmarkType
from app.domain.ports import BookmarkRepository, SortField, SortOrder


class FakeBookmarkRepository(BookmarkRepository):
    """In-memory BookmarkRepository implementation for tests.

    `get`/`list` hand back deep copies, not the stored instance, so mutating a
    returned `Bookmark` without calling `save()` has no effect — matching
    SqlAlchemyBookmarkRepository, which always builds a fresh domain object
    from the row. This also means two `get()` calls for the same id are
    independent snapshots, which concurrent-write races rely on.
    """

    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, Bookmark] = {}

    def _filtered(
        self,
        *,
        name: str | None,
        type: BookmarkType | None,
        tag: str | None,
    ) -> list[Bookmark]:
        rows = [b for b in self._rows.values() if not b.is_deleted]
        if name is not None:
            rows = [b for b in rows if name.lower() in b.name.lower()]
        if type is not None:
            rows = [b for b in rows if b.type == type]
        if tag is not None:
            rows = [b for b in rows if tag in b.tags]
        return rows

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
        rows = self._filtered(name=name, type=type, tag=tag)
        key = (lambda b: b.name.lower()) if sort_by == "name" else (lambda b: b.created_at)
        rows.sort(key=key, reverse=sort_order == "desc")
        rows = rows[offset : offset + limit]
        return [copy.deepcopy(b) for b in rows]

    async def count(
        self,
        *,
        name: str | None = None,
        type: BookmarkType | None = None,
        tag: str | None = None,
    ) -> int:
        return len(self._filtered(name=name, type=type, tag=tag))

    async def get(self, bookmark_id: uuid.UUID) -> Bookmark | None:
        bookmark = self._rows.get(bookmark_id)
        if bookmark is None or bookmark.is_deleted:
            return None
        return copy.deepcopy(bookmark)

    def _url_taken_by_other_live(self, bookmark: Bookmark) -> bool:
        # Mirrors the partial unique index on BookmarkRow.url: a url is taken only
        # if another *live* bookmark holds it. Reusing a soft-deleted url is allowed.
        return any(
            b.id != bookmark.id and not b.is_deleted and b.url == bookmark.url
            for b in self._rows.values()
        )

    async def add(self, bookmark: Bookmark) -> Bookmark:
        if self._url_taken_by_other_live(bookmark):
            raise BookmarkUrlConflictError(bookmark.url)
        self._rows[bookmark.id] = bookmark
        return bookmark

    async def save(self, bookmark: Bookmark) -> Bookmark:
        existing = self._rows.get(bookmark.id)
        if existing is None:
            raise BookmarkNotFoundError(bookmark.id)
        if existing.is_deleted and not bookmark.is_deleted:
            # Soft-deleted concurrently since this bookmark was read; matches
            # SqlAlchemyBookmarkRepository.save() so the race is testable
            # without a database.
            raise BookmarkNotFoundError(bookmark.id)
        if not bookmark.is_deleted and self._url_taken_by_other_live(bookmark):
            raise BookmarkUrlConflictError(bookmark.url)
        self._rows[bookmark.id] = bookmark
        return bookmark
