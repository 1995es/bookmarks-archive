"""Bookmark use cases. Depend only on the BookmarkRepository port, never on a concrete adapter."""

import uuid
from urllib.parse import urlparse

from app.domain.models import Bookmark, BookmarkType
from app.domain.ports import BookmarkRepository


def derive_name_from_url(url: str) -> str:
    """Fallback name for the url-only fast path: the URL's host, minus a leading www."""
    hostname = urlparse(url).hostname or url
    return hostname.removeprefix("www.")


async def list_bookmarks(
    repo: BookmarkRepository,
    *,
    name: str | None = None,
    tag: str | None = None,
    type: BookmarkType | None = None,
) -> list[Bookmark]:
    return await repo.list(name=name, type=type, tag=tag)


async def get_bookmark(repo: BookmarkRepository, bookmark_id: uuid.UUID) -> Bookmark | None:
    return await repo.get(bookmark_id)


async def create_bookmark(
    repo: BookmarkRepository,
    *,
    url: str,
    name: str | None = None,
    description: str | None,
    tags: list[str],
    type: BookmarkType = BookmarkType.POST,
) -> Bookmark:
    bookmark = Bookmark(
        id=uuid.uuid7(),
        name=name if name is not None else derive_name_from_url(url),
        url=url,
        description=description,
        tags=tags,
        type=type,
    )
    return await repo.add(bookmark)


async def update_bookmark(
    repo: BookmarkRepository,
    bookmark_id: uuid.UUID,
    *,
    name: str,
    url: str,
    description: str | None,
    tags: list[str],
    type: BookmarkType,
) -> Bookmark | None:
    bookmark = await repo.get(bookmark_id)
    if bookmark is None:
        return None
    bookmark.update(name=name, url=url, description=description, tags=tags, type=type)
    return await repo.save(bookmark)


async def delete_bookmark(repo: BookmarkRepository, bookmark_id: uuid.UUID) -> bool:
    bookmark = await repo.get(bookmark_id)
    if bookmark is None:
        return False
    bookmark.delete()
    await repo.save(bookmark)
    return True
