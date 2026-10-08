"""iTunes Search / Lookup provider (issue #12).

No API key and always enabled. ``search`` queries **each configured storefront**
(``settings.itunes_countries``, default ``"US,JP,GB"`` — order = query order) so
JP-only and other obscure pressings surface; ``fetch_album`` tries the same
storefronts in order until one has the collection.

Politeness: a ~0.3 s spacing guard between storefront requests (module lock),
a 20 s per-request timeout, and per-storefront degradation — a failing
storefront is recorded and skipped, empty results for a storefront are not an
error, and only an all-storefronts failure raises.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

from ..config import settings
from . import _client
from .base import NotFound, ProviderError, SearchResult, TrackInput

SEARCH_URL = f"{_client.ITUNES_BASE}/search"
LOOKUP_URL = f"{_client.ITUNES_BASE}/lookup"

#: Keep storefront requests ~0.3 s apart (issue #12); overridden to 0 in tests.
_MIN_INTERVAL = 0.3
_TIMEOUT = 20.0

_throttle_lock = threading.Lock()
_next_slot = 0.0

_DIGITS_RE = re.compile(r"^\d+$")

#: iTunes asks for 600x600; search/lookup rows only expose artworkUrl100.
_ART_UPGRADE = ("100x100bb", "600x600bb")


@dataclass
class ItunesAlbum:
    """Album metadata normalized away from the iTunes lookup payload."""

    itunes_id: str
    title: str
    artist: str
    year: int | None
    country: str | None
    label: str | None
    cover_url: str | None
    tracks: list[TrackInput]
    genres: list[str] = field(default_factory=list)


def countries() -> list[str]:
    """Parsed storefront codes in configured order (``US,JP,GB`` → [US, JP, GB])."""
    return [
        code.strip().upper()
        for code in (settings.itunes_countries or "").split(",")
        if code.strip()
    ]


def _require_countries() -> None:
    if not countries():
        raise ProviderError(
            "no iTunes storefronts configured (set ITUNES_COUNTRIES, e.g. US,JP,GB)"
        )


def _throttle() -> None:
    """Reserve the next storefront slot, sleeping to ~0.3 s spacing."""
    global _next_slot
    with _throttle_lock:
        now = time.monotonic()
        wait = _next_slot - now
        if wait > 0:
            time.sleep(wait)
        _next_slot = time.monotonic() + _MIN_INTERVAL


def _year(date: object) -> int | None:
    if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit():
        return int(date[:4])
    return None


def upgrade_art(url: str | None) -> str | None:
    """``artworkUrl100`` → 600x600 by rewriting the ``100x100bb`` size token."""
    if not url:
        return None
    return url.replace(*_ART_UPGRADE) if _ART_UPGRADE[0] in url else url


def search(query: str, limit: int = 20) -> list[SearchResult]:
    """Search every configured storefront; per-storefront failures degrade
    (only all-failed raises), an empty storefront result is not an error."""
    _require_countries()
    rows: list[SearchResult] = []
    failures: list[str] = []
    for cc in countries():
        try:
            rows.extend(_search_storefront(query, limit, cc))
        except ProviderError as exc:
            failures.append(f"{cc}: {exc.reason}")
    if failures and not rows and len(failures) == len(countries()):
        raise ProviderError(
            f"all iTunes storefronts failed — {'; '.join(failures)}"
        )
    return rows


def _search_storefront(query: str, limit: int, cc: str) -> list[SearchResult]:
    _throttle()
    data = _client.get_json(
        SEARCH_URL,
        params={
            "term": query,
            "entity": "album",
            "media": "music",
            "limit": min(limit, 200),
            "country": cc,
        },
        timeout=_TIMEOUT,
    )
    if not isinstance(data, dict):
        return []
    results: list[SearchResult] = []
    for item in data.get("results") or []:
        collection_id = item.get("collectionId")
        title = (item.get("collectionName") or "").strip()
        if collection_id is None or not title:
            continue
        results.append(
            SearchResult(
                source="itunes",
                external_id=str(collection_id),
                title=title,
                artist=(item.get("artistName") or "").strip() or "Unknown Artist",
                year=_year(item.get("releaseDate")),
                track_count=item.get("trackCount"),
                cover_url=upgrade_art(item.get("artworkUrl100")),
                itunes_id=str(collection_id),
            )
        )
    return results


def fetch_album(collection_id: str) -> ItunesAlbum:
    """Look up a collection across storefronts → full metadata + tracklist.

    The first storefront that has the collection wins; empty lookups are
    skipped, per-storefront errors degrade, all-failed raises. Every
    storefront empty (and none failed) means the id doesn't exist →
    :class:`NotFound`.
    """
    if not _DIGITS_RE.match(str(collection_id)):
        raise NotFound(f"invalid iTunes collection id: {collection_id!r}")
    _require_countries()
    failures: list[str] = []
    for cc in countries():
        try:
            album = _lookup_storefront(str(collection_id), cc)
        except ProviderError as exc:
            failures.append(f"{cc}: {exc.reason}")
            continue
        if album is not None:
            return album
    if failures:
        raise ProviderError(
            f"iTunes lookup failed for {collection_id} — "
            f"{'; '.join(failures)}"
        )
    raise NotFound(f"iTunes has no collection {collection_id}")


def _lookup_storefront(collection_id: str, cc: str) -> ItunesAlbum | None:
    """One storefront's lookup; ``None`` = empty (collection not in this
    storefront) so the caller can try the next one."""
    _throttle()
    data = _client.get_json(
        LOOKUP_URL,
        params={
            "id": collection_id,
            "entity": "song",
            "limit": 200,
            "country": cc,
        },
        timeout=_TIMEOUT,
    )
    if not isinstance(data, dict):
        return None
    results = data.get("results") or []
    collection = next(
        (item for item in results if item.get("wrapperType") == "collection"),
        None,
    )
    if collection is None:
        return None

    # entity=song returns the collection first, then its songs — which may
    # arrive out of order on multi-disc releases → sort by disc then track.
    songs = [item for item in results if item.get("wrapperType") == "track"]
    songs.sort(key=lambda s: (s.get("discNumber") or 0, s.get("trackNumber") or 0))

    tracks: list[TrackInput] = []
    for song in songs:
        title = (song.get("trackName") or "").strip()
        if not title:
            continue
        millis = song.get("trackTimeMillis")
        duration = (
            round(millis / 1000)
            if isinstance(millis, (int, float)) and millis >= 0
            else None
        )
        tracks.append(
            TrackInput(position=len(tracks) + 1, title=title, duration_seconds=duration)
        )

    genres = [g for g in [collection.get("primaryGenreName")] if g]
    return ItunesAlbum(
        itunes_id=str(collection.get("collectionId") or collection_id),
        title=(collection.get("collectionName") or "").strip(),
        artist=(collection.get("artistName") or "").strip() or "Unknown Artist",
        year=_year(collection.get("releaseDate")),
        country=_clean_country(collection.get("country")) or cc,
        label=None,  # iTunes exposes no clean label field (only "copyright")
        cover_url=upgrade_art(collection.get("artworkUrl100")),
        tracks=tracks,
        genres=genres,
    )


def _clean_country(country: object) -> str | None:
    if isinstance(country, str):
        cleaned = country.strip().upper()
        return cleaned or None
    return None