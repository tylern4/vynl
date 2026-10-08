"""Music metadata providers: MusicBrainz, Deezer, Cover Art Archive (PLAN §6).

Public interface — routers import from here, never from submodules directly.
Issue #2 implements the functions below; consumers may already rely on the
signatures and mock them in tests.
"""

from .base import ImportedAlbum, NotFound, ProviderError, SearchResult, TrackInput

__all__ = [
    "ImportedAlbum",
    "NotFound",
    "ProviderError",
    "SearchResult",
    "TrackInput",
    "search_albums",
    "import_album",
]


def search_albums(query: str, limit: int = 20) -> list[SearchResult]:
    """Search Deezer and MusicBrainz, merge and dedupe (PLAN §6).

    Raises ProviderError only if every provider fails; a single failing
    provider degrades to the other's results.
    """
    raise ProviderError("music providers are not implemented yet (issue #2)")


def import_album(source: str, external_id: str) -> ImportedAlbum:
    """Fetch full metadata + tracklist for one album from its source.

    Raises NotFound for unknown ids, ProviderError for upstream failures.
    """
    raise ProviderError("music providers are not implemented yet (issue #2)")
