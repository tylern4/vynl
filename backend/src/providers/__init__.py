"""Music metadata providers: MusicBrainz, Deezer, iTunes, Discogs (+ CAA).

Public interface — routers import from here, never from submodules directly:

* ``search_albums(query, limit=20)`` — concurrent search of the enabled
  providers (MusicBrainz + Deezer + iTunes always, plus Discogs when a token is
  configured), normalized and merged/deduped per §6; degrades to the surviving
  providers, raises ``ProviderError`` only when *all* fail.
* ``search_albums_detailed(query, limit=20)`` — same, plus ``SearchOutcome``
  carrying which providers failed, so the router can set §5's
  ``X-Search-Degraded`` header.
* ``import_album(source, external_id)`` — full metadata + tracklist + cover
  URL. The wire body only carries one id, so the counterpart providers' ids are
  discovered by a normalized artist/title/year search ("twin discovery") and
  each source can fall back independently. Any of the four sources is valid.

Import preference order (§6, issue #12): Deezer → iTunes → Discogs →
MusicBrainz for tracklist and artwork; MusicBrainz stays the canonical
metadata source when its twin is known, otherwise the requested source's own
album wins, then the first available provider.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor

from . import _client, coverart, deezer, discogs, itunes, musicbrainz
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

#: Providers in stable order for the fan-out, ``SearchOutcome.degraded``, and
#: the all-failed error detail. Discogs is skipped at runtime when its token
#: is blank (it is absent from searches entirely, per §6 / issue #12).
_PROVIDERS = ("musicbrainz", "deezer", "itunes", "discogs")


def set_client(client) -> None:
    """Test seam: inject an ``httpx.Client`` (e.g. ``httpx.MockTransport``)."""
    _client.set_client(client)


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), _MAX_LIMIT))


def _enabled_providers() -> tuple[str, ...]:
    """The providers actually queried right now (Discogs needs a token)."""
    return _PROVIDERS if discogs.is_enabled() else _PROVIDERS[:3]


def _settle(future: Future) -> tuple[list[SearchResult], ProviderError | None]:
    """Collect a provider future; ProviderError/NotFound → degraded, not raised."""
    try:
        return future.result(), None
    except ProviderError as exc:  # NotFound is a ProviderError subclass
        return [], exc


def _search_provider(name: str, query: str, limit: int) -> list[SearchResult]:
    if name == "deezer":
        return deezer.search(query, limit)
    if name == "musicbrainz":
        return musicbrainz.search(query, limit)
    if name == "itunes":
        return itunes.search(query, limit)
    if name == "discogs":
        return discogs.search(query, limit)
    raise AssertionError(f"unknown provider name: {name!r}")  # pragma: no cover


def search_albums(query: str, limit: int = 20) -> list[SearchResult]:
    """Search all enabled providers, merge and dedupe (PLAN §6).

    Raises ProviderError only if every provider fails; a single failing
    provider degrades to the others' results.
    """
    return search_albums_detailed(query, limit).results


def search_albums_detailed(query: str, limit: int = 20) -> SearchOutcome:
    """Like :func:`search_albums` but also reports degraded providers (§5)."""
    if not query or not query.strip():
        return SearchOutcome()
    limit = _clamp_limit(limit)
    names = _enabled_providers()
    rows: dict[str, list[SearchResult]] = {}
    errors: dict[str, ProviderError | None] = {}
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        futures = {
            name: pool.submit(_search_provider, name, query, limit) for name in names
        }
        for name in names:
            rows[name], errors[name] = _settle(futures[name])

    degraded = [name for name in names if errors[name] is not None]
    if len(degraded) == len(names):
        detail = "; ".join(f"{name}: {errors[name].reason}" for name in names)
        raise ProviderError(f"all music providers failed — {detail}")
    return SearchOutcome(
        results=merge_results(rows, limit),
        degraded=degraded,
    )


def import_album(source: str, external_id: str) -> ImportedAlbum:
    """Fetch full metadata + tracklist for one album from its source.

    Raises NotFound for unknown ids, ProviderError for upstream failures and
    unknown sources.
    """
    if source == "musicbrainz":
        return _import_musicbrainz(str(external_id))
    if source == "deezer":
        return _import_deezer(str(external_id))
    if source == "itunes":
        return _import_itunes(str(external_id))
    if source == "discogs":
        return _import_discogs(str(external_id))
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
    mb_album, resolved_rg, year_hint = _resolve_musicbrainz_twin(
        album.title, album.artist, album.year
    )
    return _assemble(
        "deezer",
        external_id,
        mb=mb_album,
        deezer_album=album,
        rg_id=resolved_rg,
        year_hint=year_hint,
    )


def _import_itunes(collection_id: str) -> ImportedAlbum:
    """iTunes collection import: MB twin for canonical metadata + rg id, then
    best-effort Deezer twin for the preferred tracklist/artwork (#12)."""
    album = itunes.fetch_album(collection_id)
    mb_album, resolved_rg, year_hint = _resolve_musicbrainz_twin(
        album.title, album.artist, album.year
    )
    deezer_album = _find_deezer_twin(album.title, album.artist, album.year)
    return _assemble(
        "itunes",
        collection_id,
        mb=mb_album,
        deezer_album=deezer_album,
        itunes_album=album,
        rg_id=resolved_rg,
        year_hint=year_hint,
    )


def _import_discogs(release_id: str) -> ImportedAlbum:
    """Discogs release import: same twin discovery as iTunes, with the Discogs
    album feeding formats/styles + its own tracklist/artwork fallback (#12)."""
    album = discogs.fetch_album(release_id)
    mb_album, resolved_rg, year_hint = _resolve_musicbrainz_twin(
        album.title, album.artist, album.year
    )
    deezer_album = _find_deezer_twin(album.title, album.artist, album.year)
    return _assemble(
        "discogs",
        release_id,
        mb=mb_album,
        deezer_album=deezer_album,
        discogs_album=album,
        rg_id=resolved_rg,
        year_hint=year_hint,
    )


def _resolve_musicbrainz_twin(
    title: str, artist: str, year: int | None
) -> tuple[musicbrainz.MBAlbum | None, str | None, int | None]:
    """Best-effort MusicBrainz resolution for (artist, title, year) → the
    fetched release, its release-group id, and the twin's year as a hint.

    Returns ``(None, None, None)`` on any failure — twin discovery never fails
    an import (PLAN §6 rule 4); a release fetch failing still keeps the rg id
    so CAA and the ``musicbrainz_release_group_id`` column can be filled in.
    """
    twin = _find_musicbrainz_twin(title, artist, year)
    if twin is None:
        return None, None, None
    rg_id = twin.musicbrainz_release_group_id or twin.external_id
    try:
        mb_album = musicbrainz.fetch_album(rg_id)
    except ProviderError:
        mb_album = None
    resolved_rg = mb_album.release_group_id if mb_album is not None else rg_id
    return mb_album, resolved_rg, twin.year


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
    itunes_album: itunes.ItunesAlbum | None = None,
    discogs_album: discogs.DiscogsAlbum | None = None,
    rg_id: str | None,
    year_hint: int | None,
) -> ImportedAlbum:
    """Mix canonical metadata with the best tracklist/artwork (§6, issue #12).

    Canonical metadata: MusicBrainz when its twin is known, else the requested
    source's own album, else the first provider that answered. Tracklist and
    artwork preference: Deezer → iTunes → Discogs → MusicBrainz (CAA after all
    providers). Each album may be ``None`` (independent per-source fallback).
    """
    def first_known(*values):
        for value in values:
            if value is not None:
                return value
        return None

    # (source, album) in the preference order used for metadata fallback.
    source_albums = [
        ("musicbrainz", mb),
        ("deezer", deezer_album),
        ("itunes", itunes_album),
        ("discogs", discogs_album),
    ]
    meta_album: object | None = mb
    meta_source: str | None = "musicbrainz"
    if mb is None:
        meta_album = dict(source_albums).get(source)
        meta_source = source if meta_album is not None else None
        if meta_album is None:
            for candidate_source, candidate in source_albums:
                if candidate is not None:
                    meta_album, meta_source = candidate, candidate_source
                    break
    if meta_album is not None:
        title, artist = meta_album.title, meta_album.artist
        label = meta_album.label
        country = first_known(getattr(meta_album, "country", None), None)
    else:
        title, artist, label, country = "", "Unknown Artist", None, None

    deezer_cover = deezer_album.cover_url if deezer_album is not None else None
    deezer_id = deezer_album.deezer_id if deezer_album is not None else None
    itunes_id = itunes_album.itunes_id if itunes_album is not None else None
    discogs_id = discogs_album.discogs_id if discogs_album is not None else None

    # Genres from every contributor, Deezer → iTunes → Discogs, deduped.
    genres: list[str] = []
    for album in (deezer_album, itunes_album, discogs_album):
        for genre in (album.genres if album is not None else []):
            if genre not in genres:
                genres.append(genre)

    # Tracklist preference: Deezer → iTunes → Discogs → MusicBrainz (§6).
    if deezer_album is not None and deezer_album.tracks:
        tracks: list[TrackInput] = deezer_album.tracks
        tracklist_source = "deezer"
    elif itunes_album is not None and itunes_album.tracks:
        tracks = itunes_album.tracks
        tracklist_source = "itunes"
    elif discogs_album is not None and discogs_album.tracks:
        tracks = discogs_album.tracks
        tracklist_source = "discogs"
    elif mb is not None and mb.tracks:
        tracks = mb.tracks
        tracklist_source = "musicbrainz"
    else:
        tracks, tracklist_source = [], None

    metadata: dict = {}
    if mb is not None:
        metadata["musicbrainz_release_id"] = mb.release_id
    if genres:
        metadata["genres"] = genres
    if discogs_album is not None and discogs_album.styles:
        metadata["discogs_styles"] = list(discogs_album.styles)
    if discogs_album is not None and discogs_album.formats:
        metadata["discogs_formats"] = list(discogs_album.formats)

    # Artwork preference: Deezer → iTunes → Discogs → CAA (via resolve_cover).
    provider_cover = None
    artwork_source: str | None
    if deezer_cover:
        artwork_source = "deezer"
    elif itunes_album is not None and itunes_album.cover_url:
        provider_cover = itunes_album.cover_url
        artwork_source = "itunes"
    elif discogs_album is not None and discogs_album.cover_url:
        provider_cover = discogs_album.cover_url
        artwork_source = "discogs"
    else:
        artwork_source = None

    cover_url = coverart.resolve_cover(
        deezer_cover=deezer_cover,
        provider_cover=provider_cover,
        release_group_id=rg_id,
        release_id=mb.release_id if mb is not None else None,
    )
    if artwork_source is None and cover_url is not None:
        artwork_source = "cover_art_archive"

    # Every contributing source's full tracklist (non-empty only); the
    # preferred one is always included so the preview can compare pressings.
    tracklists_by_source: dict[str, list[TrackInput]] = {}
    for album_name, album in source_albums:
        if album is not None and album.tracks:
            tracklists_by_source[album_name] = album.tracks

    return ImportedAlbum(
        source=source,
        external_id=external_id,
        title=title,
        artist=artist,
        year=first_known(
            mb.year if mb is not None else None,
            year_hint,
            deezer_album.year if deezer_album is not None else None,
            itunes_album.year if itunes_album is not None else None,
            discogs_album.year if discogs_album is not None else None,
        ),
        label=label,
        country=country,
        musicbrainz_release_group_id=rg_id,
        deezer_id=deezer_id,
        itunes_id=itunes_id,
        discogs_id=discogs_id,
        cover_url=cover_url,
        metadata=metadata,
        tracks=tracks,
        metadata_source=meta_source,
        tracklist_source=tracklist_source,
        artwork_source=artwork_source,
        tracklists_by_source=tracklists_by_source,
    )
