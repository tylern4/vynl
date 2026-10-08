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
    import_album,
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
    """Reset the HTTP seam; make the MB 1 req/s guard instant between tests."""
    monkeypatch.setattr(musicbrainz, "_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(musicbrainz, "_next_slot", 0.0)
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
    return {
        MB_SEARCH: load_fixture("mb_release_group_search.json"),
        DEEZER_SEARCH: load_fixture("deezer_search.json"),
    }


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
                DEEZER_SEARCH: connect_error})
    outcome = search_albums_detailed("remain in light")
    assert outcome.degraded == ["deezer"]
    assert [row.title for row in outcome.results] == [
        "Remain in Light",
        "Naked",
        "My Life in the Bush of Ghosts",
    ]
    assert all(row.source == "musicbrainz" for row in outcome.results)


def test_search_raises_only_when_all_providers_fail():
    use_routes({MB_SEARCH: connect_error, DEEZER_SEARCH: connect_error})
    with pytest.raises(ProviderError) as excinfo:
        search_albums("anything")
    reason = excinfo.value.reason
    assert "all music providers failed" in reason
    assert "musicbrainz" in reason and "deezer" in reason


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
    rows = merge_results([deezer_row], [mb_row], limit=10)
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
    assert len(merge_results([deezer_row], [near], limit=10)) == 1
    assert len(merge_results([deezer_row], [no_year], limit=10)) == 1
    rows = merge_results([deezer_row], [far], limit=10)
    assert len(rows) == 2
    assert {row.source for row in rows} == {"deezer", "musicbrainz"}


def test_merge_dedupes_identical_albums_first_wins():
    first = _row("deezer", "1", "Album", "Artist", year=1980, deezer_id=1)
    duplicate = _row("deezer", "2", "ALBUM", "artist", year=1980, deezer_id=2)
    mb_row = _row("musicbrainz", "m", "Album", "Artist", year=1980)
    rows = merge_results([first, duplicate], [mb_row], limit=10)
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
