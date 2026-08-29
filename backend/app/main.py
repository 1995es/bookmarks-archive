"""Composition root: builds the FastAPI app and wires the inbound adapter in."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.adapters.inbound import background
from app.adapters.inbound.api import router
from app.adapters.outbound import orm  # noqa: F401  # registers BookmarkRow on Base.metadata
from app.adapters.outbound.database import Base, engine
from app.adapters.outbound.llm_config import resolve_llm_model
from app.domain.exceptions import (
    BookmarkInvalidError,
    BookmarkNotFoundError,
    BookmarkUrlConflictError,
)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Fails fast on a bad LLM_MODEL or missing API key, rather than only surfacing it
    # inside the first background enrichment task.
    background.llm_model = resolve_llm_model()

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


@app.exception_handler(BookmarkUrlConflictError)
async def bookmark_url_conflict_handler(
    request: Request, exc: BookmarkUrlConflictError
) -> JSONResponse:
    """A url that already belongs to a live bookmark is a 409 Conflict, not a
    validation error: the request is well-formed, it just collides with existing
    state. Raised by the repository (add/save) via the port's uniqueness contract."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(BookmarkInvalidError)
async def bookmark_invalid_handler(request: Request, exc: BookmarkInvalidError) -> JSONResponse:
    """Domain invariant violations (Bookmark.validate()) surface as 422, matching
    the status FastAPI already uses for Pydantic schema validation failures."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


app.include_router(router)
