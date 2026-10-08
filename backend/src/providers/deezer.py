"""Deezer provider: album search + album lookup (PLAN §6).

No API key and no explicit rate limit. Quirk worth knowing: Deezer answers
missing resources with **HTTP 200** and an ``{"error": {...}}`` body, so
``_unwrap`` maps those onto NotFound/ProviderError.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import _client
from .base import NotFound, ProviderError, SearchResult, TrackInput

SEARCH_URL = f"{_client.DEEZER_BASE}/search/album"
ALBUM_URL = f"{_client.DEEZER_BASE}/album/{{album_id}}"

_DIGITS_RE = re.compile(r"^\d+$")


@dataclass
class DeezerAlbum:
    """Album metadata normalized away from the Deezer payload."""

    deezer_id: int
    title: str
    artist: str
    year: int | None
    label: str | None
    cover_url: str | None
    tracks: list[TrackInput]
    genres: list[str] = field(default_factory=list)


def _unwrap(data: object, url: str):
    """Deezer reports errors in-body (HTTP 200); turn them into protocol errors."""
    if isinstance(data, dict) and "error" in data:
        error = data.get("error") or {}
        message = error.get("message") or "unknown error"
        code = error.get("code")
        # Code 800 ("no data") is Deezer's flavour of 404.
        if code == 800 or message == "no data":
            raise NotFound(f"deezer has no data for {url}: {message}")
        raise ProviderError(f"deezer error {code} from {url}: {message}")
    return data


def _year(date: object) -> int | None:
    if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit():
        return int(date[:4])
    return None


def search(query: str, limit: int = 20) -> list[SearchResult]:
    """Album search: ``/search/album?q=…&limit=…`` (PLAN §6)."""
    data = _unwrap(
        _client.get_json(SEARCH_URL, params={"q": query, "limit": limit}),
        SEARCH_URL,
    )
    results: list[SearchResult] = []
    for item in data.get("data", []) if isinstance(data, dict) else []:
        album_id = item.get("id")
        title = (item.get("title") or "").strip()
        if album_id is None or not title:
            continue
        artist = ((item.get("artist") or {}).get("name") or "").strip()
        results.append(
            SearchResult(
                source="deezer",
                external_id=str(album_id),
                title=title,
                artist=artist or "Unknown Artist",
                # /search/album rows carry no release_date → year stays None
                # unless the payload includes one; pairing tolerates that.
                year=_year(item.get("release_date")),
                track_count=item.get("nb_tracks"),
                cover_url=_cover(item),
                deezer_id=int(album_id),
            )
        )
    return results


def _cover(item: dict) -> str | None:
    return item.get("cover_xl") or item.get("cover_big") or item.get("cover")


def fetch_album(album_id: str) -> DeezerAlbum:
    """Fetch ``/album/{id}`` → full metadata + tracklist (PLAN §6)."""
    if not _DIGITS_RE.match(str(album_id)):
        raise NotFound(f"invalid Deezer album id: {album_id!r}")
    url = ALBUM_URL.format(album_id=album_id)
    data = _unwrap(_client.get_json(url), url)
    if not isinstance(data, dict):
        raise ProviderError(f"unexpected deezer payload for {url}")

    artist = ((data.get("artist") or {}).get("name") or "").strip()
    raw_tracks = ((data.get("tracks") or {}).get("data")) or []
    tracks: list[TrackInput] = []
    for track in raw_tracks:
        title = (track.get("title") or "").strip()
        if not title:
            continue
        tracks.append(
            TrackInput(
                position=len(tracks) + 1,
                title=title,
                # Deezer durations are already seconds (PLAN §6).
                duration_seconds=track.get("duration"),
            )
        )
    genres = [
        genre["name"]
        for genre in ((data.get("genres") or {}).get("data") or [])
        if genre.get("name")
    ]
    return DeezerAlbum(
        deezer_id=int(data.get("id") or album_id),
        title=(data.get("title") or "").strip(),
        artist=artist or "Unknown Artist",
        year=_year(data.get("release_date")),
        label=(data.get("label") or "").strip() or None,
        cover_url=_cover(data),
        tracks=tracks,
        genres=genres,
    )
