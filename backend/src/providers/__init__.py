"""Music metadata providers: MusicBrainz, Deezer, Cover Art Archive (PLAN §6).

Public interface — routers import from here, never from submodules directly:

* ``search_albums(query, limit=20)`` — concurrent search of both providers,
  normalized and merged/deduped per §6; degrades to the surviving provider,
  raises ``ProviderError`` only when *both* fail.
* ``search_albums_detailed(query, limit=20)`` — same, plus ``SearchOutcome``
  carrying which providers failed, so the router can set §5's
  ``X-Search-Degraded`` header.
* ``import_album(source, external_id)`` — full metadata + tracklist + cover
  URL. The wire body only carries one id, so the counterpart provider's id is
  discovered by a normalized artist/title/year search ("twin discovery") and
  either source can fall back independently.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor

from . import _client, coverart, deezer, musicbrainz
from ._merge import (
    SearchOutcome,
    find_match,
    merge_results,
    normalize,
    normalize_artist,
)
from .base import ImportedAlbum, NotFound, ProviderError, SearchResult, TrackInput

__all__ = [
    "ImportedAlbum",
    "NotFound",
    "ProviderError",
    "SearchOutcome",
    "SearchResult",
    "TrackInput",
    "import_album",
    "search_albums",
    "search_albums_detailed",
    "set_client",
]

#: Upper bound applied to ``limit`` (MB and Deezer both cap at 100 anyway).
_MAX_LIMIT = 100

#: Providers in stable order for ``SearchOutcome.degraded``.
_PROVIDERS = ("musicbrainz", "deezer")


def set_client(client) -> None:
    """Test seam: inject an ``httpx.Client`` (e.g. ``httpx.MockTransport``)."""
    _client.set_client(client)


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), _MAX_LIMIT))


def _settle(future: Future) -> tuple[list[SearchResult], ProviderError | None]:
    """Collect a provider future; ProviderError/NotFound → degraded, not raised."""
    try:
        return future.result(), None
    except ProviderError as exc:  # NotFound is a ProviderError subclass
        return [], exc


def search_albums(query: str, limit: int = 20) -> list[SearchResult]:
    """Search Deezer and MusicBrainz, merge and dedupe (PLAN §6).

    Raises ProviderError only if every provider fails; a single failing
    provider degrades to the other's results.
    """
    return search_albums_detailed(query, limit).results


def search_albums_detailed(query: str, limit: int = 20) -> SearchOutcome:
    """Like :func:`search_albums` but also reports degraded providers (§5)."""
    if not query or not query.strip():
        return SearchOutcome()
    limit = _clamp_limit(limit)
    with ThreadPoolExecutor(max_workers=2) as pool:
        deezer_future = pool.submit(deezer.search, query, limit)
        musicbrainz_future = pool.submit(musicbrainz.search, query, limit)
        deezer_rows, deezer_error = _settle(deezer_future)
        musicbrainz_rows, musicbrainz_error = _settle(musicbrainz_future)

    errors = {"musicbrainz": musicbrainz_error, "deezer": deezer_error}
    degraded = [name for name in _PROVIDERS if errors[name] is not None]
    if len(degraded) == len(_PROVIDERS):
        detail = "; ".join(
            f"{name}: {errors[name].reason}" for name in _PROVIDERS
        )
        raise ProviderError(f"all music providers failed — {detail}")
    return SearchOutcome(
        results=merge_results(deezer_rows, musicbrainz_rows, limit),
        degraded=degraded,
    )


def import_album(source: str, external_id: str) -> ImportedAlbum:
    """Fetch full metadata + tracklist for one album from its source.

    Raises NotFound for unknown ids, ProviderError for upstream failures.
    """
    if source == "musicbrainz":
        return _import_musicbrainz(str(external_id))
    if source == "deezer":
        return _import_deezer(str(external_id))
    raise ProviderError(f"unknown music source: {source!r}")


def _import_musicbrainz(external_id: str) -> ImportedAlbum:
    # Primary source: failures propagate (routers map them to 404/502).
    album = musicbrainz.fetch_album(external_id)
    # Counterpart discovery is best-effort — Deezer being down or 404ing
    # degrades to a MusicBrainz-only import (PLAN §6 import rule 1).
    deezer_album = _find_deezer_twin(album.title, album.artist, album.year)
    return _assemble(
        "musicbrainz",
        external_id,
        mb=album,
        deezer_album=deezer_album,
        rg_id=album.release_group_id,
        year_hint=None,
    )


def _import_deezer(external_id: str) -> ImportedAlbum:
    album = deezer.fetch_album(external_id)
    twin = _find_musicbrainz_twin(album.title, album.artist, album.year)
    mb_album = None
    if twin is not None:
        rg_id = twin.musicbrainz_release_group_id or twin.external_id
        try:
            mb_album = musicbrainz.fetch_album(rg_id)
        except ProviderError:
            # Release fetch failed — keep the rg id + search date so CAA and
            # the musicbrainz_release_group_id column still get filled in.
            mb_album = None
    resolved_rg = (
        mb_album.release_group_id
        if mb_album is not None
        else (twin.musicbrainz_release_group_id or twin.external_id)
        if twin is not None
        else None
    )
    return _assemble(
        "deezer",
        external_id,
        mb=mb_album,
        deezer_album=album,
        rg_id=resolved_rg,
        year_hint=twin.year if twin is not None else None,
    )


def _find_deezer_twin(
    title: str, artist: str, year: int | None
) -> deezer.DeezerAlbum | None:
    """Find + fetch the Deezer counterpart of a MusicBrainz album, or None."""
    query = f"{artist} {title}".strip()
    if not query:
        return None
    try:
        candidates = deezer.search(query, limit=10)
    except ProviderError:
        return None
    match = find_match(candidates, artist=artist, title=title, year=year)
    if match is None:
        return None
    try:
        return deezer.fetch_album(match[1].external_id)
    except ProviderError:
        # e.g. the album 404'd between search and fetch → single-source import.
        return None


def _find_musicbrainz_twin(
    title: str, artist: str, year: int | None
) -> SearchResult | None:
    """Find the MusicBrainz release-group counterpart of a Deezer album."""
    query = _lucene_query(artist, title)
    if not query:
        return None
    try:
        candidates = musicbrainz.search(query, limit=10)
    except ProviderError:
        return None
    match = find_match(candidates, artist=artist, title=title, year=year)
    return match[1] if match is not None else None


def _lucene_query(artist: str, title: str) -> str:
    """Fielded MusicBrainz query with Lucene-safe quoted phrases."""

    def phrase(text: str) -> str:
        escaped = text.strip().replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    parts = []
    if artist.strip():
        parts.append(f"artist:{phrase(artist)}")
    if title.strip():
        parts.append(f"releasegroup:{phrase(title)}")
    return " AND ".join(parts)


def _assemble(
    source: str,
    external_id: str,
    *,
    mb: musicbrainz.MBAlbum | None,
    deezer_album: deezer.DeezerAlbum | None,
    rg_id: str | None,
    year_hint: int | None,
) -> ImportedAlbum:
    """Mix canonical MusicBrainz metadata with Deezer tracklist/cover (§6).

    With both sources: MB wins for title/artist/year/label/country, Deezer
    wins for tracks and cover_url. Either side may be None (independent
    per-source fallback).
    """
    def first_known(*values):
        for value in values:
            if value is not None:
                return value
        return None

    if mb is not None:
        title, artist = mb.title, mb.artist
        label, country = mb.label, mb.country
    else:
        title, artist = deezer_album.title, deezer_album.artist
        label, country = deezer_album.label, None

    deezer_cover = deezer_album.cover_url if deezer_album is not None else None
    if deezer_album is not None:
        deezer_id: int | None = deezer_album.deezer_id
        genres = list(deezer_album.genres)
    else:
        deezer_id, genres = None, []

    if deezer_album is not None and deezer_album.tracks:
        tracks = deezer_album.tracks  # preferred tracklist source when both (§6)
    else:
        tracks = mb.tracks if mb is not None else []

    metadata: dict = {}
    if mb is not None:
        metadata["musicbrainz_release_id"] = mb.release_id
    if genres:
        metadata["genres"] = genres

    # Source provenance (issue #13, additive — import behavior unchanged):
    # the breakdown mirrors exactly how tracks/artwork/metadata were chosen.
    if deezer_album is not None and deezer_album.tracks:
        tracklist_source = "deezer"  # preferred tracklist when both (§6)
    elif mb is not None and mb.tracks:
        tracklist_source = "musicbrainz"
    else:
        tracklist_source = None

    cover_url = coverart.resolve_cover(
        deezer_cover=deezer_cover,
        release_group_id=rg_id,
        release_id=mb.release_id if mb is not None else None,
    )
    if deezer_cover:
        artwork_source = "deezer"
    elif cover_url is not None:
        artwork_source = "cover_art_archive"
    else:
        artwork_source = None

    # Every contributing source's full tracklist (non-empty only); the
    # preferred one is always included so the preview can compare pressings.
    tracklists_by_source: dict[str, list[TrackInput]] = {}
    if deezer_album is not None and deezer_album.tracks:
        tracklists_by_source["deezer"] = deezer_album.tracks
    if mb is not None and mb.tracks:
        tracklists_by_source["musicbrainz"] = mb.tracks

    return ImportedAlbum(
        source=source,
        external_id=external_id,
        title=title,
        artist=artist,
        year=first_known(
            mb.year if mb is not None else None,
            year_hint,
            deezer_album.year if deezer_album is not None else None,
        ),
        label=label,
        country=country,
        musicbrainz_release_group_id=rg_id,
        deezer_id=deezer_id,
        cover_url=cover_url,
        metadata=metadata,
        tracks=tracks,
        metadata_source="musicbrainz" if mb is not None else (
            "deezer" if deezer_album is not None else None
        ),
        tracklist_source=tracklist_source,
        artwork_source=artwork_source,
        tracklists_by_source=tracklists_by_source,
    )
