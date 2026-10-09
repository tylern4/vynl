"""MusicBrainz provider: release-group search + release lookup (PLAN §6).

Policy: custom User-Agent with ``settings.musicbrainz_contact`` and a hard
maximum of 1 request/second, enforced by a module-level lock + minimum-interval
guard (:func:`_throttle`). Search calls that hit MusicBrainz concurrently (the
ThreadPoolExecutor in ``search_albums``) queue up behind the same lock.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass

from ..config import settings
from ..version import APP_NAME, APP_VERSION
from . import _client
from .base import NotFound, SearchResult, TrackInput

RELEASE_GROUP_SEARCH = f"{_client.MUSICBRAINZ_BASE}/release-group"
RELEASE_GROUP_LOOKUP = f"{_client.MUSICBRAINZ_BASE}/release-group/{{mbid}}"
RELEASE_LOOKUP = f"{_client.MUSICBRAINZ_BASE}/release/{{mbid}}"
RELEASE_INC = "recordings+artist-credits+labels+release-groups"

# MusicBrainz asks for a max of 1 request/second per client (PLAN §6).
_MIN_INTERVAL = 1.0
_throttle_lock = threading.Lock()
_next_slot = 0.0

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass
class MBAlbum:
    """Release metadata normalized away from the MusicBrainz payload."""

    title: str
    artist: str
    year: int | None
    label: str | None
    country: str | None
    release_id: str
    release_group_id: str | None
    tracks: list[TrackInput]


def _throttle() -> None:
    """Reserve the next request slot, sleeping until 1/s spacing is satisfied."""
    global _next_slot
    with _throttle_lock:
        now = time.monotonic()
        wait = _next_slot - now
        if wait > 0:
            time.sleep(wait)
        _next_slot = time.monotonic() + _MIN_INTERVAL


def _headers() -> dict[str, str]:
    return {"User-Agent": f"{APP_NAME}/{APP_VERSION} ({settings.musicbrainz_contact})"}


def _get(url: str, *, params: dict, not_found_statuses: tuple[int, ...] = (404,)):
    _throttle()
    return _client.get_json(
        url,
        params=params,
        headers=_headers(),
        not_found_statuses=not_found_statuses,
    )


def _year(date: object) -> int | None:
    """Parse a MusicBrainz partial date (``1980``, ``1980-10``, ``1980-10-01``)."""
    if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit():
        return int(date[:4])
    return None


def join_credit(credit: list | None) -> str:
    """Flatten an artist-credit list (``name`` + ``joinphrase``) to one string."""
    if not credit:
        return ""
    return "".join(
        f"{entry.get('name', '')}{entry.get('joinphrase') or ''}" for entry in credit
    ).strip()


def _validate_mbid(mbid: str) -> None:
    if not _UUID_RE.match(str(mbid).strip()):
        raise NotFound(f"invalid MusicBrainz id: {mbid!r}")


def search(query: str, limit: int = 20) -> list[SearchResult]:
    """Release-group search: ``/ws/2/release-group?query=…&fmt=json`` (PLAN §6)."""
    data = _get(
        RELEASE_GROUP_SEARCH,
        params={"query": query, "limit": limit, "fmt": "json"},
    )
    results: list[SearchResult] = []
    for group in data.get("release-groups", []):
        mbid = group.get("id")
        title = (group.get("title") or "").strip()
        if not mbid or not title:
            continue
        results.append(
            SearchResult(
                source="musicbrainz",
                external_id=str(mbid),
                title=title,
                artist=join_credit(group.get("artist-credit")) or "Unknown Artist",
                year=_year(group.get("first-release-date")),
                musicbrainz_release_group_id=str(mbid),
            )
        )
    return results


def fetch_album(mbid: str) -> MBAlbum:
    """Resolve a release-group MBID to full release metadata.

    Accepts a bare release MBID too (falls through to the release lookup when
    the id is not a release group). Raises ``NotFound`` for unknown ids and
    ``ProviderError`` for upstream failures.
    """
    _validate_mbid(mbid)
    try:
        group = _get(
            RELEASE_GROUP_LOOKUP.format(mbid=mbid),
            params={"inc": "releases", "fmt": "json"},
            not_found_statuses=(400, 404),  # MB answers 400 "Invalid mbid."
        )
    except NotFound:
        # Not a release group — maybe the caller has a release MBID.
        return _fetch_release(mbid, release_group_id=None)
    releases = group.get("releases") or []
    if not releases:
        raise NotFound(f"release group {mbid} has no releases")
    release_id = _pick_release(releases)
    return _fetch_release(release_id, release_group_id=group.get("id") or mbid)


def _pick_release(releases: list[dict]) -> str:
    """Prefer official releases, then the earliest date (stable within ties)."""
    def key(release: dict):
        date = release.get("date") or "9999-99-99"
        official = 0 if release.get("status") == "Official" else 1
        return (official, date)

    return sorted(releases, key=key)[0]["id"]


def _fetch_release(release_id: str, release_group_id: str | None) -> MBAlbum:
    data = _get(
        RELEASE_LOOKUP.format(mbid=release_id),
        params={"inc": RELEASE_INC, "fmt": "json"},
        not_found_statuses=(400, 404),
    )
    group = data.get("release-group") or {}
    rg_id = group.get("id") or release_group_id

    date = data.get("date") or group.get("first-release-date")
    title = (data.get("title") or group.get("title") or "").strip()
    artist = (
        join_credit(data.get("artist-credit"))
        or join_credit(group.get("artist-credit"))
        or "Unknown Artist"
    )
    label = None
    for info in data.get("label-info") or []:
        name = ((info or {}).get("label") or {}).get("name")
        if name:
            label = name
            break

    return MBAlbum(
        title=title,
        artist=artist,
        year=_year(date),
        label=label,
        country=data.get("country") or None,
        release_id=str(data.get("id") or release_id),
        release_group_id=str(rg_id) if rg_id else None,
        tracks=_parse_tracks(data.get("media") or []),
    )


def _parse_tracks(media: list[dict]) -> list[TrackInput]:
    """Flatten media/track lists; ``length`` is milliseconds → seconds (PLAN §6)."""
    tracks: list[TrackInput] = []
    position = 0
    for medium in media:
        offset = medium.get("track-offset")
        for index, track in enumerate(medium.get("tracks") or [], start=1):
            track_position = track.get("position")
            if offset is not None and isinstance(track_position, int):
                position = offset + track_position
            else:
                position += 1
            title = (track.get("title") or "").strip()
            if not title:
                continue
            length = track.get("length")
            duration = round(length / 1000) if isinstance(length, (int, float)) else None
            tracks.append(
                TrackInput(position=position, title=title, duration_seconds=duration)
            )
    tracks.sort(key=lambda track: track.position)
    return tracks
