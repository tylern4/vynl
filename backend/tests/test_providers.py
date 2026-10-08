"""Provider-layer tests (issue #2): MusicBrainz, Deezer, Cover Art Archive,
merge/dedupe rules, and import assembly (PLAN §6).

Every test injects an ``httpx.MockTransport``-backed client through the
``providers`` ``set_client`` seam — **zero live network**. Unexpected request
URLs fail the test, so nothing can leak out.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from src.config import settings
from src.providers import (
    NotFound,
    ProviderError,
    SearchResult,
    _client,
    coverart,
    deezer,
    discogs,
    import_album,
    itunes,
    musicbrainz,
    search_albums,
    search_albums_detailed,
    set_client,
)
from src.providers._merge import merge_results, normalize, normalize_artist

# --------------------------------------------------------------- constants

FIXTURES = Path(__file__).parent / "fixtures"

MB_HOST = "musicbrainz.org"
DEEZER_HOST = "api.deezer.com"
CAA_HOST = "coverartarchive.org"
ARCHIVE_HOST = "archive.org"
ITUNES_HOST = "itunes.apple.com"
DISCOGS_HOST = "api.discogs.com"

RG_REMAIN = "f6b1b900-6108-32f0-abbd-2855af9151eb"
REL_REMAIN = "6a5ee7ec-b90b-47f5-aec2-bc8177c9b46a"  # Official — picked
RG_DISCOVERY = "b9d5f8c0-4e2a-4f6a-9a5e-1d2c3b4a5e6f"
REL_DISCOVERY = "c0ffee00-1111-4222-8333-444455556666"
UNKNOWN_RG = "11111111-2222-3333-4444-555555555555"

DEEZER_REMAIN_ID = 467270
DEEZER_DISCOVERY_ID = 302127
COVER_XL_REMAIN = (
    "https://cdn-images.dzcdn.net/images/cover/remain/1000x1000-000000-80-0-0.jpg"
)
COVER_XL_DISCOVERY = (
    "https://cdn-images.dzcdn.net/images/cover/discovery/1000x1000-000000-80-0-0.jpg"
)
CAA_RG_REMAIN = f"https://coverartarchive.org/release-group/{RG_REMAIN}/front-500"
CAA_REL_REMAIN = f"https://coverartarchive.org/release/{REL_REMAIN}/front"

MB_SEARCH = ("GET", MB_HOST, "/ws/2/release-group")
DEEZER_SEARCH = ("GET", DEEZER_HOST, "/search/album")
ITUNES_SEARCH = ("GET", ITUNES_HOST, "/search")
ITUNES_LOOKUP = ("GET", ITUNES_HOST, "/lookup")
DISCOGS_SEARCH = ("GET", DISCOGS_HOST, "/database/search")
DISCOGS_RELEASE = ("GET", DISCOGS_HOST, "/releases/{{release_id}}")


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def connect_error(request: httpx.Request) -> httpx.Response:
    """Route spec: simulate a provider outage."""
    raise httpx.ConnectError("simulated outage", request=request)


def make_client(routes: dict) -> httpx.Client:
    """MockTransport client dispatching on ``(method, host, path)``.

    Route specs: ``dict`` → 200 JSON; ``int`` → status with empty JSON body;
    ``(status, body[, headers])`` → status + JSON body; callable → whatever
    it returns (or raises).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.host, request.url.path)
        if key not in routes:
            pytest.fail(f"unexpected provider request: {request.method} {request.url}")
        spec = routes[key]
        if callable(spec):
            return spec(request)
        if isinstance(spec, dict):
            status, body, headers = 200, spec, {}
        elif isinstance(spec, int):
            status, body, headers = spec, {}, {}
        else:
            status, body = spec[0], spec[1]
            headers = spec[2] if len(spec) > 2 else {}
        return httpx.Response(status, json=body, headers=headers, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def use_routes(routes: dict) -> None:
    set_client(make_client(routes))


# ------------------------------------------------------------- pytest hooks


@pytest.fixture(autouse=True)
def _clean_tables():
    """Shadow tests/conftest.py's DB-truncating fixture: provider tests are
    HTTP-only and must not require Postgres."""
    yield


@pytest.fixture(autouse=True)
def _provider_env(monkeypatch):
    """Reset the HTTP seam; make every provider's throttle instant between
    tests (MB/Deezer/iTunes spacing guards and Discogs' backoff)."""
    monkeypatch.setattr(musicbrainz, "_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(musicbrainz, "_next_slot", 0.0)
    monkeypatch.setattr(itunes, "_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(itunes, "_next_slot", 0.0)
    monkeypatch.setattr(discogs, "_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(discogs, "_next_slot", 0.0)
    monkeypatch.setattr(discogs, "_BACKOFF_BASE", 0.0)
    set_client(None)
    yield
    set_client(None)


# ------------------------------------------------------------------- search


def test_musicbrainz_search_parses_release_groups():
    use_routes({MB_SEARCH: load_fixture("mb_release_group_search.json")})
    rows = musicbrainz.search("talking heads", limit=10)
    assert [row.external_id for row in rows] == [
        RG_REMAIN,
        "1d4a1b8e-2f3c-4a5b-8c9d-0e1f2a3b4c5d",
        "7e2c9a4b-5d6e-4f70-8192-a3b4c5d6e7f8",
    ]
    remain = rows[0]
    assert remain.source == "musicbrainz"
    assert remain.musicbrainz_release_group_id == RG_REMAIN
    assert remain.deezer_id is None
    assert (remain.title, remain.artist, remain.year) == (
        "Remain in Light",
        "Talking Heads",
        1980,
    )
    assert remain.track_count is None and remain.cover_url is None
    assert remain.label is None
    # artist-credit joinphrase flattening
    assert rows[2].artist == "Brian Eno & David Byrne"
    assert rows[2].title == "My Life in the Bush of Ghosts"
    assert rows[2].year == 1981


def test_deezer_search_parses_albums():
    use_routes({DEEZER_SEARCH: load_fixture("deezer_search.json")})
    rows = deezer.search("remain in light", limit=10)
    assert len(rows) == 3
    first = rows[0]
    assert first.source == "deezer"
    assert first.external_id == str(DEEZER_REMAIN_ID)
    assert first.deezer_id == DEEZER_REMAIN_ID
    assert first.musicbrainz_release_group_id is None
    assert first.track_count == 12
    assert first.cover_url == COVER_XL_REMAIN
    assert first.year is None  # /search/album carries no release_date
    assert first.label is None


def _both_provider_routes() -> dict:
    """Deezer + MusicBrainz playbook used by the merged-search tests, plus a
    quiet iTunes storefront (issue #12: iTunes is always on; no results keeps
    those tests' expectations unchanged). Discogs is disabled by default."""
    return {
        MB_SEARCH: load_fixture("mb_release_group_search.json"),
        DEEZER_SEARCH: load_fixture("deezer_search.json"),
        ITUNES_SEARCH: _itunes_empty(),
    }


def _itunes_empty() -> dict:
    """iTunes answers any storefront search with no results when the album is
    not in that country's catalog — never an error."""
    return {"resultCount": 0, "results": []}


def test_search_merges_both_providers_with_stable_order():
    use_routes(_both_provider_routes())
    outcome = search_albums_detailed("remain in light", limit=20)
    assert outcome.degraded == []
    assert [(row.source, row.title) for row in outcome.results] == [
        ("musicbrainz", "Remain in Light"),  # merged pair
        ("deezer", "Little Creatures"),  # deezer relevance first
        ("musicbrainz", "Naked"),
        ("musicbrainz", "My Life in the Bush of Ghosts"),
    ]
    merged = outcome.results[0]
    assert merged.external_id == RG_REMAIN
    assert merged.musicbrainz_release_group_id == RG_REMAIN
    assert merged.deezer_id == DEEZER_REMAIN_ID
    assert merged.artist == "Talking Heads"
    assert merged.year == 1980  # MusicBrainz wins
    assert merged.track_count == 12  # Deezer wins
    assert merged.cover_url == COVER_XL_REMAIN  # Deezer wins
    # the duplicate Deezer edition was deduped away
    assert sum(1 for row in outcome.results if row.title == "Remain in Light") == 1


def test_search_degrades_to_deezer_when_musicbrainz_down():
    use_routes(
        {
            MB_SEARCH: connect_error,
            DEEZER_SEARCH: load_fixture("deezer_search.json"),
            ITUNES_SEARCH: _itunes_empty(),
        }
    )
    outcome = search_albums_detailed("remain in light")
    assert outcome.degraded == ["musicbrainz"]
    assert [row.title for row in outcome.results] == [
        "Remain in Light",
        "Little Creatures",
    ]
    assert all(row.source == "deezer" for row in outcome.results)


def test_search_degrades_to_musicbrainz_when_deezer_down():
    use_routes({MB_SEARCH: load_fixture("mb_release_group_search.json"),
                DEEZER_SEARCH: connect_error,
                ITUNES_SEARCH: _itunes_empty()})
    outcome = search_albums_detailed("remain in light")
    assert outcome.degraded == ["deezer"]
    assert [row.title for row in outcome.results] == [
        "Remain in Light",
        "Naked",
        "My Life in the Bush of Ghosts",
    ]
    assert all(row.source == "musicbrainz" for row in outcome.results)


def test_search_raises_only_when_all_enabled_providers_fail():
    # Discogs is unconfigured (omitted); iTunes is always on, so all three
    # remaining providers must fail for the search to raise.
    use_routes(
        {
            MB_SEARCH: connect_error,
            DEEZER_SEARCH: connect_error,
            ITUNES_SEARCH: connect_error,
        }
    )
    with pytest.raises(ProviderError) as excinfo:
        search_albums("anything")
    reason = excinfo.value.reason
    assert "all music providers failed" in reason
    assert "musicbrainz" in reason and "deezer" in reason and "itunes" in reason


def test_search_blank_query_and_limit():
    use_routes({})  # any HTTP request here fails the test
    assert search_albums("   ") == []
    assert search_albums_detailed("").degraded == []
    use_routes(_both_provider_routes())
    assert len(search_albums("remain in light", limit=1)) == 1
    assert len(search_albums("remain in light", limit=100)) == 4


# ------------------------------------------------------- merge rules (unit)


def _row(source, external_id, title, artist, year=None, **kwargs) -> SearchResult:
    return SearchResult(
        source=source,
        external_id=external_id,
        title=title,
        artist=artist,
        year=year,
        **kwargs,
    )


def test_normalize_strips_feat_suffix_for_comparison_only():
    assert normalize("  Album   Name ") == "album name"
    assert normalize_artist("Artist feat. Somebody") == "artist"
    assert normalize_artist("Artist ft. Somebody") == "artist"
    assert normalize_artist("Artist featuring Somebody") == "artist"
    assert normalize_artist("  The   Band  ") == "the band"
    assert normalize_artist("Honest Face") == "honest face"  # no false strip


def test_merge_pairs_on_normalized_artist_title_and_feat_suffix():
    deezer_row = _row(
        "deezer",
        "1",
        "  Album  Name ",
        "Artist feat. Somebody",
        deezer_id=1,
        track_count=9,
        cover_url="https://img.example/cover.jpg",
    )
    mb_row = _row("musicbrainz", "<mbid>", "album name", "Artist", year=1999)
    rows = merge_results({"deezer": [deezer_row], "musicbrainz": [mb_row]}, limit=10)
    assert len(rows) == 1
    merged = rows[0]
    assert merged.source == "musicbrainz"
    assert merged.external_id == "<mbid>"
    assert merged.artist == "Artist"  # canonical display string, not feat…
    assert merged.year == 1999
    assert merged.track_count == 9 and merged.cover_url == "https://img.example/cover.jpg"
    assert merged.deezer_id == 1
    assert merged.musicbrainz_release_group_id == "<mbid>"


def test_merge_year_tolerance_is_plus_or_minus_one():
    deezer_row = _row("deezer", "1", "Album", "Artist", year=1980, deezer_id=1)
    near = _row("musicbrainz", "a", "Album", "Artist", year=1981)
    far = _row("musicbrainz", "b", "Album", "Artist", year=1983)
    no_year = _row("musicbrainz", "c", "Album", "Artist")
    assert len(merge_results({"deezer": [deezer_row], "musicbrainz": [near]}, limit=10)) == 1
    assert len(merge_results({"deezer": [deezer_row], "musicbrainz": [no_year]}, limit=10)) == 1
    rows = merge_results({"deezer": [deezer_row], "musicbrainz": [far]}, limit=10)
    assert len(rows) == 2
    assert {row.source for row in rows} == {"deezer", "musicbrainz"}


def test_merge_dedupes_identical_albums_first_wins():
    first = _row("deezer", "1", "Album", "Artist", year=1980, deezer_id=1)
    duplicate = _row("deezer", "2", "ALBUM", "artist", year=1980, deezer_id=2)
    mb_row = _row("musicbrainz", "m", "Album", "Artist", year=1980)
    rows = merge_results(
        {"deezer": [first, duplicate], "musicbrainz": [mb_row]}, limit=10
    )
    assert len(rows) == 1
    assert rows[0].deezer_id == 1


# ------------------------------------------------------------------- import


def test_import_musicbrainz_merges_deezer_twin():
    use_routes(
        {
            ("GET", MB_HOST, f"/ws/2/release-group/{RG_REMAIN}"): load_fixture(
                "mb_release_group_releases.json"
            ),
            ("GET", MB_HOST, f"/ws/2/release/{REL_REMAIN}"): load_fixture(
                "mb_release.json"
            ),
            DEEZER_SEARCH: load_fixture("deezer_search.json"),
            ("GET", DEEZER_HOST, f"/album/{DEEZER_REMAIN_ID}"): load_fixture(
                "deezer_album.json"
            ),
        }
    )
    album = import_album("musicbrainz", RG_REMAIN)
    assert album.source == "musicbrainz"
    assert album.external_id == RG_REMAIN
    assert album.musicbrainz_release_group_id == RG_REMAIN
    assert album.deezer_id == DEEZER_REMAIN_ID
    # canonical metadata from MusicBrainz…
    assert album.title == "Remain in Light"
    assert album.artist == "Talking Heads"
    assert album.year == 1980
    assert album.label == "Sire Records"  # MB label-info beats Deezer's "Sire"
    assert album.country == "US"
    # …tracklist + cover from Deezer (preferred when both ids are known)
    assert len(album.tracks) == 7
    assert album.tracks[0].title == "Born Under Punches (The Heat Goes On)"
    assert album.tracks[0].duration_seconds == 349
    assert album.tracks[-1].duration_seconds == 257  # MB length was null → Deezer used
    assert album.cover_url == COVER_XL_REMAIN  # cover_xl wins, CAA never consulted
    # Official release picked over the Promotion copy
    assert album.metadata["musicbrainz_release_id"] == REL_REMAIN
    assert album.metadata["genres"] == ["Rock"]
    # Source breakdown (issue #13): MB metadata, Deezer tracklist + artwork.
    assert album.metadata_source == "musicbrainz"
    assert album.tracklist_source == "deezer"
    assert album.artwork_source == "deezer"
    assert set(album.tracklists_by_source) == {"musicbrainz", "deezer"}
    assert len(album.tracklists_by_source["deezer"]) == 7
    assert (
        album.tracklists_by_source["deezer"][0].title
        == "Born Under Punches (The Heat Goes On)"
    )
    assert album.tracks is album.tracklists_by_source["deezer"]  # preferred one


def test_import_falls_back_to_musicbrainz_when_deezer_404s():
    use_routes(
        {
            ("GET", MB_HOST, f"/ws/2/release-group/{RG_REMAIN}"): load_fixture(
                "mb_release_group_releases.json"
            ),
            ("GET", MB_HOST, f"/ws/2/release/{REL_REMAIN}"): load_fixture(
                "mb_release.json"
            ),
            DEEZER_SEARCH: load_fixture("deezer_search.json"),
            ("GET", DEEZER_HOST, f"/album/{DEEZER_REMAIN_ID}"): load_fixture(
                "deezer_album_missing.json"
            ),
            ("HEAD", CAA_HOST, f"/release-group/{RG_REMAIN}/front-500"): 404,
            ("HEAD", CAA_HOST, f"/release/{REL_REMAIN}/front"): 404,
        }
    )
    album = import_album("musicbrainz", RG_REMAIN)
    assert album.deezer_id is None
    # MusicBrainz tracklist: length ms → seconds, positions across both media
    assert [track.position for track in album.tracks] == [1, 2, 3, 4, 5, 6, 7]
    assert [track.duration_seconds for track in album.tracks] == [
        349,
        388,
        263,
        271,
        203,
        271,
        None,  # null length, and the untitled B4 track was skipped
    ]
    assert album.tracks[-1].title == "The Overload"
    # CAA has no art → cover_url is None, not an error
    assert album.cover_url is None
    assert album.label == "Sire Records"
    assert "genres" not in album.metadata
    # MB-only breakdown: everything from MusicBrainz, no artwork.
    assert album.metadata_source == "musicbrainz"
    assert album.tracklist_source == "musicbrainz"
    assert album.artwork_source is None
    assert list(album.tracklists_by_source) == ["musicbrainz"]
    assert album.tracklists_by_source["musicbrainz"] == album.tracks


def test_import_cover_falls_back_to_release_front():
    use_routes(
        {
            ("GET", MB_HOST, f"/ws/2/release-group/{RG_REMAIN}"): load_fixture(
                "mb_release_group_releases.json"
            ),
            ("GET", MB_HOST, f"/ws/2/release/{REL_REMAIN}"): load_fixture(
                "mb_release.json"
            ),
            DEEZER_SEARCH: {"data": [], "total": 0},  # no Deezer twin
            ("HEAD", CAA_HOST, f"/release-group/{RG_REMAIN}/front-500"): 404,
            ("HEAD", CAA_HOST, f"/release/{REL_REMAIN}/front"): 200,
        }
    )
    album = import_album("musicbrainz", RG_REMAIN)
    assert album.cover_url == CAA_REL_REMAIN
    assert album.deezer_id is None
    assert album.tracks[0].duration_seconds == 349
    # Cover Art Archive resolved the artwork (no Deezer cover available).
    assert album.artwork_source == "cover_art_archive"


def test_import_cover_follows_redirect_but_keeps_caa_url():
    archive_path = f"/download/mbid-{REL_REMAIN}/mbid-{REL_REMAIN}.jpg"

    def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302, headers={"location": f"https://{ARCHIVE_HOST}{archive_path}"}, request=request
        )

    use_routes(
        {
            ("GET", MB_HOST, f"/ws/2/release-group/{RG_REMAIN}"): load_fixture(
                "mb_release_group_releases.json"
            ),
            ("GET", MB_HOST, f"/ws/2/release/{REL_REMAIN}"): load_fixture(
                "mb_release.json"
            ),
            DEEZER_SEARCH: {"data": [], "total": 0},
            ("HEAD", CAA_HOST, f"/release-group/{RG_REMAIN}/front-500"): redirect,
            ("HEAD", ARCHIVE_HOST, archive_path): 200,
        }
    )
    album = import_album("musicbrainz", RG_REMAIN)
    assert album.cover_url == CAA_RG_REMAIN  # stable CAA URL, not archive.org


def test_import_musicbrainz_not_found_for_unknown_id():
    use_routes(
        {
            ("GET", MB_HOST, f"/ws/2/release-group/{UNKNOWN_RG}"): 404,
            ("GET", MB_HOST, f"/ws/2/release/{UNKNOWN_RG}"): 404,
        }
    )
    with pytest.raises(NotFound):
        import_album("musicbrainz", UNKNOWN_RG)


def test_import_musicbrainz_not_found_for_malformed_id():
    use_routes({})  # validation must happen before any HTTP
    with pytest.raises(NotFound):
        import_album("musicbrainz", "not-a-mbid")


def test_import_deezer_source_with_musicbrainz_twin():
    def mb_search(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("query", "")
        assert query == 'artist:"Daft Punk" AND releasegroup:"Discovery"'
        return httpx.Response(
            200, json=load_fixture("mb_release_group_search_discovery.json"), request=request
        )

    use_routes(
        {
            ("GET", DEEZER_HOST, f"/album/{DEEZER_DISCOVERY_ID}"): load_fixture(
                "deezer_album_discovery.json"
            ),
            MB_SEARCH: mb_search,
            ("GET", MB_HOST, f"/ws/2/release-group/{RG_DISCOVERY}"): load_fixture(
                "mb_release_group_releases_discovery.json"
            ),
            ("GET", MB_HOST, f"/ws/2/release/{REL_DISCOVERY}"): load_fixture(
                "mb_release_discovery.json"
            ),
        }
    )
    album = import_album("deezer", str(DEEZER_DISCOVERY_ID))
    assert album.source == "deezer"
    assert album.external_id == str(DEEZER_DISCOVERY_ID)
    assert album.deezer_id == DEEZER_DISCOVERY_ID
    assert album.musicbrainz_release_group_id == RG_DISCOVERY
    assert (album.title, album.artist, album.year) == ("Discovery", "Daft Punk", 2001)
    assert album.label == "Virgin Records"  # MB canonical beats Deezer's label
    assert album.country == "FR"
    assert album.cover_url == COVER_XL_DISCOVERY
    # Deezer tracklist preferred over the MusicBrainz medium
    assert [track.title for track in album.tracks] == [
        "One More Time",
        "Aerodynamic",
        "Digital Love",
        "Harder, Better, Faster, Stronger",
    ]
    assert [track.duration_seconds for track in album.tracks] == [320, 207, 301, 224]
    assert album.metadata == {
        "musicbrainz_release_id": REL_DISCOVERY,
        "genres": ["Electronic"],
    }


def test_import_deezer_source_degrades_when_musicbrainz_down():
    use_routes(
        {
            ("GET", DEEZER_HOST, f"/album/{DEEZER_DISCOVERY_ID}"): load_fixture(
                "deezer_album_discovery.json"
            ),
            MB_SEARCH: connect_error,
        }
    )
    album = import_album("deezer", str(DEEZER_DISCOVERY_ID))
    assert album.musicbrainz_release_group_id is None
    assert album.label == "Daft Life Ltd./ADA France"  # Deezer's own label
    assert album.country is None
    assert album.year == 2001
    assert album.cover_url == COVER_XL_DISCOVERY
    assert len(album.tracks) == 4
    assert "musicbrainz_release_id" not in album.metadata
    assert album.metadata["genres"] == ["Electronic"]
    # Deezer-only breakdown: metadata + tracklist + artwork all from Deezer.
    assert album.metadata_source == "deezer"
    assert album.tracklist_source == "deezer"
    assert album.artwork_source == "deezer"
    assert list(album.tracklists_by_source) == ["deezer"]
    assert album.tracklists_by_source["deezer"] == album.tracks


def test_import_deezer_not_found():
    use_routes(
        {("GET", DEEZER_HOST, f"/album/{DEEZER_DISCOVERY_ID}"): load_fixture(
            "deezer_album_missing.json"
        )}
    )
    # Deezer answers missing albums with HTTP 200 + {"error": {"code": 800}}
    with pytest.raises(NotFound):
        import_album("deezer", str(DEEZER_DISCOVERY_ID))
    with pytest.raises(NotFound):
        import_album("deezer", "not-numeric")


def test_import_rejects_unknown_source():
    use_routes({})  # no HTTP for a bad source
    with pytest.raises(ProviderError) as excinfo:
        import_album("spotify", "123")
    assert "unknown music source" in excinfo.value.reason


# -------------------------------------------------------------- cover art


def test_cover_resolution_prefers_deezer_cover():
    use_routes({})  # a probe against any URL fails the test
    assert (
        coverart.resolve_cover(
            deezer_cover="https://img.example/cover.jpg",
            release_group_id=RG_REMAIN,
            release_id=REL_REMAIN,
        )
        == "https://img.example/cover.jpg"
    )


def test_cover_art_archive_404_returns_none_not_error():
    use_routes(
        {
            ("HEAD", CAA_HOST, f"/release-group/{RG_REMAIN}/front-500"): 404,
            ("HEAD", CAA_HOST, f"/release/{REL_REMAIN}/front"): 404,
        }
    )
    assert coverart.resolve_cover(release_group_id=RG_REMAIN, release_id=REL_REMAIN) is None


# ------------------------------------------------------------- http helpers


def test_get_json_maps_http_failures_onto_provider_errors():
    def garbage(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>not json</html>", request=request)

    use_routes(
        {
            ("GET", DEEZER_HOST, "/boom"): 500,
            ("GET", DEEZER_HOST, "/missing"): 404,
            ("GET", DEEZER_HOST, "/garbage"): garbage,
        }
    )
    with pytest.raises(ProviderError) as excinfo:
        _client.get_json("https://api.deezer.com/boom")
    assert "HTTP 500" in excinfo.value.reason
    with pytest.raises(NotFound):
        _client.get_json("https://api.deezer.com/missing")
    with pytest.raises(ProviderError) as excinfo:
        _client.get_json("https://api.deezer.com/garbage")
    assert "invalid JSON" in excinfo.value.reason


def test_url_exists_falls_back_to_get_when_head_rejected():
    use_routes(
        {
            ("HEAD", CAA_HOST, "/probe"): 405,
            ("GET", CAA_HOST, "/probe"): (200, {}, {"content-type": "image/jpeg"}),
        }
    )
    assert _client.url_exists("https://coverartarchive.org/probe") is True


def test_musicbrainz_rate_limiter_spaces_requests(monkeypatch):
    monkeypatch.setattr(musicbrainz, "_MIN_INTERVAL", 0.05)
    monkeypatch.setattr(musicbrainz, "_next_slot", 0.0)
    start = time.monotonic()
    for _ in range(3):
        musicbrainz._throttle()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.09  # two enforced 50ms gaps


def test_musicbrainz_sends_configured_user_agent(monkeypatch):
    monkeypatch.setattr(settings, "musicbrainz_contact", "vynl-tests@example.com")
    seen: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        seen["user_agent"] = request.headers.get("user-agent")
        return httpx.Response(200, json={"release-groups": []}, request=request)

    use_routes({MB_SEARCH: capture})
    musicbrainz.search("any query")
    assert seen["user_agent"] == "vynl/0.1.0 (vynl-tests@example.com)"


# ------------------------------------------------------------- iTunes (#12)


def _itunes_search_countries(routes: dict) -> list[str]:
    """Route callable helper: records requested countries; returns iTunes
    search rows only for the storefronts given in ``routes``."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        country = request.url.params.get("country")
        seen.append(country)
        if country in routes:
            return routes[country](request)
        return httpx.Response(200, json=_itunes_empty(), request=request)

    use_routes({ITUNES_SEARCH: handler})
    return seen


def test_itunes_search_queries_every_storefront_and_maps_results(monkeypatch):
    monkeypatch.setattr(settings, "itunes_countries", "US,JP,GB")
    seen = _itunes_search_countries(
        {
            "US": lambda r: httpx.Response(
                200, json=load_fixture("itunes_search.json"), request=r
            )
        }
    )
    rows = itunes.search("remain in light", limit=10)
    assert seen == ["US", "JP", "GB"]  # every configured storefront in order
    assert len(rows) == 1
    remain = rows[0]
    assert remain.source == "itunes"
    assert remain.external_id == "1440814958"
    assert remain.itunes_id == "1440814958"
    assert (remain.title, remain.artist, remain.year) == (
        "Remain in Light",
        "Talking Heads",
        1980,
    )
    assert remain.track_count == 8
    # artworkUrl100 upgraded to the 600x600 size token
    assert remain.cover_url.endswith("600x600bb.jpg")


def test_itunes_artwork_upgrade():
    assert itunes.upgrade_art("https://a/b/100x100bb.jpg") == "https://a/b/600x600bb.jpg"
    assert itunes.upgrade_art("https://a/b/600x600bb.jpg") == "https://a/b/600x600bb.jpg"
    assert itunes.upgrade_art(None) is None
    assert itunes.upgrade_art("https://a/b/photo.jpg") == "https://a/b/photo.jpg"


def test_itunes_search_degrades_one_storefront_down(monkeypatch):
    monkeypatch.setattr(settings, "itunes_countries", "US,JP,GB")

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated outage", request=request)

    seen = _itunes_search_countries(
        {"US": fail, "JP": lambda r: httpx.Response(
            200, json=load_fixture("itunes_search.json"), request=r
        )}
    )
    rows = itunes.search("remain in light")
    assert seen == ["US", "JP", "GB"]
    assert len(rows) == 1  # US failed, JP had it, GB empty — not an error
    assert rows[0].itunes_id == "1440814958"


def test_itunes_search_raises_when_every_storefront_fails():
    use_routes({ITUNES_SEARCH: connect_error})
    with pytest.raises(ProviderError) as excinfo:
        itunes.search("anything")
    assert "all iTunes storefronts failed" in excinfo.value.reason
    assert "US" in excinfo.value.reason and "JP" in excinfo.value.reason


def test_itunes_requires_configured_storefronts(monkeypatch):
    monkeypatch.setattr(settings, "itunes_countries", "")
    use_routes({})  # validation must precede any HTTP
    with pytest.raises(ProviderError) as excinfo:
        itunes.search("anything")
    assert "no iTunes storefronts configured" in excinfo.value.reason


def test_itunes_fetch_album_sort_and_durations(monkeypatch):
    monkeypatch.setattr(settings, "itunes_countries", "US,JP,GB")

    def lookup(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("country") != "US":
            return httpx.Response(200, json=_itunes_empty(), request=request)
        return httpx.Response(
            200, json=load_fixture("itunes_lookup.json"), request=request
        )

    use_routes({ITUNES_LOOKUP: lookup})
    album = itunes.fetch_album("1440814958")
    assert album.itunes_id == "1440814958"
    assert (album.title, album.artist, album.year) == (
        "Remain in Light",
        "Talking Heads",
        1980,
    )
    assert album.country == "USA"  # fixture payload country, uppercased as-is
    assert album.label is None  # iTunes exposes no clean label field
    assert album.genres == ["Rock"]
    assert album.cover_url.endswith("600x600bb.jpg")
    # tracks sorted by (discNumber, trackNumber) despite the mixed payload
    assert [track.title for track in album.tracks] == [
        "Born Under Punches",
        "Crosseyed and Painless",
        "The Great Curve",
        "Once in a Lifetime",
        "Seen and Not Seen",
        "Houses in Motion",
        "Listening Wind",
        "The Overload",
        "Drugs",
    ]
    # trackTimeMillis → seconds
    assert [track.duration_seconds for track in album.tracks] == [
        349, 285, 263, 259, 203, 269, 243, 257, 271,
    ]


def test_itunes_fetch_album_found_on_later_storefront(monkeypatch):
    monkeypatch.setattr(settings, "itunes_countries", "US,JP,GB")

    def lookup(request: httpx.Request) -> httpx.Response:
        country = request.url.params.get("country")
        if country == "US":
            raise httpx.ConnectError("outage", request=request)
        if country != "JP":
            return httpx.Response(200, json=_itunes_empty(), request=request)
        return httpx.Response(
            200, json=load_fixture("itunes_lookup.json"), request=request
        )

    use_routes({ITUNES_LOOKUP: lookup})
    album = itunes.fetch_album("1440814958")
    # storefront iteration skipped the US outage and found it in Japan —
    # but the copy's country is what the payload says, not the storefront.
    assert album.title == "Remain in Light"
    assert album.country == "USA"


def test_itunes_fetch_album_not_found_when_no_storefront_has_it():
    use_routes({ITUNES_LOOKUP: {"resultCount": 0, "results": []}})
    with pytest.raises(NotFound):
        itunes.fetch_album("1440814958")
    with pytest.raises(NotFound):
        itunes.fetch_album("not-numeric")  # id validated before any HTTP


def test_itunes_rate_limiter_spaces_storefront_requests(monkeypatch):
    monkeypatch.setattr(itunes, "_MIN_INTERVAL", 0.05)
    monkeypatch.setattr(itunes, "_next_slot", 0.0)
    start = time.monotonic()
    for _ in range(3):
        itunes._throttle()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.09  # two enforced 50ms gaps


# ------------------------------------------------------------- Discogs (#12)


def _enable_discogs(monkeypatch, token="test-token") -> None:
    monkeypatch.setattr(settings, "discogs_token", token)


def test_discogs_disabled_direct_calls_raise(monkeypatch):
    _enable_discogs(monkeypatch, "")
    assert discogs.is_enabled() is False
    use_routes({})  # disabled fast-fails before any HTTP
    with pytest.raises(ProviderError) as excinfo:
        discogs.search("anything")
    assert excinfo.value.reason == "Discogs is not configured"
    with pytest.raises(ProviderError) as excinfo:
        discogs.fetch_album("249504")
    assert excinfo.value.reason == "Discogs is not configured"


def test_discogs_search_parses_artist_title_and_label(monkeypatch):
    _enable_discogs(monkeypatch)
    seen: dict = {}

    def search(request: httpx.Request) -> httpx.Response:
        seen["per_page"] = request.url.params.get("per_page")
        seen["token"] = request.url.params.get("token")
        assert request.url.params.get("type") == "release"
        return httpx.Response(
            200, json=load_fixture("discogs_search.json"), request=request
        )

    use_routes({DISCOGS_SEARCH: search})
    rows = discogs.search("talking heads", limit=10)
    assert seen["per_page"] == "10"  # per_page=limit
    assert seen["token"] == "test-token"
    assert len(rows) == 2
    remain = rows[0]
    assert remain.source == "discogs"
    assert remain.external_id == "249504"
    assert remain.discogs_id == "249504"
    # "Artist – Title" parsed into artist + title
    assert (remain.artist, remain.title, remain.year) == (
        "Talking Heads",
        "Remain in Light",
        1980,
    )
    assert remain.label == "Sire"  # first label entry
    assert remain.cover_url == "https://img.discogs.com/XYZ/remain.jpg"
    assert rows[1].cover_url is None  # spacer.gif placeholder counts as none


def test_discogs_split_title():
    assert discogs.split_title("Talking Heads – Remain in Light") == (
        "Talking Heads",
        "Remain in Light",
    )
    assert discogs.split_title("Talking Heads - Remain in Light") == (
        "Talking Heads",
        "Remain in Light",
    )
    assert discogs.split_title("  Spaced  –  Title  ") == ("Spaced", "Title")
    assert discogs.split_title("No Separator Here") == (None, "No Separator Here")


def test_discogs_duration_to_seconds():
    assert discogs._duration_to_seconds("5:49") == 349
    assert discogs._duration_to_seconds("1:04:05") == 3845
    assert discogs._duration_to_seconds(None) is None  # null-safe
    assert discogs._duration_to_seconds("") is None
    assert discogs._duration_to_seconds("nope") is None
    assert discogs._duration_to_seconds("4:60") == 300  # no validation, no crash
    assert discogs._duration_to_seconds(349) is None  # non-string ignored


def test_discogs_fetch_album_maps_release_metadata(monkeypatch):
    _enable_discogs(monkeypatch)
    use_routes({("GET", DISCOGS_HOST, "/releases/249504"): load_fixture(
        "discogs_release.json"
    )})
    album = discogs.fetch_album("249504")
    assert album.discogs_id == "249504"
    assert album.title == "Remain in Light"
    assert album.artist == "Talking Heads"  # artist credits joined
    assert album.year == 1980
    assert album.country == "EUROPE"
    assert album.label == "Sire"
    assert album.genres == ["Rock"]
    assert album.styles == ["New Wave", "Art Rock"]
    assert album.formats == ["Vinyl LP Album"]
    # first >=300px image wins (the 150px secondary is passed over)
    assert album.cover_url == "https://img.discogs.com/XYZ/remain-full.jpg"
    assert [track.title for track in album.tracks] == [
        "Born Under Punches (The Heat Goes On)",
        "Crosseyed and Painless",
        "Once in a Lifetime",
        "Houses in Motion",
        "Seen and Not Seen",
        "The Great Curve",
        "Listening Wind",
        "The Overload",
        "Drugs",
    ]
    # "MM:SS"/"H:MM:SS" → seconds; null durations stay null
    assert [track.duration_seconds for track in album.tracks] == [
        349, 285, 259, 270, 205, 336, 282, 360, None,
    ]


def test_discogs_429_backs_off_then_succeeds(monkeypatch):
    _enable_discogs(monkeypatch)
    calls = {"n": 0}

    def search(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={}, request=request)
        return httpx.Response(200, json={"results": []}, request=request)

    use_routes({DISCOGS_SEARCH: search})
    rows = discogs.search("anything")
    assert calls["n"] == 3  # two 429s retried with backoff, third succeeded
    assert rows == []


def test_discogs_backs_off_on_ratelimit_remaining_zero(monkeypatch):
    _enable_discogs(monkeypatch)
    calls = {"n": 0}

    def search(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json={"results": []},
                headers={"X-Discogs-Ratelimit-Remaining": "0"},
                request=request,
            )
        return httpx.Response(200, json={"results": []}, request=request)

    use_routes({DISCOGS_SEARCH: search})
    assert discogs.search("anything") == []
    assert calls["n"] == 2


def test_discogs_exhausted_rate_limit_raises(monkeypatch):
    _enable_discogs(monkeypatch)
    monkeypatch.setattr(discogs, "_RETRIES", 1)

    def search(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={}, request=request)

    use_routes({DISCOGS_SEARCH: search})
    with pytest.raises(ProviderError) as excinfo:
        discogs.search("anything")
    assert "HTTP 429" in excinfo.value.reason


def test_discogs_fetch_album_not_found(monkeypatch):
    _enable_discogs(monkeypatch)
    use_routes({("GET", DISCOGS_HOST, "/releases/999999"): 404})
    with pytest.raises(NotFound):
        discogs.fetch_album("999999")
    with pytest.raises(NotFound):
        discogs.fetch_album("not-numeric")


def test_discogs_sends_issue_user_agent(monkeypatch):
    _enable_discogs(monkeypatch)
    seen: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        seen["user_agent"] = request.headers.get("user-agent")
        seen["token"] = request.url.params.get("token")
        return httpx.Response(200, json={"results": []}, request=request)

    use_routes({DISCOGS_SEARCH: capture})
    discogs.search("any query")
    assert seen["user_agent"] == "vynl/0.1.0 (+https://github.com/tylern4/vynl)"
    assert seen["token"] == "test-token"


# --------------------------------------------------- merge across 4 sources


def test_search_merges_four_providers_and_collects_ids(monkeypatch):
    _enable_discogs(monkeypatch)
    use_routes(
        {
            MB_SEARCH: load_fixture("mb_release_group_search.json"),
            DEEZER_SEARCH: load_fixture("deezer_search.json"),
            ITUNES_SEARCH: load_fixture("itunes_search.json"),
            DISCOGS_SEARCH: load_fixture("discogs_search.json"),
        }
    )
    outcome = search_albums_detailed("talking heads", limit=20)
    assert outcome.degraded == []
    # Phase-1 order unchanged; iTunes/Discogs rows absorb onto the merged row
    # and anything unmatched (Discovery) appends at the end.
    assert [(row.source, row.title) for row in outcome.results] == [
        ("musicbrainz", "Remain in Light"),  # MB ⊕ Deezer ⊕ iTunes ⊕ Discogs
        ("deezer", "Little Creatures"),
        ("musicbrainz", "Naked"),
        ("musicbrainz", "My Life in the Bush of Ghosts"),
        ("discogs", "Discovery"),
    ]
    merged = outcome.results[0]
    assert merged.external_id == RG_REMAIN
    assert merged.musicbrainz_release_group_id == RG_REMAIN
    assert merged.deezer_id == DEEZER_REMAIN_ID
    assert merged.itunes_id == "1440814958"
    assert merged.discogs_id == "249504"
    assert merged.cover_url == COVER_XL_REMAIN  # Deezer art stays preferred
    assert merged.year == 1980  # MB year stays canonical
    assert outcome.results[-1].discogs_id == "249505"


def test_search_appends_unmatched_itunes_rows_after_musicbrainz():
    def itunes_search(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("country") != "US":
            return httpx.Response(200, json=_itunes_empty(), request=request)
        return httpx.Response(
            200,
            json={
                "resultCount": 1,
                "results": [
                    {
                        "wrapperType": "collection",
                        "collectionId": 123456789,
                        "artistName": "Yumi Matsutoya",
                        "collectionName": "Yuming Brand",
                        "releaseDate": "1982-01-01T00:00:00Z",
                        "trackCount": 10,
                        "artworkUrl100": "https://img.example/yuming/100x100bb.jpg",
                    }
                ],
            },
            request=request,
        )

    use_routes(
        {
            MB_SEARCH: load_fixture("mb_release_group_search.json"),
            DEEZER_SEARCH: load_fixture("deezer_search.json"),
            ITUNES_SEARCH: itunes_search,
        }
    )
    rows = search_albums("talking heads")
    assert [(row.source, row.title) for row in rows] == [
        ("musicbrainz", "Remain in Light"),
        ("deezer", "Little Creatures"),
        ("musicbrainz", "Naked"),
        ("musicbrainz", "My Life in the Bush of Ghosts"),
        ("itunes", "Yuming Brand"),
    ]
    assert rows[-1].itunes_id == "123456789"


def test_search_degrades_when_itunes_down(monkeypatch):
    _enable_discogs(monkeypatch)
    use_routes(
        {
            MB_SEARCH: load_fixture("mb_release_group_search.json"),
            DEEZER_SEARCH: load_fixture("deezer_search.json"),
            ITUNES_SEARCH: connect_error,
            DISCOGS_SEARCH: load_fixture("discogs_search.json"),
        }
    )
    outcome = search_albums_detailed("talking heads")
    assert outcome.degraded == ["itunes"]
    assert [row.title for row in outcome.results] == [
        "Remain in Light",
        "Little Creatures",
        "Naked",
        "My Life in the Bush of Ghosts",
        "Discovery",
    ]
    assert any(row.discogs_id == "249504" for row in outcome.results)


def test_search_omits_discogs_entirely_when_disabled():
    # Default env (blank token): Discogs must not even be queried.
    use_routes({MB_SEARCH: load_fixture("mb_release_group_search.json"),
                DEEZER_SEARCH: load_fixture("deezer_search.json"),
                ITUNES_SEARCH: _itunes_empty()})
    outcome = search_albums_detailed("talking heads")
    assert outcome.degraded == []
    assert all(row.source != "discogs" for row in outcome.results)


def test_merge_absorbs_itunes_then_discogs_into_mb_only_row():
    mb_row = _row("musicbrainz", "m", "Album", "Artist", year=1999)
    itunes_row = _row(
        "itunes", "i1", "Album", "Artist", year=1999,
        itunes_id="i1", cover_url="https://itunes-art", track_count=10,
    )
    discogs_row = _row("discogs", "d1", "Album", "Artist", year=1999, discogs_id="d1")
    rows = merge_results(
        {"musicbrainz": [mb_row], "itunes": [itunes_row], "discogs": [discogs_row]},
        limit=10,
    )
    assert len(rows) == 1
    merged = rows[0]
    assert merged.source == "musicbrainz"  # Deezer relevance / MB canonical
    assert merged.itunes_id == "i1"
    assert merged.discogs_id == "d1"
    assert merged.year == 1999
    assert merged.track_count == 10  # filled from the absorbed source
    assert merged.cover_url == "https://itunes-art"


# ---------------------------------------------------- iTunes/Discogs import


def test_import_itunes_prefers_deezer_tracklist_with_mb_metadata():
    def lookup(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("country") != "US":
            return httpx.Response(200, json=_itunes_empty(), request=request)
        return httpx.Response(
            200, json=load_fixture("itunes_lookup.json"), request=request
        )

    use_routes(
        {
            ITUNES_LOOKUP: lookup,
            MB_SEARCH: load_fixture("mb_release_group_search.json"),
            ("GET", MB_HOST, f"/ws/2/release-group/{RG_REMAIN}"): load_fixture(
                "mb_release_group_releases.json"
            ),
            ("GET", MB_HOST, f"/ws/2/release/{REL_REMAIN}"): load_fixture(
                "mb_release.json"
            ),
            DEEZER_SEARCH: load_fixture("deezer_search.json"),
            ("GET", DEEZER_HOST, f"/album/{DEEZER_REMAIN_ID}"): load_fixture(
                "deezer_album.json"
            ),
        }
    )
    album = import_album("itunes", "1440814958")
    assert album.source == "itunes"
    assert album.external_id == "1440814958"
    assert album.itunes_id == "1440814958"
    assert album.deezer_id == DEEZER_REMAIN_ID
    assert album.musicbrainz_release_group_id == RG_REMAIN
    # canonical metadata from the MusicBrainz twin…
    assert (album.title, album.artist, album.year) == (
        "Remain in Light",
        "Talking Heads",
        1980,
    )
    assert album.label == "Sire Records"
    assert album.country == "US"
    # …tracklist + artwork from Deezer (preferred over iTunes)
    assert album.tracklist_source == "deezer"
    assert album.artwork_source == "deezer"
    assert album.metadata_source == "musicbrainz"
    assert len(album.tracks) == 7
    assert album.tracks[0].title == "Born Under Punches (The Heat Goes On)"
    assert album.tracks[0].duration_seconds == 349
    assert album.cover_url == COVER_XL_REMAIN
    assert album.metadata["musicbrainz_release_id"] == REL_REMAIN
    assert album.metadata["genres"] == ["Rock"]
    assert set(album.tracklists_by_source) == {"musicbrainz", "deezer", "itunes"}


def test_import_itunes_degrades_when_twins_missing():
    def lookup(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("country") != "US":
            return httpx.Response(200, json=_itunes_empty(), request=request)
        return httpx.Response(
            200, json=load_fixture("itunes_lookup.json"), request=request
        )

    use_routes(
        {
            ITUNES_LOOKUP: lookup,
            MB_SEARCH: {"release-groups": []},
            DEEZER_SEARCH: {"data": [], "total": 0},
        }
    )
    album = import_album("itunes", "1440814958")
    assert album.itunes_id == "1440814958"
    assert album.deezer_id is None
    assert album.musicbrainz_release_group_id is None
    assert (album.title, album.artist, album.year) == (
        "Remain in Light",
        "Talking Heads",
        1980,
    )
    assert album.label is None
    assert album.country == "USA"  # iTunes-only metadata, payload says "USA"
    # iTunes-only: metadata + tracklist + artwork all from iTunes.
    assert album.metadata_source == "itunes"
    assert album.tracklist_source == "itunes"
    assert album.artwork_source == "itunes"
    assert len(album.tracks) == 9
    assert album.tracks[0].title == "Born Under Punches"
    assert album.cover_url.endswith("600x600bb.jpg")
    assert album.metadata == {"genres": ["Rock"]}


def test_import_itunes_not_found():
    use_routes({ITUNES_LOOKUP: {"resultCount": 0, "results": []}})
    with pytest.raises(NotFound):
        import_album("itunes", "1440814958")


def test_import_discogs_collects_formats_styles_with_mb_twin(monkeypatch):
    _enable_discogs(monkeypatch)
    use_routes(
        {
            ("GET", DISCOGS_HOST, "/releases/249504"): load_fixture(
                "discogs_release.json"
            ),
            MB_SEARCH: load_fixture("mb_release_group_search.json"),
            ("GET", MB_HOST, f"/ws/2/release-group/{RG_REMAIN}"): load_fixture(
                "mb_release_group_releases.json"
            ),
            ("GET", MB_HOST, f"/ws/2/release/{REL_REMAIN}"): load_fixture(
                "mb_release.json"
            ),
            DEEZER_SEARCH: {"data": [], "total": 0},  # no Deezer twin
        }
    )
    album = import_album("discogs", "249504")
    assert album.source == "discogs"
    assert album.external_id == "249504"
    assert album.discogs_id == "249504"
    assert album.musicbrainz_release_group_id == RG_REMAIN
    assert album.deezer_id is None
    # MB canonical metadata; Discogs feeds genres/styles/formats too.
    assert (album.title, album.artist, album.year) == (
        "Remain in Light",
        "Talking Heads",
        1980,
    )
    assert album.label == "Sire Records"
    assert album.metadata_source == "musicbrainz"
    assert album.metadata["musicbrainz_release_id"] == REL_REMAIN
    assert album.metadata["genres"] == ["Rock"]
    assert album.metadata["discogs_styles"] == ["New Wave", "Art Rock"]
    assert album.metadata["discogs_formats"] == ["Vinyl LP Album"]
    # Discogs tracklist + artwork (Deezer absent; iTunes not involved).
    assert album.tracklist_source == "discogs"
    assert album.artwork_source == "discogs"
    assert len(album.tracks) == 9
    assert album.tracks[0].duration_seconds == 349
    assert album.tracks[-1].duration_seconds is None  # null duration preserved
    assert album.cover_url == "https://img.discogs.com/XYZ/remain-full.jpg"
    assert set(album.tracklists_by_source) == {"musicbrainz", "discogs"}


def test_import_discogs_raises_when_disabled():
    use_routes({})  # no HTTP — disabled fast-fails before any request
    with pytest.raises(ProviderError) as excinfo:
        import_album("discogs", "249504")
    assert excinfo.value.reason == "Discogs is not configured"
    # The token gate runs before id validation too.
    with pytest.raises(ProviderError) as excinfo:
        import_album("discogs", "not-numeric")
    assert excinfo.value.reason == "Discogs is not configured"
