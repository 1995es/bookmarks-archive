"""add favicon_url to bookmarks

Revision ID: 4c1a7de92b38
Revises: 875c6f32916c
Create Date: 2026-09-25 09:12:04.118233

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c1a7de92b38"
down_revision: str | Sequence[str] | None = "875c6f32916c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable and with no server default, so this is a metadata-only ALTER on
    # SQLite (no table rewrite). Rows that predate it keep NULL: enrichment only
    # runs on create and on manual retry, so existing bookmarks stay icon-less
    # until one of those happens.
    op.add_column("bookmarks", sa.Column("favicon_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("bookmarks", "favicon_url")
