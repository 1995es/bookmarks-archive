"""Inbound adapter: the enrichment BackgroundTask's edge.

get_db closes its AsyncSession when the request ends, but a BackgroundTask runs
after the response is sent, so it can't reuse the route's injected repo/session —
it opens its own via SessionLocal instead.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.adapters.outbound.database import SessionLocal
from app.adapters.outbound.http_content_fetcher import HttpContentFetcher
from app.adapters.outbound.llm_bookmark_enricher import LLMBookmarkEnricherService
from app.adapters.outbound.llm_config import DEFAULT_MODEL
from app.adapters.outbound.sqlalchemy_repository import SqlAlchemyBookmarkRepository
from app.application.enrich_bookmark import enrich_bookmark
from app.domain.exceptions import (
    BookmarkInvalidError,
    BookmarkNotFoundError,
    ContentFetchError,
    EnrichmentError,
)
from app.domain.ports import BookmarkRepository

logger = logging.getLogger(__name__)

EnrichmentRunner = Callable[[uuid.UUID], Awaitable[None]]

# Set by main.py's lifespan at startup, once LLM_MODEL has been resolved and validated.
# Defaults to DEFAULT_MODEL so tests that skip the lifespan (e.g. importing this module
# directly) still get a usable value.
llm_model: str = DEFAULT_MODEL

_MAX_ENRICHMENT_ATTEMPTS = 5

# ContentFetchError/EnrichmentError cover transient failures — a flaky fetch, or an
# LLM provider rejecting the request (e.g. a free-tier rate limit) — which are worth
# retrying with backoff. BookmarkNotFoundError/BookmarkInvalidError are not retried:
# they mean the bookmark was deleted or is otherwise invalid, and trying again won't
# change that. Exposed as a module attribute (`.retry`) so tests can swap out the
# wait strategy instead of sleeping through five real backoffs.
enrich_bookmark_with_retry = retry(
    retry=retry_if_exception_type((ContentFetchError, EnrichmentError)),
    stop=stop_after_attempt(_MAX_ENRICHMENT_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    reraise=True,
)(enrich_bookmark)


async def _mark_enrichment_failed(bookmark_id: uuid.UUID, repo: BookmarkRepository) -> None:
    bookmark = await repo.get(bookmark_id)
    if bookmark is None:
        return
    bookmark.mark_enrichment_failed()
    try:
        await repo.save(bookmark)
    except BookmarkNotFoundError:
        # Deleted between this get() and save() — nothing left to mark.
        pass


async def run_enrichment(bookmark_id: uuid.UUID) -> None:
    """Composes dependencies, opens its own session, and swallows every failure.

    Nothing past this function should ever raise: after retries are exhausted,
    the bookmark is persisted as enrichment_status=FAILED and the failure is
    logged for visibility, rather than left indistinguishable from "never ran".
    """
    try:
        async with SessionLocal() as db:
            repo = SqlAlchemyBookmarkRepository(db)
            async with HttpContentFetcher() as fetcher:
                enricher = LLMBookmarkEnricherService(model=llm_model)
                try:
                    await enrich_bookmark_with_retry(
                        bookmark_id, repo=repo, fetcher=fetcher, enricher=enricher
                    )
                except (ContentFetchError, EnrichmentError) as exc:
                    logger.warning(
                        "enrichment failed for %s after %d attempts: %s",
                        bookmark_id,
                        _MAX_ENRICHMENT_ATTEMPTS,
                        exc,
                    )
                    await _mark_enrichment_failed(bookmark_id, repo)
    except (BookmarkNotFoundError, BookmarkInvalidError) as exc:
        # BookmarkNotFoundError here means the bookmark was deleted between the
        # use case's get() and save() — an expected race, not a bug.
        logger.warning("enrichment failed for %s: %s", bookmark_id, exc)
    except Exception:
        logger.exception("unexpected error enriching %s", bookmark_id)


def get_enrichment_runner() -> EnrichmentRunner:
    """FastAPI provider. Overridable in tests."""
    return run_enrichment
