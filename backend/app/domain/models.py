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


class EnrichmentStatus(str, Enum):
    """Where a bookmark stands in the background enrichment pipeline.

    A bookmark is born PENDING and moves to DONE (Bookmark.enrich() succeeded)
    or FAILED (background.py exhausted its retries). A FAILED bookmark can be
    moved back to PENDING via Bookmark.mark_enrichment_pending(), the manual
    retry path — there's still no automatic re-attempt.
    """

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


_MAX_NAME_LENGTH = 200
_MAX_TAGS = 50
_MAX_TAG_LENGTH = 50
_MAX_DESCRIPTION_LENGTH = 2000


@dataclass(frozen=True)
class FetchedContent:
    """Title, meta description, and body text extracted from a bookmark's URL.

    Returned by ContentFetcher.fetch() — a structured alternative to a single
    blob of text, so BookmarkEnricherService gets the page's own title/description
    as distinct signals from the body, and enrich_bookmark can use `name` to
    replace a placeholder bookmark name without re-parsing the page itself.
    """

    name: str
    description: str
    content: str


@dataclass(frozen=True)
class ExtractedData:
    """Description and tags derived from a bookmark's content, merged in via Bookmark.enrich()."""

    description: str
    tags: list[str]


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
    enrichment_status: EnrichmentStatus = EnrichmentStatus.PENDING

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

    def enrich(self, data: ExtractedData, *, name: str | None = None) -> None:
        """Merge generated description/tags onto what the user already provided.

        Description is appended (not replaced) so a user-written description
        survives; tags are appended without duplicating existing ones. Both are
        bounded to the same limits schemas.py enforces at the wire boundary —
        the LLM path never goes through Pydantic, so an oversized or empty tag,
        or an over-length description, would otherwise persist and then fail
        BookmarkRead validation on every subsequent read.

        `name`, unlike description, is replaced outright rather than merged —
        two names can't be meaningfully combined the way two paragraphs can.
        Passing one is opt-in: the caller (enrich_bookmark) decides whether the
        current name is still the auto-derived placeholder worth replacing, or
        a name the user actually chose. Truncated to _MAX_NAME_LENGTH for the
        same reason description/tags are: this never passes through Pydantic.
        """
        if name:
            self.name = name[:_MAX_NAME_LENGTH]

        if self.description:
            merged = f"{self.description}\n\n{data.description}"
        else:
            merged = data.description
        self.description = merged[:_MAX_DESCRIPTION_LENGTH]

        for tag in data.tags:
            tag = tag[:_MAX_TAG_LENGTH]
            if tag and tag not in self.tags:
                self.tags.append(tag)
        self.tags = self.tags[:_MAX_TAGS]

        self.enrichment_status = EnrichmentStatus.DONE
        self.validate()

    def mark_enrichment_failed(self) -> None:
        """Record that background.py exhausted its retries without enriching this
        bookmark. Called instead of enrich() — the bookmark keeps whatever
        description/tags it already had."""
        self.enrichment_status = EnrichmentStatus.FAILED

    def mark_enrichment_pending(self) -> None:
        """Reset a FAILED bookmark so background.py can attempt enrichment again."""
        self.enrichment_status = EnrichmentStatus.PENDING

    def validate(self) -> None:
        if not self.name:
            raise BookmarkInvalidError("name must not be empty")
        if not self.url:
            raise BookmarkInvalidError("url must not be empty")
