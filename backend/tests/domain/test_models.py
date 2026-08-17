"""Unit tests for domain entities. Pure Python — no framework, no I/O."""

import uuid
from datetime import UTC, datetime

import pytest

from app.domain.models import (
    _MAX_DESCRIPTION_LENGTH,
    _MAX_TAG_LENGTH,
    Bookmark,
    BookmarkType,
    ExtractedData,
)


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


def test_enrich_sets_description_when_empty() -> None:
    bookmark = _bookmark(description=None)

    bookmark.enrich(ExtractedData(description="generated summary", tags=[]))

    assert bookmark.description == "generated summary"


def test_enrich_appends_to_existing_description() -> None:
    bookmark = _bookmark(description="un artículo")

    bookmark.enrich(ExtractedData(description="generated summary", tags=[]))

    assert "un artículo" in bookmark.description
    assert "generated summary" in bookmark.description


def test_enrich_appends_tags_preserving_user_tags() -> None:
    bookmark = _bookmark(tags=["python"])

    bookmark.enrich(ExtractedData(description="d", tags=["web"]))

    assert bookmark.tags == ["python", "web"]


def test_enrich_does_not_duplicate_tags() -> None:
    bookmark = _bookmark(tags=["python"])

    bookmark.enrich(ExtractedData(description="d", tags=["python", "web"]))

    assert bookmark.tags == ["python", "web"]


def test_enrich_truncates_at_max_tags() -> None:
    bookmark = _bookmark(tags=[f"tag{i}" for i in range(45)])

    bookmark.enrich(ExtractedData(description="d", tags=[f"new{i}" for i in range(20)]))

    assert len(bookmark.tags) == 50
    assert bookmark.tags[:45] == [f"tag{i}" for i in range(45)]


def test_enrich_truncates_oversized_tags() -> None:
    bookmark = _bookmark(tags=[])
    long_tag = "x" * (_MAX_TAG_LENGTH + 10)

    bookmark.enrich(ExtractedData(description="d", tags=[long_tag]))

    assert bookmark.tags == [long_tag[:_MAX_TAG_LENGTH]]


def test_enrich_drops_empty_tags() -> None:
    bookmark = _bookmark(tags=[])

    bookmark.enrich(ExtractedData(description="d", tags=["", "python"]))

    assert bookmark.tags == ["python"]


def test_enrich_truncates_oversized_description() -> None:
    bookmark = _bookmark(description=None)
    long_description = "x" * (_MAX_DESCRIPTION_LENGTH + 500)

    bookmark.enrich(ExtractedData(description=long_description, tags=[]))

    assert len(bookmark.description) == _MAX_DESCRIPTION_LENGTH


def test_enrich_truncates_merged_description_over_limit() -> None:
    bookmark = _bookmark(description="x" * (_MAX_DESCRIPTION_LENGTH - 10))

    bookmark.enrich(ExtractedData(description="y" * 100, tags=[]))

    assert len(bookmark.description) == _MAX_DESCRIPTION_LENGTH


def test_enrich_revalidates_invariants() -> None:
    bookmark = _bookmark()
    bookmark.name = ""

    with pytest.raises(ValueError, match="name"):
        bookmark.enrich(ExtractedData(description="d", tags=[]))


def test_enrich_does_not_touch_name_url_type() -> None:
    bookmark = _bookmark(name="A", url="https://a.com", type=BookmarkType.VIDEO)

    bookmark.enrich(ExtractedData(description="d", tags=["x"]))

    assert bookmark.name == "A"
    assert bookmark.url == "https://a.com"
    assert bookmark.type == BookmarkType.VIDEO
