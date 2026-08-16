"""SQLAlchemy async engine, session, and declarative base setup."""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


def _as_async_url(url: str) -> str:
    """Force an async driver on a plain `sqlite://` URL.

    Deployments (docker-compose, Dockerfile.prod) pass DATABASE_URL without a
    driver; create_async_engine would reject the sync pysqlite dialect, so map
    it onto aiosqlite here instead of requiring every caller to know that.
    """
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


DATABASE_URL = _as_async_url(os.environ.get("DATABASE_URL", "sqlite:///./bookmarks.db"))

# check_same_thread is a SQLite/pysqlite-only DBAPI argument; other dialects
# (e.g. Postgres via DATABASE_URL) reject it as an unexpected keyword.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_async_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with SessionLocal() as db:
        yield db
