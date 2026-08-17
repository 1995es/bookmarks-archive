"""Enrichment use case. Depends only on ports, never on concrete adapters."""

import uuid

from app.domain.models import Bookmark
from app.domain.ports import BookmarkEnricherService, BookmarkRepository, ContentFetcher


async def enrich_bookmark(
    bookmark_id: uuid.UUID,
    *,
    repo: BookmarkRepository,
    fetcher: ContentFetcher,
    enricher: BookmarkEnricherService,
) -> Bookmark | None:
    """Fetch a bookmark's content, derive a description/tags, and persist the merge.

    Returns None (rather than raising) when the bookmark is missing or soft-deleted,
    matching get_bookmark/update_bookmark's everyday-not-found convention. Any other
    failure (fetch, enrichment, or a concurrent-delete race in repo.save()) propagates
    to the caller, which decides what to do with it — this use case stays testable
    without mocking logging.
    """
    bookmark = await repo.get(bookmark_id)
    if bookmark is None:
        return None

    content = await fetcher.fetch(bookmark.url)
    data = await enricher.extract_data(url=bookmark.url, content=content)
    bookmark.enrich(data)
    return await repo.save(bookmark)
