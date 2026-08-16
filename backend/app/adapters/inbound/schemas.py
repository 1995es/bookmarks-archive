"""HTTP DTOs (Pydantic). Translate between the wire format and domain objects."""

from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.domain.models import BookmarkType

_MAX_TAGS = 50
_MAX_TAG_LENGTH = 50


class BookmarkBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=_MAX_TAGS)
    type: BookmarkType

    @field_validator("url")
    @classmethod
    def _url_must_be_absolute_http(cls, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("url must be an absolute http(s) URL")
        return url

    @field_validator("tags")
    @classmethod
    def _tags_must_be_nonempty_and_bounded(cls, tags: list[str]) -> list[str]:
        for tag in tags:
            if not tag or len(tag) > _MAX_TAG_LENGTH:
                raise ValueError(f"each tag must be 1-{_MAX_TAG_LENGTH} characters")
        return tags


class BookmarkCreate(BookmarkBase):
    pass


class BookmarkUpdate(BookmarkBase):
    pass


class BookmarkRead(BookmarkBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
