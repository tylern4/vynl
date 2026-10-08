"""Collection CRUD: import, list/detail/update/delete, cover, play logging.

Ownership: every endpoint is scoped to ``current_user.id`` — another user's
album is indistinguishable from a missing one (404). Write endpoints go
through #1's ``require_write`` so read-only accounts can't mutate the shelf.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .. import providers
from ..auth import get_current_user, require_write
from ..database import get_db
from ..models import Album, Play, Tag, Track, User, album_tags
from ..schemas import (
    AlbumImportRequest,
    AlbumOut,
    AlbumUpdate,
    PlayCreate,
    PlayOut,
    album_to_out,
)
from ..services import artwork

router = APIRouter(prefix="/albums", tags=["albums"])

COVER_CACHE_CONTROL = "public, max-age=86400"
FUTURE_SKEW = timedelta(minutes=5)


def get_owned_album(db: Session, album_id: int, user: User) -> Album:
    """Fetch an album owned by ``user`` or 404 (also used by routers/tags.py)."""
    album = db.scalar(select(Album).where(Album.id == album_id))
    if album is None or album.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Album not found"
        )
    return album


def _find_duplicate(
    db: Session,
    user_id: int,
    source: str,
    external_id: str,
    title: str | None,
    artist: str | None,
) -> Album | None:
    """Hard dedupe on (user, source, external_id) + soft dedupe on
    (user, lower(title), lower(artist)) — PLAN §6 import rules."""
    existing = db.scalar(
        select(Album).where(
            Album.user_id == user_id,
            Album.source == source,
            Album.external_id == external_id,
        )
    )
    if existing is not None:
        return existing
    if title is not None and artist is not None:
        existing = db.scalar(
            select(Album).where(
                Album.user_id == user_id,
                func.lower(func.trim(Album.title)) == title.strip().lower(),
                func.lower(func.trim(Album.artist)) == artist.strip().lower(),
            )
        )
    return existing


def _conflict(existing: Album) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Album already in your shelf (id={existing.id})",
    )


@router.post("/import", response_model=AlbumOut, status_code=status.HTTP_201_CREATED)
def import_album(
    payload: AlbumImportRequest,
    current_user: Annotated[User, Depends(require_write)],
    db: Annotated[Session, Depends(get_db)],
):
    existing = _find_duplicate(
        db, current_user.id, payload.source, payload.external_id, None, None
    )
    if existing is not None:
        raise _conflict(existing)

    try:
        imported = providers.import_album(payload.source, payload.external_id)
    except providers.NotFound as exc:  # NotFound subclasses ProviderError
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Album not found at the provider: {exc.reason}",
        )
    except providers.ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Provider error: {exc.reason}",
        )

    existing = _find_duplicate(
        db, current_user.id, payload.source, payload.external_id,
        imported.title, imported.artist,
    )
    if existing is not None:
        raise _conflict(existing)

    album = Album(
        user_id=current_user.id,
        title=imported.title,
        artist=imported.artist,
        year=imported.year,
        label=imported.label,
        country=imported.country,
        source=payload.source,
        external_id=payload.external_id,
        musicbrainz_release_group_id=imported.musicbrainz_release_group_id,
        deezer_id=imported.deezer_id,
        cover_url=imported.cover_url,
        metadata_=dict(imported.metadata or {}),
        track_count=len(imported.tracks),
    )
    db.add(album)
    try:
        db.flush()  # assign album.id before tracks
        for track in imported.tracks:
            db.add(
                Track(
                    album_id=album.id,
                    position=track.position,
                    title=track.title,
                    duration_seconds=track.duration_seconds,
                )
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        # A concurrent import raced us: 409 if we can see the winner, else the
        # IntegrityError was something else (e.g. duplicate track positions).
        existing = _find_duplicate(
            db, current_user.id, payload.source, payload.external_id,
            imported.title, imported.artist,
        )
        if existing is not None:
            raise _conflict(existing)
        raise

    # Artwork caching is best-effort: any failure leaves cover_path null and
    # the frontend hotlinks cover_url (never fails the import).
    if album.cover_url:
        try:
            cover_path = artwork.download_cover(album.cover_url, album.id)
        except Exception:  # noqa: BLE001 — artwork must never fail an import
            cover_path = None
        if cover_path:
            album.cover_path = cover_path
            db.commit()
            db.refresh(album)

    return album_to_out(album, tracks=album.tracks)


@router.get("", response_model=list[AlbumOut])
def list_albums(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    tag: Annotated[list[str] | None, Query()] = None,
    favorite: bool | None = None,
    sort: str = "added",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if sort not in ("added", "title", "artist", "year", "played"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sort must be one of: added, title, artist, year, played",
        )

    stmt = (
        select(Album)
        .where(Album.user_id == current_user.id)
        .options(selectinload(Album.tags))
    )
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(Album.title.ilike(pattern), Album.artist.ilike(pattern)))
    if favorite is not None:
        stmt = stmt.where(Album.favorite == favorite)
    if tag:
        names = {t.strip().lower() for t in tag if t and t.strip()}
        if names:
            # exact tag match, ALL-OF semantics when `tag` is repeated
            link = (
                select(album_tags.c.album_id)
                .join(Tag, Tag.id == album_tags.c.tag_id)
                .where(Tag.user_id == current_user.id, Tag.name.in_(names))
                .group_by(album_tags.c.album_id)
                .having(func.count(func.distinct(Tag.name)) == len(names))
            )
            stmt = stmt.where(Album.id.in_(link))

    orders = {
        "added": (Album.created_at.desc(), Album.id.desc()),
        "title": (func.lower(Album.title).asc(), Album.id.asc()),
        "artist": (
            func.lower(Album.artist).asc(),
            func.lower(Album.title).asc(),
            Album.id.asc(),
        ),
        "year": (Album.year.asc().nulls_last(), func.lower(Album.title).asc()),
        "played": (Album.last_played_at.desc().nulls_last(), Album.id.desc()),
    }
    albums = db.scalars(
        stmt.order_by(*orders[sort]).limit(limit).offset(offset)
    ).all()
    return [album_to_out(album) for album in albums]


@router.get("/{album_id}", response_model=AlbumOut)
def get_album(
    album_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    album = get_owned_album(db, album_id, current_user)
    return album_to_out(album, tracks=album.tracks)


@router.patch("/{album_id}", response_model=AlbumOut)
def update_album(
    album_id: int,
    payload: AlbumUpdate,
    current_user: Annotated[User, Depends(require_write)],
    db: Annotated[Session, Depends(get_db)],
):
    album = get_owned_album(db, album_id, current_user)
    provided = payload.model_fields_set
    if "favorite" in provided:
        if payload.favorite is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="favorite cannot be null",
            )
        album.favorite = payload.favorite
    if "note" in provided:
        album.note = payload.note
    if "year" in provided:
        album.year = payload.year
    if "label" in provided:
        album.label = payload.label
    db.commit()
    db.refresh(album)
    return album_to_out(album, tracks=album.tracks)


@router.delete("/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_album(
    album_id: int,
    current_user: Annotated[User, Depends(require_write)],
    db: Annotated[Session, Depends(get_db)],
):
    album = get_owned_album(db, album_id, current_user)
    cached = artwork.resolve_cover_file(album.cover_path)
    db.delete(album)  # tracks / album_tags / plays cascade at the DB level
    db.commit()
    if cached is not None:
        try:
            cached.unlink()
        except OSError:
            pass  # orphaned file is harmless; never fail the delete


@router.get("/{album_id}/cover")
def get_cover(
    album_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    album = get_owned_album(db, album_id, current_user)
    path = artwork.resolve_cover_file(album.cover_path)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No cover image"
        )
    return FileResponse(
        path,
        media_type=artwork.media_type_for_name(path.name),
        headers={"Cache-Control": COVER_CACHE_CONTROL},
    )


# --- Play listening history (PLAN §5) ---------------------------------------


@router.post("/{album_id}/plays", response_model=AlbumOut,
             status_code=status.HTTP_201_CREATED)
def log_play(
    album_id: int,
    current_user: Annotated[User, Depends(require_write)],
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[PlayCreate | None, Body()] = None,
):
    album = get_owned_album(db, album_id, current_user)
    played_at = payload.played_at if payload and payload.played_at else None
    if played_at is None:
        played_at = datetime.now(timezone.utc)
    else:
        if played_at.tzinfo is None:
            played_at = played_at.replace(tzinfo=timezone.utc)  # naive = UTC
        if played_at > datetime.now(timezone.utc) + FUTURE_SKEW:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="played_at cannot be in the future",
            )
    db.add(Play(album_id=album.id, user_id=current_user.id, played_at=played_at))
    # Denormalize last_played_at = max(played_at) so dusty stays one lookup.
    if album.last_played_at is None or played_at > album.last_played_at:
        album.last_played_at = played_at
    db.commit()
    db.refresh(album)
    return album_to_out(album, tracks=album.tracks)


@router.get("/{album_id}/plays", response_model=list[PlayOut])
def list_plays(
    album_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    album = get_owned_album(db, album_id, current_user)
    return db.scalars(
        select(Play)
        .where(Play.album_id == album.id)
        .order_by(Play.played_at.desc(), Play.id.desc())
    ).all()


@router.delete("/{album_id}/plays/{play_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_play(
    album_id: int,
    play_id: int,
    current_user: Annotated[User, Depends(require_write)],
    db: Annotated[Session, Depends(get_db)],
):
    album = get_owned_album(db, album_id, current_user)
    play = db.get(Play, play_id)
    if play is None or play.album_id != album.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Play not found"
        )
    db.delete(play)
    db.flush()  # autoflush is off — remove the row before recomputing
    album.last_played_at = db.scalar(
        select(func.max(Play.played_at)).where(Play.album_id == album.id)
    )
    db.commit()
