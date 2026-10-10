"""Dusty/random recommendation picker (PLAN §5).

``dusty`` surfaces the records you haven't spun in a while: candidates are
ranked by ``COALESCE(last_played_at, '-infinity')`` ascending (never-played
first), sampled without replacement from the bottom 25% with random jitter so
the answer isn't always the same record, skipping anything played within the
last 3 days when enough alternatives exist. ``random`` is a uniform sample.

The RNG is dependency-injected (``random.Random`` via ``get_rng``) so tests
can pin a seed and assert exact picks.
"""

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import get_current_user
from ..database import get_db
from ..models import Album, Tag, User, album_tags
from ..schemas import RecommendationOut, album_to_out

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

FRESH_WINDOW = timedelta(days=3)  # skip albums spun this recently (dusty)


def get_rng() -> random.Random:
    """Fresh RNG per request; tests override this dependency for determinism."""
    return random.Random()


def _candidates(
    db: Session, tag: str | None
) -> list[Album]:
    stmt = (
        select(Album)
        .options(selectinload(Album.tags))
        .order_by(  # COALESCE(last_played_at, '-infinity'), id breaks never-played ties
            Album.last_played_at.asc().nulls_first(), Album.id.asc()
        )
    )
    if tag:
        name = tag.strip().lower()
        if name:
            link = (
                select(album_tags.c.album_id)
                .join(Tag, Tag.id == album_tags.c.tag_id)
                .where(Tag.name == name)
            )
            stmt = stmt.where(Album.id.in_(link))
    return list(db.scalars(stmt).all())


def _dusty(albums: list[Album], n: int, rng: random.Random) -> list[Album]:
    if not albums:
        return []
    # Bottom 25% of the dusty ranking (at least n so sampling is possible).
    pool_size = max(math.ceil(len(albums) * 0.25), n)
    pool = albums[:pool_size]
    # Skip albums spun in the last 3 days when enough alternatives exist.
    cutoff = datetime.now(timezone.utc) - FRESH_WINDOW
    eligible = [
        a
        for a in pool
        if a.last_played_at is None or a.last_played_at < cutoff
    ]
    if len(eligible) >= n:
        pool = eligible
    # Random jitter over dusty rank: nearby records swap, all picks stay in
    # the pool (no duplicates — each index is sorted exactly once).
    jitter = max(1.0, len(pool) * 0.25)
    ranked = sorted(range(len(pool)), key=lambda i: i + rng.random() * jitter)
    return [pool[i] for i in ranked[:n]]


def _reason(album: Album, mode: str) -> str:
    if mode == "random":
        return "Random pick"
    if album.last_played_at is None:
        return "Never played"
    played = album.last_played_at
    if played.tzinfo is None:
        played = played.replace(tzinfo=timezone.utc)
    return f"Haven't spun this since {played.strftime('%b %Y')}"


def _days_since(album: Album) -> int | None:
    if album.last_played_at is None:
        return None
    played = album.last_played_at
    if played.tzinfo is None:
        played = played.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc).date() - played.date()).days


@router.get("", response_model=list[RecommendationOut])
def recommendations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    rng: Annotated[random.Random, Depends(get_rng)],
    mode: Literal["dusty", "random"] = "dusty",
    tag: str | None = None,
    n: int = 1,
):
    n = max(1, min(20, n))  # clamp 1–20
    albums = _candidates(db, tag)
    if mode == "random":
        picks = rng.sample(albums, k=min(n, len(albums)))
    else:
        picks = _dusty(albums, n, rng)
    return [
        RecommendationOut(
            album=album_to_out(album),
            reason=_reason(album, mode),
            days_since_played=_days_since(album),
        )
        for album in picks
    ]
