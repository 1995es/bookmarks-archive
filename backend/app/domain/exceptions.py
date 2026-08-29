"""Domain-level exceptions. Part of the BookmarkRepository port's contract."""

import uuid


class BookmarkNotFoundError(Exception):
    """Raised by BookmarkRepository.save() when the bookmark no longer exists."""

    def __init__(self, bookmark_id: uuid.UUID) -> None:
        self.bookmark_id = bookmark_id
        super().__init__(f"Bookmark {bookmark_id} does not exist")


class BookmarkInvalidError(ValueError):
    """Raised by Bookmark.validate() when a domain invariant is violated."""


class BookmarkUrlConflictError(Exception):
    """Raised by BookmarkRepository.add()/save() when another live (non-deleted)
    bookmark already has the same url. A soft-deleted bookmark's url is free to
    reuse, so this only fires against bookmarks visible to get()/list()."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(f"A bookmark with url {url!r} already exists")


class ContentFetchError(Exception):
    """Raised by ContentFetcher.fetch() on a network failure or non-2xx status."""


class EnrichmentError(Exception):
    """Raised by BookmarkEnricherService.extract_data() when the provider fails
    or its response can't be parsed into ExtractedData."""


class MissingLLMCredentialsError(Exception):
    """Raised at startup when LLM_MODEL's provider needs an API key that isn't set."""

    def __init__(self, *, model: str, provider: str, env_var: str) -> None:
        self.model = model
        self.provider = provider
        self.env_var = env_var
        super().__init__(
            f"LLM_MODEL={model!r} uses provider {provider!r}, which requires {env_var} "
            f"to be set in the environment."
        )
