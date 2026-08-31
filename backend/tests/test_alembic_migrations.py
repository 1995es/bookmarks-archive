"""Tests for the Alembic baseline revision, which has to double as the one-time
adoption path for databases `create_all()` + the old `outbound/migrations.py`
already built (see `alembic/versions/875c6f32916c_create_bookmarks_table.py`).

Runs `alembic upgrade head` as a subprocess with `DATABASE_URL` set, the same
way the Docker `CMD`/a developer's shell invokes it — not via Alembic's Python
API — because `app.adapters.outbound.database` reads `DATABASE_URL` from the
environment exactly once, at import time, and by the time this test module
runs, other test modules have already imported it against their own database.
"""

import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

_BACKEND_ROOT = Path(__file__).resolve().parent.parent

# The `bookmarks` table exactly as it stood before enrichment_status was added,
# i.e. before Alembic existed at all.
_PRE_ENRICHMENT_SCHEMA = """
CREATE TABLE bookmarks (
    id CHAR(32) NOT NULL PRIMARY KEY,
    name VARCHAR NOT NULL,
    url VARCHAR NOT NULL,
    description VARCHAR,
    created_at DATETIME NOT NULL,
    tags JSON NOT NULL,
    type VARCHAR(5) NOT NULL,
    deleted_at DATETIME
)
"""


@pytest.fixture()
def db_path() -> Generator[str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


def _upgrade(db_path: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_ROOT,
        env={**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"},
        check=True,
        capture_output=True,
    )


def test_creates_table_on_a_fresh_database(db_path: str) -> None:
    _upgrade(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(bookmarks)"))}
    assert "enrichment_status" in columns


def test_backfills_pre_existing_rows_as_done(db_path: str) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text(_PRE_ENRICHMENT_SCHEMA))
        conn.execute(
            text(
                "INSERT INTO bookmarks (id, name, url, description, created_at, tags, type)"
                " VALUES (:id, 'Old', 'https://old.example', NULL, :created_at, '[]', 'SITE')"
            ),
            {"id": uuid.uuid4().hex, "created_at": datetime.now(UTC).isoformat()},
        )

    _upgrade(db_path)

    with engine.connect() as conn:
        statuses = [row[0] for row in conn.execute(text("SELECT enrichment_status FROM bookmarks"))]
    assert statuses == ["DONE"]


def test_is_idempotent(db_path: str) -> None:
    _upgrade(db_path)

    _upgrade(db_path)  # a second boot against an already-migrated database

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(bookmarks)"))}
    assert "enrichment_status" in columns
