"""Composition root: builds the FastAPI app and wires the inbound adapter in."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.adapters.inbound.api import router
from app.adapters.outbound import orm  # noqa: F401  # registers BookmarkRow on Base.metadata
from app.adapters.outbound.database import Base, engine
from app.domain.exceptions import BookmarkInvalidError, BookmarkNotFoundError

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # create_all is sync DDL; run_sync drives it over the async engine's connection.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Bookmarks Archive API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)


@app.exception_handler(BookmarkNotFoundError)
async def bookmark_not_found_handler(request: Request, exc: BookmarkNotFoundError) -> JSONResponse:
    """Only reachable via a get-then-save race (e.g. concurrent deletes); everyday
    404s are handled by the service layer's None-returning lookups instead."""
    return JSONResponse(status_code=404, content={"detail": "Bookmark not found"})


@app.exception_handler(BookmarkInvalidError)
async def bookmark_invalid_handler(request: Request, exc: BookmarkInvalidError) -> JSONResponse:
    """Domain invariant violations (Bookmark.validate()) surface as 422, matching
    the status FastAPI already uses for Pydantic schema validation failures."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


app.include_router(router)
