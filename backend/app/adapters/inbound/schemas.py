"""HTTP DTOs (Pydantic). Translate between the wire format and domain objects."""

from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.domain.models import (
    _MAX_DESCRIPTION_LENGTH,
    _MAX_NAME_LENGTH,
    _MAX_TAG_LENGTH,
    _MAX_TAGS,
    BookmarkType,
    EnrichmentStatus,
)


def _validate_absolute_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("url must be an absolute http(s) URL")
    return url


def _validate_tags(tags: list[str]) -> list[str]:
    for tag in tags:
        if not tag or len(tag) > _MAX_TAG_LENGTH:
            raise ValueError(f"each tag must be 1-{_MAX_TAG_LENGTH} characters")
    return tags


class BookmarkBase(BaseModel):
    name: str = Field(min_length=1, max_length=_MAX_NAME_LENGTH)
    url: str = Field(min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=_MAX_DESCRIPTION_LENGTH)
    tags: list[str] = Field(default_factory=list, max_length=_MAX_TAGS)
    type: BookmarkType

    @field_validator("url")
    @classmethod
    def _url_must_be_absolute_http(cls, url: str) -> str:
        return _validate_absolute_http_url(url)

    @field_validator("tags")
    @classmethod
    def _tags_must_be_nonempty_and_bounded(cls, tags: list[str]) -> list[str]:
        return _validate_tags(tags)


class BookmarkCreate(BaseModel):
    """Only `url` is required. A blank/omitted `name` is derived server-side from the
    URL's host; an omitted `type` defaults to 'post'."""

    name: str | None = Field(default=None, max_length=_MAX_NAME_LENGTH)
    url: str = Field(min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=_MAX_DESCRIPTION_LENGTH)
    tags: list[str] = Field(default_factory=list, max_length=_MAX_TAGS)
    type: BookmarkType = BookmarkType.POST

    @field_validator("name")
    @classmethod
    def _blank_name_becomes_none(cls, name: str | None) -> str | None:
        if name is not None and not name.strip():
            return None
        return name

    @field_validator("url")
    @classmethod
    def _url_must_be_absolute_http(cls, url: str) -> str:
        return _validate_absolute_http_url(url)

    @field_validator("tags")
    @classmethod
    def _tags_must_be_nonempty_and_bounded(cls, tags: list[str]) -> list[str]:
        return _validate_tags(tags)


class BookmarkUpdate(BookmarkBase):
    pass


class BookmarkRead(BookmarkBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    enrichment_status: EnrichmentStatus

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
