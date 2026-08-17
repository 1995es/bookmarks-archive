"""Inbound HTTP adapter: FastAPI routes. Translate HTTP calls into application-layer use cases."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.adapters.inbound.background import EnrichmentRunner, get_enrichment_runner
from app.adapters.inbound.schemas import BookmarkCreate, BookmarkRead, BookmarkUpdate
from app.adapters.outbound.sqlalchemy_repository import get_repository
from app.application import bookmark_service
from app.domain.models import BookmarkType
from app.domain.ports import BookmarkRepository

router = APIRouter()


@router.get("/bookmarks", response_model=list[BookmarkRead])
async def list_bookmarks(
    name: str | None = None,
    tag: str | None = None,
    type: BookmarkType | None = None,
    repo: BookmarkRepository = Depends(get_repository),
) -> list[BookmarkRead]:
    return await bookmark_service.list_bookmarks(repo, name=name, tag=tag, type=type)


@router.post("/bookmarks", response_model=BookmarkRead, status_code=201)
async def create_bookmark(
    bookmark: BookmarkCreate,
    background_tasks: BackgroundTasks,
    repo: BookmarkRepository = Depends(get_repository),
    enrich: EnrichmentRunner = Depends(get_enrichment_runner),
) -> BookmarkRead:
    created = await bookmark_service.create_bookmark(repo, **bookmark.model_dump())
    background_tasks.add_task(enrich, created.id)
    return created


@router.get("/bookmarks/{bookmark_id}", response_model=BookmarkRead)
async def get_bookmark(
    bookmark_id: uuid.UUID, repo: BookmarkRepository = Depends(get_repository)
) -> BookmarkRead:
    bookmark = await bookmark_service.get_bookmark(repo, bookmark_id)
    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return bookmark


@router.put("/bookmarks/{bookmark_id}", response_model=BookmarkRead)
async def update_bookmark(
    bookmark_id: uuid.UUID,
    bookmark: BookmarkUpdate,
    repo: BookmarkRepository = Depends(get_repository),
) -> BookmarkRead:
    updated = await bookmark_service.update_bookmark(repo, bookmark_id, **bookmark.model_dump())
    if updated is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return updated


@router.delete("/bookmarks/{bookmark_id}", status_code=204)
async def delete_bookmark(
    bookmark_id: uuid.UUID, repo: BookmarkRepository = Depends(get_repository)
) -> None:
    deleted = await bookmark_service.delete_bookmark(repo, bookmark_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bookmark not found")
