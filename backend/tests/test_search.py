"""GET /api/search/albums (external) and GET /api/tracks (library) — PLAN §5.

The providers seam ``src.providers.search_albums`` is mocked; no network.
"""

from uuid import uuid4

import pytest
from src.models import Album, Track
from src.providers import ProviderError, SearchOutcome, SearchResult


@pytest.fixture()
def search_results():
    """A couple of provider-shaped results (extras included on purpose: the
    response model must strip them down to the §5 wire shape)."""
    return [
        SearchResult(
            source="deezer",
            external_id="302127",
            title="Remain in Light",
            artist="Talking Heads",
            year=1980,
            track_count=8,
            cover_url="https://e-cdn.example/cover.jpg",
            label="Sire",
            deezer_id=302127,
            musicbrainz_release_group_id="abc-123",
        ),
        SearchResult(
            source="musicbrainz",
            external_id="mbid-0000-1111",
            title="Speaking in Tongues",
            artist="Talking Heads",
            year=1983,
        ),
    ]


@pytest.fixture()
def headers(admin, auth_headers):
    """Auth headers for the first registered (active admin) user."""
    return auth_headers("admin@example.com")


@pytest.fixture()
def mock_search(monkeypatch):
    """Replace src.providers.search_albums_detailed; exposes recorded calls."""

    class _Mock:
        def __init__(self):
            self.calls = []

        def install(self, results=None, error=None, degraded=None):
            def fake(query: str, limit: int = 20):
                self.calls.append((query, limit))
                if error is not None:
                    raise error
                return SearchOutcome(
                    results=results or [], degraded=list(degraded or [])
                )

            monkeypatch.setattr("src.providers.search_albums_detailed", fake)

    return _Mock()


def test_search_requires_auth(client, search_results, mock_search):
    mock_search.install(results=search_results)
    res = client.get("/api/search/albums", params={"q": "talking heads"})
    assert res.status_code == 401


def test_search_returns_normalized_wire_shape(client, headers, search_results, mock_search):
    mock_search.install(results=search_results)
    res = client.get(
        "/api/search/albums", params={"q": "talking heads"}, headers=headers
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body) == 2
    # Exactly the PLAN §5 SearchResult keys — provider-internal ids stripped.
    expected_keys = {
        "source", "external_id", "title", "artist",
        "year", "track_count", "cover_url", "label",
    }
    assert set(body[0].keys()) == expected_keys
    assert set(body[1].keys()) == expected_keys
    assert body[0] == {
        "source": "deezer",
        "external_id": "302127",
        "title": "Remain in Light",
        "artist": "Talking Heads",
        "year": 1980,
        "track_count": 8,
        "cover_url": "https://e-cdn.example/cover.jpg",
        "label": "Sire",
    }
    # Nullable fields default to null, not omitted.
    assert body[1]["year"] == 1983
    assert body[1]["cover_url"] is None
    assert body[1]["label"] is None
    assert body[1]["track_count"] is None


def test_search_passes_query_and_limit_through(client, headers, mock_search):
    mock_search.install(results=[])
    res = client.get(
        "/api/search/albums",
        params={"q": "talking heads", "limit": 5},
        headers=headers,
    )
    assert res.status_code == 200
    assert mock_search.calls == [("talking heads", 5)]


def test_search_default_limit_is_20(client, headers, mock_search):
    mock_search.install(results=[])
    res = client.get("/api/search/albums", params={"q": "bowie"}, headers=headers)
    assert res.status_code == 200
    assert mock_search.calls == [("bowie", 20)]


def test_search_requires_q(client, headers, mock_search):
    mock_search.install(results=[])
    assert client.get("/api/search/albums", headers=headers).status_code == 422
    assert (
        client.get(
            "/api/search/albums", params={"q": ""}, headers=headers
        ).status_code
        == 422
    )


def test_search_rejects_out_of_bounds_limit(client, headers, mock_search):
    mock_search.install(results=[])
    res = client.get(
        "/api/search/albums", params={"q": "x", "limit": 0}, headers=headers
    )
    assert res.status_code == 422


def test_search_provider_error_is_502(client, headers, mock_search):
    mock_search.install(error=ProviderError("all providers are down"))
    res = client.get("/api/search/albums", params={"q": "x"}, headers=headers)
    assert res.status_code == 502
    assert "all providers are down" in res.json()["detail"]


def test_search_sets_degraded_header_when_provider_fails(
    client, headers, search_results, mock_search
):
    # §5: body stays a plain array; the failing provider is named in headers.
    mock_search.install(results=search_results[:1], degraded=["deezer"])
    res = client.get("/api/search/albums", params={"q": "talking"}, headers=headers)
    assert res.status_code == 200
    assert res.headers.get("x-search-degraded") == "deezer"
    assert len(res.json()) == 1  # the healthy provider's results still served


def test_search_omits_degraded_header_when_healthy(
    client, headers, search_results, mock_search
):
    mock_search.install(results=search_results)
    res = client.get("/api/search/albums", params={"q": "talking"}, headers=headers)
    assert res.status_code == 200
    assert "x-search-degraded" not in res.headers


def test_search_empty_results_is_200(client, headers, mock_search):
    mock_search.install(results=[])
    res = client.get("/api/search/albums", params={"q": "zzzz"}, headers=headers)
    assert res.status_code == 200
    assert res.json() == []


# --- GET /api/tracks (library song search) ----------------------------------


@pytest.fixture()
def other_user(client, admin, register_user, auth_headers):
    """Second active user; ``user["headers"]`` are their auth headers."""
    res = register_user(name="Bob", email="bob@example.com")
    assert res.status_code == 201, res.text
    user = res.json()["user"]
    res = client.patch(
        f"/api/users/{user['id']}",
        json={"status": "active"},
        headers=auth_headers("admin@example.com"),
    )
    assert res.status_code == 200, res.text
    user["headers"] = auth_headers("bob@example.com")
    return user


def make_album(db, user_id, *, title="Album", artist="Artist", **fields):
    album = Album(
        user_id=user_id,
        title=title,
        artist=artist,
        source="deezer",
        external_id=fields.pop("external_id", f"ext-{uuid4().hex[:12]}"),
        **fields,
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


def add_tracks(db, album, *specs):
    for position, title, duration in specs:
        db.add(
            Track(
                album_id=album.id,
                position=position,
                title=title,
                duration_seconds=duration,
            )
        )
    db.commit()


def test_tracks_requires_auth(client):
    assert client.get("/api/tracks", params={"q": "love"}).status_code == 401


def test_tracks_requires_q(client, headers):
    assert client.get("/api/tracks", headers=headers).status_code == 422
    assert (
        client.get("/api/tracks", params={"q": ""}, headers=headers).status_code
        == 422
    )


def test_tracks_ilike_across_track_album_artist(client, headers, db_session, admin):
    a = make_album(
        db_session, admin["id"], title="Remain in Light", artist="Talking Heads"
    )
    add_tracks(db_session, a, (1, "Born Under Punches", 349), (2, "Crosseyed and Painless", 285))
    b = make_album(db_session, admin["id"], title="Blue", artist="Joni Mitchell")
    add_tracks(db_session, b, (1, "Carey", 180))

    # by track title
    res = client.get("/api/tracks", params={"q": "painless"}, headers=headers)
    assert res.status_code == 200
    assert [t["title"] for t in res.json()] == ["Crosseyed and Painless"]
    # by album title (case-insensitive)
    res = client.get("/api/tracks", params={"q": "REMAIN"}, headers=headers)
    assert sorted(t["title"] for t in res.json()) == [
        "Born Under Punches",
        "Crosseyed and Painless",
    ]
    # by artist (case-insensitive)
    res = client.get("/api/tracks", params={"q": "joni"}, headers=headers)
    assert [t["title"] for t in res.json()] == ["Carey"]
    # no match
    res = client.get("/api/tracks", params={"q": "zzzz"}, headers=headers)
    assert res.json() == []


def test_tracks_response_shape(client, headers, db_session, admin):
    album = make_album(
        db_session,
        admin["id"],
        title="Remain in Light",
        artist="Talking Heads",
        year=1980,
        cover_url="https://img.example/cover.jpg",
    )
    add_tracks(db_session, album, (1, "Born Under Punches", 349))
    res = client.get("/api/tracks", params={"q": "born"}, headers=headers)
    assert res.status_code == 200
    t = res.json()[0]
    assert set(t.keys()) == {"id", "title", "duration_seconds", "position", "album"}
    assert set(t["album"].keys()) == {"id", "title", "artist", "year", "cover_url"}
    assert t["album"]["id"] == album.id
    assert t["album"]["title"] == "Remain in Light"
    assert t["album"]["artist"] == "Talking Heads"
    assert t["album"]["year"] == 1980
    assert t["album"]["cover_url"] == "https://img.example/cover.jpg"
    assert t["title"] == "Born Under Punches"
    assert t["duration_seconds"] == 349
    assert t["position"] == 1


def test_tracks_ordered_artist_album_position(client, headers, db_session, admin):
    a1 = make_album(db_session, admin["id"], title="One", artist="Alpha Pop")
    add_tracks(db_session, a1, (2, "Second", 200), (1, "First", 100))
    a2 = make_album(db_session, admin["id"], title="Two", artist="Zulu Pop")
    add_tracks(db_session, a2, (1, "Zed", 50))

    res = client.get("/api/tracks", params={"q": "pop"}, headers=headers)
    assert [t["title"] for t in res.json()] == ["First", "Second", "Zed"]
    # grouping follows the artist order
    assert [t["album"]["artist"] for t in res.json()] == [
        "Alpha Pop",
        "Alpha Pop",
        "Zulu Pop",
    ]


def test_tracks_scoped_to_current_user(client, headers, other_user, db_session):
    theirs = make_album(
        db_session, other_user["id"], title="Bobs", artist="Bobby Blue"
    )
    add_tracks(db_session, theirs, (1, "Secret Song", 100))
    res = client.get("/api/tracks", params={"q": "secret"}, headers=headers)
    assert res.json() == []
    res = client.get(
        "/api/tracks", params={"q": "secret"}, headers=other_user["headers"]
    )
    assert [t["title"] for t in res.json()] == ["Secret Song"]


def test_tracks_limit_and_bounds(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"], title="Alpha", artist="Many Songs")
    add_tracks(
        db_session, album, *[(i, f"Song {i}", i * 10) for i in range(1, 8)]
    )
    # default limit 50 → all seven
    res = client.get("/api/tracks", params={"q": "songs"}, headers=headers)
    assert len(res.json()) == 7
    res = client.get("/api/tracks", params={"q": "songs", "limit": 3}, headers=headers)
    body = res.json()
    assert len(body) == 3
    assert [t["position"] for t in body] == [1, 2, 3]  # in-track order kept
    # bounds
    assert (
        client.get(
            "/api/tracks", params={"q": "songs", "limit": 0}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/tracks", params={"q": "songs", "limit": 999}, headers=headers
        ).status_code
        == 422
    )
