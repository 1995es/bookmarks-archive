"""Inbound adapter: the enrichment BackgroundTask's edge.

get_db closes its AsyncSession when the request ends, but a BackgroundTask runs
after the response is sent, so it can't reuse the route's injected repo/session —
it opens its own via SessionLocal instead.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable

from app.adapters.outbound.database import SessionLocal
from app.adapters.outbound.http_content_fetcher import HttpContentFetcher
from app.adapters.outbound.llm_bookmark_enricher import LLMBookmarkEnricherService
from app.adapters.outbound.sqlalchemy_repository import SqlAlchemyBookmarkRepository
from app.application.enrich_bookmark import enrich_bookmark
from app.domain.exceptions import (
    BookmarkInvalidError,
    BookmarkNotFoundError,
    ContentFetchError,
    EnrichmentError,
)

logger = logging.getLogger(__name__)

EnrichmentRunner = Callable[[uuid.UUID], Awaitable[None]]


async def run_enrichment(bookmark_id: uuid.UUID) -> None:
    """Composes dependencies, opens its own session, and swallows every failure.

    Nothing past this function should ever raise: a failed enrichment just
    leaves the bookmark un-enriched, logged for visibility.
    """
    try:
        async with SessionLocal() as db:
            repo = SqlAlchemyBookmarkRepository(db)
            async with HttpContentFetcher() as fetcher:
                enricher = LLMBookmarkEnricherService()
                await enrich_bookmark(bookmark_id, repo=repo, fetcher=fetcher, enricher=enricher)
    except (ContentFetchError, EnrichmentError, BookmarkNotFoundError, BookmarkInvalidError) as exc:
        # BookmarkNotFoundError here means the bookmark was deleted between the
        # use case's get() and save() — an expected race, not a bug.
        logger.warning("enrichment failed for %s: %s", bookmark_id, exc)
    except Exception:
        logger.exception("unexpected error enriching %s", bookmark_id)


def get_enrichment_runner() -> EnrichmentRunner:
    """FastAPI provider. Overridable in tests."""
    return run_enrichment
