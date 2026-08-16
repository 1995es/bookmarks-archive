"""Domain-level exceptions. Part of the BookmarkRepository port's contract."""

import uuid


class BookmarkNotFoundError(Exception):
    """Raised by BookmarkRepository.save() when the bookmark no longer exists."""

    def __init__(self, bookmark_id: uuid.UUID) -> None:
        self.bookmark_id = bookmark_id
        super().__init__(f"Bookmark {bookmark_id} does not exist")


class BookmarkInvalidError(ValueError):
    """Raised by Bookmark.validate() when a domain invariant is violated."""
