"""create bookmarks table

Revision ID: 875c6f32916c
Revises:
Create Date: 2026-08-30 18:36:46.832857

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "875c6f32916c"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bookmarks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column(
            "type", sa.Enum("POST", "VIDEO", "TWEET", "SITE", name="bookmarktype"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "enrichment_status",
            sa.Enum("PENDING", "DONE", "FAILED", name="enrichmentstatus"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bookmarks_deleted_at"), "bookmarks", ["deleted_at"])
    op.create_index(
        "uq_bookmarks_url_active",
        "bookmarks",
        ["url"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("bookmarks")
