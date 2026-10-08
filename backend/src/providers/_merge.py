"""Normalization + merge/dedupe rules for combined search results (PLAN §6).

Comparison-only normalization: lowercase, collapse whitespace, strip featuring
suffixes (``"Artist feat. X"`` → ``"Artist"``). Displayed fields keep the
original provider strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .base import SearchResult

_FEAT_RE = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+.*$", re.IGNORECASE)


@dataclass
class SearchOutcome:
    """Merged results plus which providers failed (for §5's degraded header)."""

    results: list[SearchResult] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)  # e.g. ["deezer"]


def normalize(text: str | None) -> str:
    """Lowercase + collapse whitespace (comparison only)."""
    return " ".join((text or "").split()).strip().lower()


def normalize_artist(artist: str | None) -> str:
    """normalize() plus featuring-suffix stripping (PLAN §6 rule 2)."""
    return _FEAT_RE.sub("", normalize(artist))


def years_match(year_a: int | None, year_b: int | None) -> bool:
    """Years within ±1, or either side missing (PLAN §6 rule 3)."""
    if year_a is None or year_b is None:
        return True
    return abs(year_a - year_b) <= 1


def same_album(a: SearchResult, b: SearchResult) -> bool:
    """True when two rows should collapse into one (artist+title, year ±1)."""
    return (
        normalize_artist(a.artist) == normalize_artist(b.artist)
        and normalize(a.title) == normalize(b.title)
        and years_match(a.year, b.year)
    )


def find_match(
    candidates: list[SearchResult],
    *,
    artist: str,
    title: str,
    year: int | None,
) -> tuple[int, SearchResult] | None:
    """Best candidate for (artist, title, year): exact year first, then ±1,
    then missing-year pairings; ties keep the earliest candidate (stable).
    """
    wanted_artist = normalize_artist(artist)
    wanted_title = normalize(title)
    best: tuple[int, int, SearchResult] | None = None
    for index, candidate in enumerate(candidates):
        if normalize_artist(candidate.artist) != wanted_artist:
            continue
        if normalize(candidate.title) != wanted_title:
            continue
        if not years_match(candidate.year, year):
            continue
        if candidate.year is not None and candidate.year == year:
            score = 0
        elif candidate.year is not None and year is not None:
            score = 1
        else:
            score = 2
        if best is None or score < best[0]:
            best = (score, index, candidate)
    if best is None:
        return None
    return best[1], best[2]


def merge_pair(musicbrainz: SearchResult, deezer: SearchResult) -> SearchResult:
    """Merged row: MB canonical title/artist/year/label, Deezer cover/count,
    carrying both ids (PLAN §6 rule 3)."""
    return SearchResult(
        source="musicbrainz",
        external_id=musicbrainz.external_id,
        title=musicbrainz.title or deezer.title,
        artist=musicbrainz.artist or deezer.artist,
        year=musicbrainz.year if musicbrainz.year is not None else deezer.year,
        track_count=(
            deezer.track_count if deezer.track_count is not None
            else musicbrainz.track_count
        ),
        cover_url=deezer.cover_url or musicbrainz.cover_url,
        label=musicbrainz.label or deezer.label,
        deezer_id=deezer.deezer_id,
        musicbrainz_release_group_id=(
            musicbrainz.musicbrainz_release_group_id or musicbrainz.external_id
        ),
    )


def merge_results(
    deezer_rows: list[SearchResult],
    musicbrainz_rows: list[SearchResult],
    limit: int,
) -> list[SearchResult]:
    """Combine both providers' results (PLAN §6 rules 1-4).

    Pair Deezer rows with matching MusicBrainz rows (deezer_id +
    release-group id → one merged row), dedupe identical albums, and keep a
    stable order: Deezer relevance first, then MusicBrainz.
    """
    unused_musicbrainz = list(musicbrainz_rows)
    emitted: list[SearchResult] = []

    def emit(row: SearchResult) -> None:
        if len(emitted) >= limit:
            return
        if any(same_album(row, seen) for seen in emitted):
            return
        emitted.append(row)

    for deezer_row in deezer_rows:
        if len(emitted) >= limit:
            break
        match = find_match(
            unused_musicbrainz,
            artist=deezer_row.artist,
            title=deezer_row.title,
            year=deezer_row.year,
        )
        if match is not None:
            index, musicbrainz_row = match
            unused_musicbrainz.pop(index)
            emit(merge_pair(musicbrainz_row, deezer_row))
        else:
            emit(deezer_row)

    for musicbrainz_row in unused_musicbrainz:
        if len(emitted) >= limit:
            break
        emit(musicbrainz_row)

    return emitted
