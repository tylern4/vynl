"""Library song search: ILIKE across track/album/artist for the user (PLAN §5)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Album, Track, User
from ..schemas import TrackSearchAlbum, TrackSearchOut

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("", response_model=list[TrackSearchOut])
def search_tracks(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    pattern = f"%{q}%"
    rows = db.execute(
        select(Track, Album)
        .join(Album, Track.album_id == Album.id)
        .where(
            Album.user_id == current_user.id,
            or_(
                Track.title.ilike(pattern),
                Album.title.ilike(pattern),
                Album.artist.ilike(pattern),
            ),
        )
        .order_by(
            func.lower(Album.artist).asc(),
            func.lower(Album.title).asc(),
            Track.position.asc(),
        )
        .limit(limit)
    ).all()
    return [
        TrackSearchOut(
            id=track.id,
            title=track.title,
            duration_seconds=track.duration_seconds,
            position=track.position,
            album=TrackSearchAlbum(
                id=album.id,
                title=album.title,
                artist=album.artist,
                year=album.year,
                cover_url=album.cover_url,
            ),
        )
        for track, album in rows
    ]
