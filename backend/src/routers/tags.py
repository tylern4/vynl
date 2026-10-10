"""Shared tags: list/create, replace an album's tag set, delete.

Tags belong to the shared shelf (one ``name`` per shelf), stored
lowercased/trimmed. The album tag-set endpoint lives here too:
``PUT /api/albums/{id}/tags`` has replace semantics and creates missing tags.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_write
from ..database import get_db
from ..models import Tag, User, album_tags
from ..schemas import AlbumOut, AlbumTagsPut, TagCreate, TagOut, album_to_out
from .albums import get_shelf_album

router = APIRouter(tags=["tags"])


def _album_count(db: Session, tag_id: int) -> int:
    return (
        db.scalar(
            select(func.count(album_tags.c.album_id)).where(
                album_tags.c.tag_id == tag_id
            )
        )
        or 0
    )


def _tag_out(db: Session, tag: Tag) -> TagOut:
    return TagOut(id=tag.id, name=tag.name, album_count=_album_count(db, tag.id))


def _normalize(raw: str) -> str:
    name = raw.strip().lower()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tag name cannot be empty",
        )
    return name


def _get_tag(db: Session, tag_id: int) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found"
        )
    return tag


@router.get("/tags", response_model=list[TagOut])
def list_tags(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    rows = db.execute(
        select(Tag, func.count(album_tags.c.album_id))
        .outerjoin(album_tags, album_tags.c.tag_id == Tag.id)
        .group_by(Tag.id)
        .order_by(Tag.name.asc())
    ).all()
    return [TagOut(id=tag.id, name=tag.name, album_count=count) for tag, count in rows]


@router.post("/tags", response_model=TagOut)
def create_tag(
    payload: TagCreate,
    response: Response,
    current_user: Annotated[User, Depends(require_write)],
    db: Annotated[Session, Depends(get_db)],
):
    name = _normalize(payload.name)
    existing = db.scalar(select(Tag).where(Tag.name == name))
    if existing is not None:  # idempotent: existing name is returned as-is
        return _tag_out(db, existing)
    tag = Tag(name=name)
    db.add(tag)
    try:
        db.commit()
    except IntegrityError:  # concurrent create of the same name
        db.rollback()
        existing = db.scalar(select(Tag).where(Tag.name == name))
        if existing is None:
            raise
        return _tag_out(db, existing)
    db.refresh(tag)
    response.status_code = status.HTTP_201_CREATED
    return TagOut(id=tag.id, name=tag.name, album_count=0)


@router.put("/albums/{album_id}/tags", response_model=AlbumOut)
def set_album_tags(
    album_id: int,
    payload: AlbumTagsPut,
    current_user: Annotated[User, Depends(require_write)],
    db: Annotated[Session, Depends(get_db)],
):
    album = get_shelf_album(db, album_id)
    names: list[str] = []
    for raw in payload.tags:
        name = _normalize(raw)
        if name not in names:  # dedupe while preserving order
            names.append(name)
    tags: list[Tag] = []
    for name in names:
        tag = db.scalar(select(Tag).where(Tag.name == name))
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
        tags.append(tag)
    album.tags = tags  # REPLACE semantics — drops anything not in payload
    db.commit()
    db.refresh(album)
    return album_to_out(album, tracks=album.tracks)


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: int,
    current_user: Annotated[User, Depends(require_write)],
    db: Annotated[Session, Depends(get_db)],
):
    tag = _get_tag(db, tag_id)
    db.delete(tag)  # album_tags links removed by FK cascade / ORM secondary
    db.commit()
