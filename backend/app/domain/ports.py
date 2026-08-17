"""Ports: abstract interfaces the application layer depends on, implemented by adapters."""

import uuid
from abc import ABC, abstractmethod

from app.domain.models import Bookmark, BookmarkType, ExtractedData


class BookmarkRepository(ABC):
    """Persists domain objects. Carries no business rules of its own.

    Implementations must hide soft-deleted bookmarks (Bookmark.is_deleted) from
    list() and get() — see tests/repository_contract.py, which every adapter's
    test suite must run to prove it honors this.
    """

    @abstractmethod
    async def list(
        self,
        *,
        name: str | None = None,
        type: BookmarkType | None = None,
        tag: str | None = None,
    ) -> list[Bookmark]: ...

    @abstractmethod
    async def get(self, bookmark_id: uuid.UUID) -> Bookmark | None: ...

    @abstractmethod
    async def add(self, bookmark: Bookmark) -> Bookmark: ...

    @abstractmethod
    async def save(self, bookmark: Bookmark) -> Bookmark:
        """Raises BookmarkNotFoundError if the bookmark no longer exists."""
        ...


class ContentFetcher(ABC):
    """Fetches the textual content behind a bookmark's URL."""

    @abstractmethod
    async def fetch(self, url: str) -> str:
        """Raises ContentFetchError on a network failure or non-2xx status."""
        ...


class BookmarkEnricherService(ABC):
    """Derives a description and tags from a bookmark's URL and fetched content.

    Takes url alongside content because the URL (domain, path) is itself a
    useful signal for the provider — passing the full Bookmark instead would
    couple this port to the entity for no real gain.
    """

    @abstractmethod
    async def extract_data(self, *, url: str, content: str) -> ExtractedData:
        """Raises EnrichmentError if the provider fails or its response isn't parseable."""
        ...
