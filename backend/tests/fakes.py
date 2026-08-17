"""Shared in-memory fakes for application-layer tests. No database, no FastAPI."""

import copy
import uuid

from app.domain.exceptions import BookmarkNotFoundError
from app.domain.models import Bookmark, BookmarkType
from app.domain.ports import BookmarkRepository


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
        return [copy.deepcopy(b) for b in rows]

    async def get(self, bookmark_id: uuid.UUID) -> Bookmark | None:
        bookmark = self._rows.get(bookmark_id)
        if bookmark is None or bookmark.is_deleted:
            return None
        return copy.deepcopy(bookmark)

    async def add(self, bookmark: Bookmark) -> Bookmark:
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
        self._rows[bookmark.id] = bookmark
        return bookmark
