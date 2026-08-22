"""Ports: abstract interfaces the application layer depends on, implemented by adapters."""

import uuid
from abc import ABC, abstractmethod
from typing import Literal

from app.domain.models import Bookmark, BookmarkType, ExtractedData, FetchedContent

SortField = Literal["name", "created_at"]
SortOrder = Literal["asc", "desc"]


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
        sort_by: SortField = "created_at",
        sort_order: SortOrder = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Bookmark]: ...

    @abstractmethod
    async def count(
        self,
        *,
        name: str | None = None,
        type: BookmarkType | None = None,
        tag: str | None = None,
    ) -> int:
        """Count of bookmarks matching the filters, ignoring limit/offset — the total
        `list()` would paginate over."""
        ...

    @abstractmethod
    async def get(self, bookmark_id: uuid.UUID) -> Bookmark | None: ...

    @abstractmethod
    async def add(self, bookmark: Bookmark) -> Bookmark: ...

    @abstractmethod
    async def save(self, bookmark: Bookmark) -> Bookmark:
        """Raises BookmarkNotFoundError if the bookmark no longer exists."""
        ...


class ContentFetcher(ABC):
    """Fetches and extracts the structured content behind a bookmark's URL."""

    @abstractmethod
    async def fetch(self, url: str) -> FetchedContent:
        """Raises ContentFetchError on a network failure or non-2xx status."""
        ...


class BookmarkEnricherService(ABC):
    """Derives a description and tags from a bookmark's URL and fetched content.

    Takes url alongside the fetched content because the URL (domain, path) is
    itself a useful signal for the provider — passing the full Bookmark instead
    would couple this port to the entity for no real gain. The fetched page's
    own title/description are passed alongside its body text so the provider
    has more context than the body alone would give it.
    """

    @abstractmethod
    async def extract_data(self, *, url: str, fetched: FetchedContent) -> ExtractedData:
        """Raises EnrichmentError if the provider fails or its response isn't parseable."""
        ...
