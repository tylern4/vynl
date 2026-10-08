"""Cover Art Archive artwork URL resolution (PLAN §6).

Resolution order: provider artwork (Deezer ``cover_xl``, then iTunes/Discogs
``provider_cover``) → CAA release-group ``front-500`` → CAA release ``front`` →
``None``. Only the URL is returned — images are never downloaded here (caching
is issue #3's job). Existence is probed with HEAD (no body), following the 302
to archive.org; a 404 simply means "no art".
"""

from __future__ import annotations

from . import _client


def release_group_front_url(mbid: str) -> str:
    return f"{_client.COVERART_BASE}/release-group/{mbid}/front-500"


def release_front_url(mbid: str) -> str:
    return f"{_client.COVERART_BASE}/release/{mbid}/front"


def resolve_cover(
    *,
    deezer_cover: str | None = None,
    provider_cover: str | None = None,
    release_group_id: str | None = None,
    release_id: str | None = None,
) -> str | None:
    """Best available remote artwork URL, or ``None`` when there is none.

    Never raises: artwork is best-effort, and CAA 404 / outages degrade to
    ``None`` rather than failing an import. ``provider_cover`` lets issue #12
    sources (iTunes/Discogs) slot in as second choice after Deezer.
    """
    if deezer_cover:
        return deezer_cover
    if provider_cover:
        return provider_cover
    if release_group_id:
        url = release_group_front_url(release_group_id)
        if _client.url_exists(url):
            return url
    if release_id:
        url = release_front_url(release_id)
        if _client.url_exists(url):
            return url
    return None
