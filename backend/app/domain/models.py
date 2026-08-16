"""Domain entities. No SQLAlchemy, no Pydantic, no framework imports."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from app.domain.exceptions import BookmarkInvalidError


class BookmarkType(str, Enum):
    POST = "post"
    VIDEO = "video"
    TWEET = "tweet"
    SITE = "site"


@dataclass
class Bookmark:
    id: UUID
    name: str
    url: str
    description: str | None
    tags: list[str]
    type: BookmarkType
    created_at: datetime | None = None
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        self.tags = list(self.tags)
        if self.created_at is None:
            self.created_at = datetime.now(UTC)
        self.validate()

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def delete(self) -> None:
        """Mark the bookmark as deleted. The sole authority on what deletion means."""
        self.deleted_at = datetime.now(UTC)

    def update(
        self,
        *,
        name: str,
        url: str,
        description: str | None,
        tags: list[str],
        type: BookmarkType,
    ) -> None:
        """Replace the mutable fields and re-check invariants atomically.

        The only sanctioned way to change these fields after construction: it
        guarantees an invalid state can never be assigned without validation,
        unlike setting attributes directly.
        """
        self.name = name
        self.url = url
        self.description = description
        self.tags = list(tags)
        self.type = type
        self.validate()

    def validate(self) -> None:
        if not self.name:
            raise BookmarkInvalidError("name must not be empty")
        if not self.url:
            raise BookmarkInvalidError("url must not be empty")
