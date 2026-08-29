"""SQLAlchemy ORM row for the `bookmarks` table. Persistence detail — never leaves this adapter."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String, Uuid, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.adapters.outbound.database import Base
from app.domain.models import BookmarkType


class BookmarkRow(Base):
    __tablename__ = "bookmarks"

    # Partial unique index: url is unique only among live rows. A soft-deleted
    # bookmark keeps its row (and url) forever, so a plain UNIQUE(url) would wrongly
    # block re-adding a url the user already deleted. `sqlite_where` makes this a
    # SQLite partial index — same dialect coupling as the json_each tag filter.
    __table_args__ = (
        Index(
            "uq_bookmarks_url_active",
            "url",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    type: Mapped[BookmarkType] = mapped_column(SAEnum(BookmarkType), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
