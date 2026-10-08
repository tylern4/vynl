"""Normalization + merge/dedupe rules for combined search results (PLAN §6).

Comparison-only normalization: lowercase, collapse whitespace, strip featuring
suffixes (``"Artist feat. X"`` → ``"Artist"``). Displayed fields keep the
original provider strings.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from .base import SearchResult

_FEAT_RE = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+.*$", re.IGNORECASE)

#: Search-result preference order used to fill a row's fuzzy fields
#: (track_count/cover_url/year) when a later source matches an emitted row.
#: Phase 1 runs Deezer ⊕ MusicBrainz; phases 2a/b absorb iTunes then Discogs
#: on top (issue #12).
PROVIDER_ORDER = ("deezer", "musicbrainz", "itunes", "discogs")


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
    carrying every known id (PLAN §6 rule 3; ids additive since issue #12)."""
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
        deezer_id=deezer.deezer_id or musicbrainz.deezer_id,
        musicbrainz_release_group_id=(
            musicbrainz.musicbrainz_release_group_id or musicbrainz.external_id
        ),
        itunes_id=musicbrainz.itunes_id or deezer.itunes_id,
        discogs_id=musicbrainz.discogs_id or deezer.discogs_id,
    )


def absorb_pair(row: SearchResult, extra: SearchResult) -> SearchResult:
    """Fold one more source's ids onto an emitted row (phase 2, issue #12).

    ``row`` keeps its source/external_id/ordering (Deezer relevance order is
    never disturbed); the extra source only *adds* ids and fills fields the row
    is still missing (year — otherwise a Deezer search row has none — plus
    track_count/cover_url), so the §6 artwork chain Deezer → iTunes → Discogs →
    MusicBrainz holds without rewriting an already-emitted row.
    """
    updates: dict = {}
    for attr in ("deezer_id", "musicbrainz_release_group_id", "itunes_id", "discogs_id"):
        if getattr(row, attr) is None and getattr(extra, attr) is not None:
            updates[attr] = getattr(extra, attr)
    if row.year is None and extra.year is not None:
        updates["year"] = extra.year
    if row.track_count is None and extra.track_count is not None:
        updates["track_count"] = extra.track_count
    if row.cover_url is None and extra.cover_url is not None:
        updates["cover_url"] = extra.cover_url
    return replace(row, **updates) if updates else row


def merge_results(
    rows: Mapping[str, list[SearchResult]],
    limit: int,
) -> list[SearchResult]:
    """Combine every provider's results (PLAN §6 rules 1-4, issue #12).

    ``rows`` maps provider name → its normalized results (Discogs simply absent
    when disabled). Two phases keep the stable order:

    Phase 1 — Deezer ⊕ MusicBrainz unchanged: pair Deezer rows with matching
    MusicBrainz rows (deezer_id + release-group id → one merged row), emit
    Deezer relevance first, then the leftover MusicBrainz rows.

    Phase 2 — absorb iTunes, then Discogs: a matching row folds its ids onto
    the emitted row (and fills missing year/count/cover per §6 preference);
    unmatched rows append at the end, in provider order, deduped as usual.
    """
    deezer_rows = rows.get("deezer") or []
    musicbrainz_rows = rows.get("musicbrainz") or []
    emitted: list[SearchResult] = []

    def emit(row: SearchResult) -> None:
        if len(emitted) >= limit:
            return
        if any(same_album(row, seen) for seen in emitted):
            return
        emitted.append(row)

    # Phase 1 — Deezer relevance first, paired with MusicBrainz.
    unused_musicbrainz = list(musicbrainz_rows)
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

    # Phase 2 — absorb iTunes then Discogs (issue #12). Absorbing into an
    # emitted row never adds a row, so continue even at the limit.
    for name in PROVIDER_ORDER[2:]:
        for extra in rows.get(name) or []:
            match = find_match(
                emitted,
                artist=extra.artist,
                title=extra.title,
                year=extra.year,
            )
            if match is not None:
                index, target = match
                emitted[index] = absorb_pair(target, extra)
            else:
                emit(extra)

    return emitted
