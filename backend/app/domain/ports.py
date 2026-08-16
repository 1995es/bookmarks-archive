"""Ports: abstract interfaces the application layer depends on, implemented by adapters."""

import uuid
from typing import Protocol

from app.domain.models import Bookmark, BookmarkType


class BookmarkRepository(Protocol):
    """Persists domain objects. Carries no business rules of its own.

    Implementations must hide soft-deleted bookmarks (Bookmark.is_deleted) from
    list() and get() — see tests/repository_contract.py, which every adapter's
    test suite must run to prove it honors this.
    """

    async def list(
        self,
        *,
        name: str | None = None,
        type: BookmarkType | None = None,
        tag: str | None = None,
    ) -> list[Bookmark]: ...

    async def get(self, bookmark_id: uuid.UUID) -> Bookmark | None: ...

    async def add(self, bookmark: Bookmark) -> Bookmark: ...

    async def save(self, bookmark: Bookmark) -> Bookmark:
        """Raises BookmarkNotFoundError if the bookmark no longer exists."""
        ...
