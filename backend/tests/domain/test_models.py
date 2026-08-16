"""Unit tests for domain entities. Pure Python — no framework, no I/O."""

import uuid
from datetime import UTC, datetime

import pytest

from app.domain.models import Bookmark, BookmarkType


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


def test_construct_with_valid_data() -> None:
    bookmark = _bookmark(name="A", url="https://a.com")

    assert bookmark.name == "A"
    assert bookmark.url == "https://a.com"
    assert bookmark.is_deleted is False


def test_created_at_defaults_to_now_when_omitted() -> None:
    bookmark = _bookmark()

    assert bookmark.created_at is not None
    assert bookmark.created_at <= datetime.now(UTC)


def test_empty_name_raises() -> None:
    with pytest.raises(ValueError, match="name"):
        _bookmark(name="")


def test_empty_url_raises() -> None:
    with pytest.raises(ValueError, match="url"):
        _bookmark(url="")


def test_tags_are_defensively_copied() -> None:
    tags = ["python"]
    bookmark = _bookmark(tags=tags)

    tags.append("ruby")

    assert bookmark.tags == ["python"]


def test_delete_sets_deleted_at_and_is_deleted() -> None:
    bookmark = _bookmark()
    assert bookmark.is_deleted is False

    bookmark.delete()

    assert bookmark.is_deleted is True
    assert bookmark.deleted_at is not None
    assert bookmark.deleted_at <= datetime.now(UTC)


def test_validate_accepts_valid_attributes() -> None:
    bookmark = _bookmark(name="A", url="https://a.com", tags=["python"], type=BookmarkType.POST)

    bookmark.name = "B"
    bookmark.url = "https://b.com"
    bookmark.description = "new"
    bookmark.tags = ["ruby"]
    bookmark.type = BookmarkType.VIDEO
    bookmark.validate()

    assert bookmark.name == "B"
    assert bookmark.url == "https://b.com"
    assert bookmark.description == "new"
    assert bookmark.tags == ["ruby"]
    assert bookmark.type == BookmarkType.VIDEO


def test_validate_rejects_empty_name() -> None:
    bookmark = _bookmark()
    bookmark.name = ""

    with pytest.raises(ValueError, match="name"):
        bookmark.validate()
