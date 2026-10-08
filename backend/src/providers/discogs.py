"""Discogs provider: release search + release lookup (issue #12).

**Token-gated**: requires ``settings.discogs_token`` (account → Developers →
Generate token). With a blank token Discogs is *disabled*: direct
search/fetch raise ``ProviderError("Discogs is not configured")`` and the
merged search omits it entirely, so the app is fully functional without one.

Rate limits: ~60 req/min authenticated → a module-level 1 req/s floor plus
retry + exponential backoff on HTTP 429 / ``X-Discogs-Ratelimit-Remaining: 0``.
Soft failures degrade (the merge layer treats a Discogs failure as one degraded
provider); hard 5xx responses raise.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

import httpx

from ..config import settings
from . import _client
from .base import NotFound, ProviderError, SearchResult, TrackInput

SEARCH_URL = f"{_client.DISCOGS_BASE}/database/search"
RELEASE_URL = f"{_client.DISCOGS_BASE}/releases/{{release_id}}"

USER_AGENT = "vynl/0.1.0 (+https://github.com/tylern4/vynl)"
_HEADERS = {"User-Agent": USER_AGENT}

# ~60 req/min authenticated → floor of 1 req/s; retried 429s back off.
_MIN_INTERVAL = 1.0
_RETRIES = 3
_BACKOFF_BASE = 1.0

_throttle_lock = threading.Lock()
_next_slot = 0.0

_DIGITS_RE = re.compile(r"^\d+$")
#: Discogs returns these placeholder images when a release has no artwork.
_SPACER_RE = re.compile(r"(spacer\.gif|duck\.gif)")
#: Search titles are usually ``"Artist – Title"`` (en-dash) or ``"Artist - Title"``.
_TITLE_SPLIT_RE = re.compile(r"\s+(?:\u2013|-)\s+")


@dataclass
class DiscogsAlbum:
    """Release metadata normalized away from the Discogs payload."""

    discogs_id: str
    title: str
    artist: str
    year: int | None
    country: str | None
    label: str | None
    cover_url: str | None
    tracks: list[TrackInput]
    genres: list[str] = field(default_factory=list)
    styles: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)


def is_enabled() -> bool:
    """Discogs contributes to merged searches only when a token is configured."""
    return bool((settings.discogs_token or "").strip())


def _require_enabled() -> None:
    if not is_enabled():
        raise ProviderError("Discogs is not configured")


def _throttle() -> None:
    """Reserve the next request slot, sleeping to a 1 req/s floor."""
    global _next_slot
    with _throttle_lock:
        now = time.monotonic()
        wait = _next_slot - now
        if wait > 0:
            time.sleep(wait)
        _next_slot = time.monotonic() + _MIN_INTERVAL


def _ratelimited(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    header = response.headers.get("X-Discogs-Ratelimit-Remaining")
    if header is not None:
        try:
            return int(header) == 0
        except ValueError:
            return False
    return False


def _get_json(url: str, *, params: dict) -> dict:
    """GET + decode, with the 1 req/s floor and 429 retry/backoff.

    Raises :class:`NotFound` on 404 and :class:`ProviderError` on transport
    errors, hard 5xx, or an exhausted rate-limit retry budget.
    """
    _throttle()
    client = _client.get_client()
    response: httpx.Response | None = None
    for attempt in range(_RETRIES + 1):
        try:
            response = client.get(url, params=params, headers=_HEADERS)
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"request to {_client.response_host(url)} failed: {exc}"
            ) from exc
        if not _ratelimited(response):
            break
        time.sleep(_BACKOFF_BASE * (2**attempt))
    assert response is not None
    if response.status_code == 404:
        raise NotFound(f"HTTP {response.status_code} from {response.url}")
    if response.status_code >= 500:
        raise ProviderError(
            f"HTTP {response.status_code} from {response.url}: {response.text[:200]}"
        )
    if response.status_code != 200:
        raise ProviderError(
            f"HTTP {response.status_code} from {response.url}: {response.text[:200]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError(f"invalid JSON from {response.url}") from exc


def search(query: str, limit: int = 20) -> list[SearchResult]:
    """``/database/search?q=…&type=release`` → normalized rows (issue #12)."""
    _require_enabled()
    data = _get_json(
        SEARCH_URL,
        params={
            "q": query,
            "type": "release",
            "per_page": max(1, min(int(limit), 100)),
            "token": settings.discogs_token,
        },
    )
    results: list[SearchResult] = []
    for item in data.get("results") or []:
        release_id = item.get("id")
        raw_title = (item.get("title") or "").strip()
        if release_id is None or not raw_title:
            continue
        artist, title = split_title(raw_title)
        label = _first_label(item.get("label")) or _first_label(
            item.get("labels")
        )
        results.append(
            SearchResult(
                source="discogs",
                external_id=str(release_id),
                title=title or raw_title,
                artist=artist or "Unknown Artist",
                year=_year(item.get("year")),
                label=label or None,
                cover_url=_usable_cover(item.get("cover_image")),
                discogs_id=str(release_id),
            )
        )
    return results


def split_title(raw_title: str) -> tuple[str | None, str | None]:
    """Split ``"Artist – Title"`` on the first spaced dash (en or ASCII).

    Returns ``(artist, title)``; a title with no separator → ``(None, raw)``.
    """
    match = _TITLE_SPLIT_RE.search(raw_title)
    if match is None:
        return None, raw_title
    artist = raw_title[: match.start()].strip() or None
    title = raw_title[match.end() :].strip() or None
    return artist, title


def fetch_album(release_id: str) -> DiscogsAlbum:
    """``/releases/{id}`` → full metadata + tracklist (issue #12)."""
    _require_enabled()
    if not _DIGITS_RE.match(str(release_id)):
        raise NotFound(f"invalid Discogs release id: {release_id!r}")
    url = RELEASE_URL.format(release_id=str(release_id))
    data = _get_json(url, params={"token": settings.discogs_token})
    if not isinstance(data, dict):
        raise ProviderError(f"unexpected Discogs payload for {url}")

    tracks: list[TrackInput] = []
    for entry in data.get("tracklist") or []:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        tracks.append(
            TrackInput(
                position=len(tracks) + 1,
                title=title,
                duration_seconds=_duration_to_seconds(entry.get("duration")),
            )
        )

    label = _first_label(data.get("labels")) or _first_label(data.get("label"))
    genres = [g for g in (data.get("genres") or []) if g]
    styles = [s for s in (data.get("styles") or []) if s]
    formats = [
        _format_name(fmt)
        for fmt in (data.get("formats") or [])
        if _format_name(fmt)
    ]
    return DiscogsAlbum(
        discogs_id=str(data.get("id") or release_id),
        title=(data.get("title") or "").strip() or "Unknown Title",
        artist=_join_artists(data.get("artists")) or "Unknown Artist",
        year=_year(data.get("year")),
        country=_clean_country(data.get("country")),
        label=label or None,
        cover_url=_pick_image(data.get("images") or []),
        tracks=tracks,
        genres=genres,
        styles=styles,
        formats=formats,
    )


def _usable_cover(url: object) -> str | None:
    """Discogs placeholder art (``spacer.gif`` / ``duck.gif``) counts as none."""
    if not isinstance(url, str) or not url.strip():
        return None
    return None if _SPACER_RE.search(url) else url.strip()


def _first_label(value: object) -> str | None:
    """First label name from the shapes Discogs returns.

    Search rows carry ``label`` as a list of strings; release payloads carry
    ``labels`` as a list of dicts. Tolerate either shape (and a bare string).
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        for entry in value:
            if isinstance(entry, str):
                name = entry
            else:
                name = entry.get("name") if isinstance(entry, dict) else None
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _pick_image(images: list[dict]) -> str | None:
    """First usable image — prefer full-size >=300px, ``uri150`` last resort."""
    for image in images:
        uri = image.get("uri")
        if uri and (image.get("width") or 0) >= 300:
            return uri
    for image in images:
        if image.get("uri"):
            return image["uri"]
    for image in images:
        if image.get("uri150"):
            return image["uri150"]
    return None


def _join_artists(artists: list | None) -> str:
    """Flatten Discogs artist credits (name + join phrase), like MB credits."""
    if not artists:
        return ""
    return "".join(
        f"{entry.get('name', '')}{entry.get('join') or ''}" for entry in artists
    ).strip()


def _format_name(fmt: dict) -> str:
    name = (fmt.get("name") or "").strip()
    descriptions = [d for d in (fmt.get("descriptions") or []) if d]
    return " ".join(p for p in [name, *descriptions] if p).strip()


def _duration_to_seconds(duration: object) -> int | None:
    """``"MM:SS"`` / ``"H:MM:SS"`` → seconds; null-safe (None/garbage → None)."""
    if not isinstance(duration, str):
        return None
    parts = duration.strip().split(":")
    if not parts or len(parts) > 3:
        return None
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if any(number < 0 for number in numbers):
        return None
    seconds = 0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds


def _year(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
        return int(value[:4])
    return None


def _clean_country(country: object) -> str | None:
    if isinstance(country, str):
        cleaned = country.strip().upper()
        return cleaned or None
    return None