"""Import, album CRUD, cover serving (PLAN §5).

Providers are mocked at the ``src.providers.import_album`` seam and artwork at
``src.services.artwork.download_cover`` — no network in tests.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from src.config import settings
from src.models import Album, Play, Tag, Track
from src.providers import ImportedAlbum, NotFound, ProviderError, TrackInput
from src.services import artwork

JPEG_MAGIC = b"\xff\xd8\xff" + b"\x00rest-of-jpeg"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-payload"


# --- shared helpers / fixtures ----------------------------------------------


@pytest.fixture()
def headers(admin, auth_headers):
    """Auth headers for the first registered (active admin) user."""
    return auth_headers("admin@example.com")


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


@pytest.fixture()
def readonly_headers(client, admin, register_user, auth_headers):
    """A read_only (approved) account — may read, may not write."""
    res = register_user(name="Rox", email="rox@example.com")
    assert res.status_code == 201, res.text
    uid = res.json()["user"]["id"]
    res = client.patch(
        f"/api/users/{uid}",
        json={"role": "read_only", "status": "active"},
        headers=auth_headers("admin@example.com"),
    )
    assert res.status_code == 200, res.text
    return auth_headers("rox@example.com")


@pytest.fixture()
def cover_root(tmp_path, monkeypatch):
    """Isolate settings.covers_dir in a per-test temp directory."""
    root = tmp_path / "covers"
    root.mkdir()
    monkeypatch.setattr(settings, "covers_dir", str(root))
    return root


def make_album(
    db,
    user_id,
    *,
    title="Unknown Album",
    artist="Unknown Artist",
    source="deezer",
    external_id=None,
    **fields,
):
    album = Album(
        user_id=user_id,
        title=title,
        artist=artist,
        source=source,
        external_id=external_id or f"ext-{uuid4().hex[:12]}",
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


def attach_tags(db, album, *names, user_id):
    for name in names:
        tag = db.scalar(
            select(Tag).where(Tag.user_id == user_id, Tag.name == name)
        )
        if tag is None:
            tag = Tag(user_id=user_id, name=name)
            db.add(tag)
        if tag not in album.tags:
            album.tags.append(tag)
    db.commit()


def provider_album(**overrides):
    data = dict(
        source="deezer",
        external_id="302127",
        title="Remain in Light",
        artist="Talking Heads",
        year=1980,
        label="Sire",
        country="US",
        cover_url="https://example.com/cover.jpg",
        metadata={"genres": ["art rock"]},
        tracks=[
            TrackInput(1, "Born Under Punches", 349),
            TrackInput(2, "Crosseyed and Painless", 285),
        ],
    )
    data.update(overrides)
    return ImportedAlbum(**data)


@pytest.fixture()
def mock_import(monkeypatch):
    """Replace src.providers.import_album; exposes recorded calls."""

    class _Mock:
        def __init__(self):
            self.calls = []

        def install(self, result=None, error=None, factory=None):
            def fake(source, external_id):
                self.calls.append((source, external_id))
                if error is not None:
                    raise error
                if factory is not None:
                    return factory(source, external_id)
                return result or provider_album(
                    source=source, external_id=external_id
                )

            monkeypatch.setattr("src.providers.import_album", fake)

    return _Mock()


@pytest.fixture()
def mock_artwork(monkeypatch):
    """Replace src.services.artwork.download_cover; records calls."""

    class _Mock:
        def __init__(self):
            self.calls = []

        def install(self, result="auto", url_error=False):
            def fake(url, album_id, **kwargs):
                self.calls.append((url, album_id))
                if url_error:
                    raise OSError("disk full")
                if result == "fail":
                    return None
                if result == "auto":
                    return f"{album_id}.jpg"
                return result

            monkeypatch.setattr("src.services.artwork.download_cover", fake)

    return _Mock()


# --- search/import: general auth sweep --------------------------------------


ALL_ENDPOINTS = [
    ("GET", "/api/search/albums?q=x", None),
    ("POST", "/api/albums/import", {"source": "deezer", "external_id": "1"}),
    ("POST", "/api/albums/preview", {"source": "deezer", "external_id": "1"}),
    ("GET", "/api/albums", None),
    ("GET", "/api/albums/1", None),
    ("PATCH", "/api/albums/1", {"favorite": True}),
    ("DELETE", "/api/albums/1", None),
    ("GET", "/api/albums/1/cover", None),
    ("POST", "/api/albums/1/plays", {}),
    ("GET", "/api/albums/1/plays", None),
    ("DELETE", "/api/albums/1/plays/1", None),
    ("GET", "/api/tags", None),
    ("POST", "/api/tags", {"name": "x"}),
    ("PUT", "/api/albums/1/tags", {"tags": ["x"]}),
    ("DELETE", "/api/tags/1", None),
    ("GET", "/api/tracks?q=x", None),
    ("GET", "/api/recommendations", None),
]


def test_every_endpoint_requires_auth(client, admin):
    for method, path, body in ALL_ENDPOINTS:
        kwargs = {"json": body} if body is not None else {}
        res = client.request(method, path, **kwargs)
        assert res.status_code == 401, f"{method} {path} -> {res.status_code}"


# --- import ------------------------------------------------------------------


def test_import_happy_path(
    client, headers, db_session, admin, mock_import, mock_artwork
):
    mock_import.install()
    mock_artwork.install()
    res = client.post(
        "/api/albums/import",
        json={"source": "deezer", "external_id": "302127"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["title"] == "Remain in Light"
    assert body["artist"] == "Talking Heads"
    assert body["year"] == 1980
    assert body["label"] == "Sire"
    assert body["country"] == "US"
    assert body["source"] == "deezer"
    assert body["external_id"] == "302127"
    assert body["cover_url"] == "https://example.com/cover.jpg"
    assert body["track_count"] == 2
    assert body["favorite"] is False
    assert body["note"] is None
    assert body["last_played_at"] is None
    assert body["tags"] == []
    assert body["created_at"]
    assert [t["position"] for t in body["tracks"]] == [1, 2]
    assert body["tracks"][0]["title"] == "Born Under Punches"
    assert body["tracks"][0]["duration_seconds"] == 349
    assert all(t["id"] for t in body["tracks"])
    assert mock_import.calls == [("deezer", "302127")]

    # artwork downloaded into covers_dir as {album_id}.{ext}
    assert mock_artwork.calls == [("https://example.com/cover.jpg", body["id"])]
    album = db_session.get(Album, body["id"])
    assert album.cover_path == f"{body['id']}.jpg"
    # provider metadata persisted on the JSONB column (attribute: metadata_)
    assert album.metadata_ == {"genres": ["art rock"]}
    assert album.user_id == admin["id"]


def test_import_artwork_failure_never_fails_import(
    client, headers, db_session, mock_import, mock_artwork
):
    mock_import.install()
    mock_artwork.install(result="fail")
    res = client.post(
        "/api/albums/import",
        json={"source": "deezer", "external_id": "302127"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    album = db_session.get(Album, res.json()["id"])
    assert album.cover_path is None
    assert album.cover_url == "https://example.com/cover.jpg"  # remote fallback


def test_import_artwork_io_error_still_imports(
    client, headers, db_session, mock_import, mock_artwork
):
    mock_import.install()
    mock_artwork.install(url_error=True)
    res = client.post(
        "/api/albums/import",
        json={"source": "deezer", "external_id": "302127"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    assert db_session.get(Album, res.json()["id"]).cover_path is None


def test_import_duplicate_source_external_is_409(
    client, headers, mock_import, mock_artwork
):
    mock_import.install()
    mock_artwork.install()
    payload = {"source": "deezer", "external_id": "302127"}
    first = client.post("/api/albums/import", json=payload, headers=headers)
    assert first.status_code == 201
    res = client.post("/api/albums/import", json=payload, headers=headers)
    assert res.status_code == 409
    assert str(first.json()["id"]) in res.json()["detail"]


def test_import_soft_dedupe_title_artist_is_409(
    client, headers, mock_import, mock_artwork
):
    mock_import.install()
    mock_artwork.install()
    first = client.post(
        "/api/albums/import",
        json={"source": "deezer", "external_id": "302127"},
        headers=headers,
    )
    assert first.status_code == 201

    # Same album via the *other* source: different ids, case/whitespace-diff title
    def factory(source, external_id):
        return provider_album(
            source=source,
            external_id=external_id,
            title="  REMAIN IN LIGHT ",
            artist="talking heads",
        )

    mock_import.install(factory=factory)
    res = client.post(
        "/api/albums/import",
        json={"source": "musicbrainz", "external_id": "mbid-copy"},
        headers=headers,
    )
    assert res.status_code == 409
    assert str(first.json()["id"]) in res.json()["detail"]


def test_import_not_found_is_404(client, headers, mock_import):
    mock_import.install(error=NotFound("unknown album id 999"))
    res = client.post(
        "/api/albums/import",
        json={"source": "deezer", "external_id": "999"},
        headers=headers,
    )
    assert res.status_code == 404
    assert "unknown album id 999" in res.json()["detail"]


def test_import_provider_error_is_502(client, headers, mock_import):
    mock_import.install(error=ProviderError("deezer rate limited"))
    res = client.post(
        "/api/albums/import",
        json={"source": "deezer", "external_id": "302127"},
        headers=headers,
    )
    assert res.status_code == 502
    assert "deezer rate limited" in res.json()["detail"]


def test_import_rejects_unknown_source(client, headers, mock_import):
    mock_import.install()
    res = client.post(
        "/api/albums/import",
        json={"source": "spotify", "external_id": "x"},
        headers=headers,
    )
    assert res.status_code == 422
    assert mock_import.calls == []  # rejected before touching the provider


def test_import_requires_active_write_user(client, readonly_headers, mock_import):
    mock_import.install()
    res = client.post(
        "/api/albums/import",
        json={"source": "deezer", "external_id": "1"},
        headers=readonly_headers,
    )
    assert res.status_code == 403
    assert "Read-only" in res.json()["detail"]


def test_import_does_not_leak_other_users_shelves(
    client, headers, other_user, db_session, mock_import, mock_artwork
):
    """Soft-dedupe and hard-dedupe are per-user: same album in two shelves is OK."""
    mock_import.install()
    mock_artwork.install()
    payload = {"source": "deezer", "external_id": "302127"}
    mine = client.post("/api/albums/import", json=payload, headers=headers)
    theirs = client.post(
        "/api/albums/import", json=payload, headers=other_user["headers"]
    )
    assert mine.status_code == 201
    assert theirs.status_code == 201
    assert mine.json()["id"] != theirs.json()["id"]


# --- import preview (issue #13) ---------------------------------------------


def _preview_payload(source="deezer", external_id="302127"):
    return {"source": source, "external_id": external_id}


def test_preview_matches_a_real_import(
    client, headers, db_session, mock_import, mock_artwork
):
    mock_import.install()
    mock_artwork.install()
    payload = _preview_payload()

    imported = client.post("/api/albums/import", json=payload, headers=headers)
    assert imported.status_code == 201
    body = imported.json()

    res = client.post("/api/albums/preview", json=payload, headers=headers)
    assert res.status_code == 200
    preview = res.json()
    # Same identity, metadata, and tracklist as a real import of the same id.
    for field in (
        "source", "external_id", "title", "artist", "year", "label",
        "country", "cover_url", "track_count",
    ):
        assert preview[field] == body[field], field
    assert preview["tracks"] == [
        {k: t[k] for k in ("position", "title", "duration_seconds")}
        for t in body["tracks"]
    ]
    assert mock_import.calls == [("deezer", "302127"), ("deezer", "302127")]


def test_preview_persists_no_album_row(client, headers, db_session, mock_import):
    mock_import.install()
    before = db_session.query(Album).count()
    res = client.post("/api/albums/preview", json=_preview_payload(), headers=headers)
    assert res.status_code == 200
    assert db_session.query(Album).count() == before  # no row, no HTTP side effect


def test_preview_breakdown_merged(client, headers, mock_import):
    # MB metadata + Deezer tracklist/cover, both tracklists contributed.
    mock_import.install(
        factory=lambda s, e_id: provider_album(
            source=s,
            external_id=e_id,
            metadata_source="musicbrainz",
            tracklist_source="deezer",
            artwork_source="deezer",
            tracklists_by_source={
                "deezer": [
                    TrackInput(1, "Born Under Punches", 349),
                    TrackInput(2, "Crosseyed and Painless", 285),
                ],
                "musicbrainz": [
                    TrackInput(1, "Born Under Punches", 349),
                    TrackInput(2, "Crosseyed and Painless", 285),
                    TrackInput(3, "The Great Curve", 263),
                ],
            },
        )
    )
    res = client.post("/api/albums/preview", json=_preview_payload(), headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["source_breakdown"] == {
        "metadata_source": "musicbrainz",
        "tracklist_source": "deezer",
        "artwork_source": "deezer",
    }
    assert sorted(body["tracklists_by_source"]) == ["deezer", "musicbrainz"]
    assert [t["title"] for t in body["tracklists_by_source"]["deezer"]] == [
        "Born Under Punches",
        "Crosseyed and Painless",
    ]
    assert len(body["tracklists_by_source"]["musicbrainz"]) == 3
    # The main tracklist is the preferred (Deezer) one.
    assert [t["title"] for t in body["tracks"]] == [
        "Born Under Punches",
        "Crosseyed and Painless",
    ]


def test_preview_breakdown_single_source(client, headers, mock_import):
    # MusicBrainz-only: metadata + tracklist from MB, no artwork anywhere.
    mock_import.install(
        factory=lambda s, e_id: provider_album(
            source=s,
            external_id=e_id,
            metadata_source="musicbrainz",
            tracklist_source="musicbrainz",
            artwork_source=None,
            tracks=[TrackInput(1, "Only Track", 222)],
            tracklists_by_source={"musicbrainz": [TrackInput(1, "Only Track", 222)]},
        )
    )
    res = client.post(
        "/api/albums/preview",
        json=_preview_payload("musicbrainz", "mbid-1"),
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["source_breakdown"] == {
        "metadata_source": "musicbrainz",
        "tracklist_source": "musicbrainz",
        "artwork_source": None,
    }
    assert list(body["tracklists_by_source"]) == ["musicbrainz"]

    # Deezer-only: everything from Deezer, only its tracklist contributed.
    mock_import.install(
        factory=lambda s, e_id: provider_album(
            source=s,
            external_id=e_id,
            metadata_source="deezer",
            tracklist_source="deezer",
            artwork_source="deezer",
            tracks=[
                TrackInput(1, "One More Time", 320),
                TrackInput(2, "Aerodynamic", 207),
            ],
            tracklists_by_source={
                "deezer": [
                    TrackInput(1, "One More Time", 320),
                    TrackInput(2, "Aerodynamic", 207),
                ]
            },
        )
    )
    res = client.post("/api/albums/preview", json=_preview_payload(), headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["source_breakdown"] == {
        "metadata_source": "deezer",
        "tracklist_source": "deezer",
        "artwork_source": "deezer",
    }
    assert list(body["tracklists_by_source"]) == ["deezer"]
    assert body["track_count"] == 2
    assert body["tracks"][0]["title"] == "One More Time"


def test_preview_tracks_are_sorted_by_position(client, headers, mock_import):
    mock_import.install(
        factory=lambda s, e_id: provider_album(
            source=s,
            external_id=e_id,
            metadata_source="deezer",
            tracklist_source="deezer",
            artwork_source="deezer",
            tracks=[
                TrackInput(3, "Third", 100),
                TrackInput(1, "First", 100),
                TrackInput(2, "Second", 100),
            ],
            tracklists_by_source={
                "deezer": [
                    TrackInput(3, "Third", 100),
                    TrackInput(1, "First", 100),
                    TrackInput(2, "Second", 100),
                ]
            },
        )
    )
    res = client.post("/api/albums/preview", json=_preview_payload(), headers=headers)
    assert res.status_code == 200
    assert [t["position"] for t in res.json()["tracks"]] == [1, 2, 3]


def test_preview_not_found_is_404(client, headers, mock_import):
    mock_import.install(error=NotFound("unknown album id 999"))
    res = client.post(
        "/api/albums/preview", json=_preview_payload("deezer", "999"), headers=headers
    )
    assert res.status_code == 404
    assert "unknown album id 999" in res.json()["detail"]


def test_preview_provider_error_is_502(client, headers, mock_import):
    mock_import.install(error=ProviderError("deezer rate limited"))
    res = client.post("/api/albums/preview", json=_preview_payload(), headers=headers)
    assert res.status_code == 502
    assert "deezer rate limited" in res.json()["detail"]


def test_preview_rejects_unknown_source(client, headers, mock_import):
    mock_import.install()
    res = client.post(
        "/api/albums/preview",
        json={"source": "spotify", "external_id": "x"},
        headers=headers,
    )
    assert res.status_code == 422
    assert mock_import.calls == []  # rejected before touching the provider


def test_preview_allowed_for_read_only(client, readonly_headers, mock_import):
    """Preview is read-only: read_only accounts may preview (unlike import)."""
    mock_import.install()
    res = client.post(
        "/api/albums/preview", json=_preview_payload(), headers=readonly_headers
    )
    assert res.status_code == 200


def test_preview_does_not_409_when_already_on_shelf(
    client, headers, mock_import, mock_artwork
):
    mock_import.install()
    mock_artwork.install()
    payload = _preview_payload()
    first = client.post("/api/albums/import", json=payload, headers=headers)
    assert first.status_code == 201
    # Import of the same id would 409; the preview must still work.
    res = client.post("/api/albums/preview", json=payload, headers=headers)
    assert res.status_code == 200
    assert res.json()["title"] == "Remain in Light"


# --- list --------------------------------------------------------------------


def test_list_empty(client, headers):
    res = client.get("/api/albums", headers=headers)
    assert res.status_code == 200
    assert res.json() == []


def test_list_returns_tags_and_omits_tracks(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"], title="Remain in Light")
    attach_tags(db_session, album, "summer", "art-rock", user_id=admin["id"])
    add_tracks(db_session, album, (1, "Track One", 100))

    res = client.get("/api/albums", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["tags"] == ["art-rock", "summer"]  # sorted
    assert body[0]["tracks"] == []  # list variant carries no tracks


def test_list_q_filters_title_and_artist_case_insensitive(
    client, headers, db_session, admin
):
    make_album(db_session, admin["id"], title="Remain in Light", artist="Talking Heads")
    make_album(db_session, admin["id"], title="Blue", artist="Joni Mitchell")
    res = client.get("/api/albums", params={"q": "TALKING"}, headers=headers)
    assert [a["title"] for a in res.json()] == ["Remain in Light"]
    res = client.get("/api/albums", params={"q": "joni"}, headers=headers)
    assert [a["title"] for a in res.json()] == ["Blue"]
    res = client.get("/api/albums", params={"q": "emain"}, headers=headers)
    assert [a["title"] for a in res.json()] == ["Remain in Light"]


def test_list_tag_filter_single_and_all_of(
    client, headers, db_session, admin
):
    a = make_album(db_session, admin["id"], title="A")
    b = make_album(db_session, admin["id"], title="B")
    c = make_album(db_session, admin["id"], title="C")
    attach_tags(db_session, a, "chill", "summer", user_id=admin["id"])
    attach_tags(db_session, b, "summer", user_id=admin["id"])

    res = client.get("/api/albums", params={"tag": "summer"}, headers=headers)
    assert sorted(x["title"] for x in res.json()) == ["A", "B"]

    res = client.get(
        "/api/albums",
        params=[("tag", "summer"), ("tag", "chill")],
        headers=headers,
    )
    assert [x["title"] for x in res.json()] == ["A"]  # ALL-OF when repeated

    res = client.get("/api/albums", params={"tag": "nope"}, headers=headers)
    assert res.json() == []
    assert c.id  # silence unused


def test_list_favorite_filter(client, headers, db_session, admin):
    make_album(db_session, admin["id"], title="Loved", favorite=True)
    make_album(db_session, admin["id"], title="Plain")
    res = client.get("/api/albums", params={"favorite": "true"}, headers=headers)
    assert [a["title"] for a in res.json()] == ["Loved"]
    res = client.get("/api/albums", params={"favorite": "false"}, headers=headers)
    assert [a["title"] for a in res.json()] == ["Plain"]


def test_list_sort_added_is_newest_first(client, headers, db_session, admin):
    make_album(db_session, admin["id"], title="First")
    make_album(db_session, admin["id"], title="Second")
    make_album(db_session, admin["id"], title="Third")
    res = client.get("/api/albums", params={"sort": "added"}, headers=headers)
    assert [a["title"] for a in res.json()] == ["Third", "Second", "First"]


def test_list_sort_title_and_artist(client, headers, db_session, admin):
    make_album(db_session, admin["id"], title="banana", artist="Zebra")
    make_album(db_session, admin["id"], title="Apple", artist="alpha")
    make_album(db_session, admin["id"], title="cherry", artist="Cat")
    res = client.get("/api/albums", params={"sort": "title"}, headers=headers)
    assert [a["title"] for a in res.json()] == ["Apple", "banana", "cherry"]
    res = client.get("/api/albums", params={"sort": "artist"}, headers=headers)
    assert [a["artist"] for a in res.json()] == ["alpha", "Cat", "Zebra"]


def test_list_sort_year_nulls_last(client, headers, db_session, admin):
    make_album(db_session, admin["id"], title="NoYear", year=None)
    make_album(db_session, admin["id"], title="Later", year=1990)
    make_album(db_session, admin["id"], title="Earlier", year=1980)
    res = client.get("/api/albums", params={"sort": "year"}, headers=headers)
    assert [a["title"] for a in res.json()] == ["Earlier", "Later", "NoYear"]


def test_list_sort_played_desc_nulls_last(client, headers, db_session, admin):
    now = datetime.now(timezone.utc)
    make_album(
        db_session, admin["id"], title="Never", last_played_at=None
    )
    make_album(
        db_session,
        admin["id"],
        title="Old",
        last_played_at=now - timedelta(days=100),
    )
    make_album(
        db_session,
        admin["id"],
        title="Fresh",
        last_played_at=now - timedelta(days=1),
    )
    res = client.get("/api/albums", params={"sort": "played"}, headers=headers)
    assert [a["title"] for a in res.json()] == ["Fresh", "Old", "Never"]


def test_list_pagination(client, headers, db_session, admin):
    for i in range(3):
        make_album(db_session, admin["id"], title=f"Album {i}")
    res = client.get(
        "/api/albums", params={"sort": "title", "limit": 2, "offset": 1},
        headers=headers,
    )
    body = res.json()
    assert [a["title"] for a in body] == ["Album 1", "Album 2"]


def test_list_rejects_bad_sort(client, headers):
    res = client.get("/api/albums", params={"sort": "bogus"}, headers=headers)
    assert res.status_code == 422


def test_list_excludes_other_users_albums(
    client, headers, other_user, db_session
):
    make_album(
        db_session,
        other_user["id"],
        title="Bobs Record",
        external_id="bob-1",
    )
    res = client.get("/api/albums", headers=headers)
    assert res.json() == []
    res = client.get("/api/albums", headers=other_user["headers"])
    assert [a["title"] for a in res.json()] == ["Bobs Record"]


# --- detail ------------------------------------------------------------------


def test_detail_includes_tracks_sorted_by_position(
    client, headers, db_session, admin
):
    album = make_album(db_session, admin["id"], title="Remain in Light")
    add_tracks(
        db_session,
        album,
        (3, "Third", 200),
        (1, "First", 100),
        (2, "Second", 150),
    )
    res = client.get(f"/api/albums/{album.id}", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert [t["position"] for t in body["tracks"]] == [1, 2, 3]
    assert [t["title"] for t in body["tracks"]] == ["First", "Second", "Third"]
    assert body["tracks"][0]["duration_seconds"] == 100
    assert body["tags"] == []


def test_detail_404_for_missing_or_foreign_album(client, headers, other_user, db_session):
    assert client.get("/api/albums/999999", headers=headers).status_code == 404
    theirs = make_album(db_session, other_user["id"])
    assert (
        client.get(f"/api/albums/{theirs.id}", headers=headers).status_code == 404
    )


# --- patch -------------------------------------------------------------------


def test_patch_updates_all_fields(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"], title="T", artist="A")
    res = client.patch(
        f"/api/albums/{album.id}",
        json={
            "favorite": True,
            "note": "play loud",
            "year": 1981,
            "label": "Sire",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["favorite"] is True
    assert body["note"] == "play loud"
    assert body["year"] == 1981
    assert body["label"] == "Sire"
    db_session.refresh(album)
    assert album.favorite is True
    assert album.note == "play loud"


def test_patch_is_partial(client, headers, db_session, admin):
    album = make_album(
        db_session, admin["id"], note="keep me", year=1977, label="Old"
    )
    res = client.patch(
        f"/api/albums/{album.id}", json={"favorite": True}, headers=headers
    )
    assert res.status_code == 200
    body = res.json()
    assert body["favorite"] is True
    assert body["note"] == "keep me"
    assert body["year"] == 1977
    assert body["label"] == "Old"


def test_patch_can_clear_nullable_fields(client, headers, db_session, admin):
    album = make_album(
        db_session, admin["id"], note="temporary", year=1990, label="Tmp"
    )
    res = client.patch(
        f"/api/albums/{album.id}",
        json={"note": None, "year": None, "label": None},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["note"] is None
    assert res.json()["year"] is None
    assert res.json()["label"] is None


def test_patch_rejects_null_favorite(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    res = client.patch(
        f"/api/albums/{album.id}", json={"favorite": None}, headers=headers
    )
    assert res.status_code == 422


def test_patch_404_foreign_and_missing(client, headers, other_user, db_session):
    assert (
        client.patch(
            "/api/albums/999999", json={"favorite": True}, headers=headers
        ).status_code
        == 404
    )
    theirs = make_album(db_session, other_user["id"])
    res = client.patch(
        f"/api/albums/{theirs.id}", json={"favorite": True}, headers=headers
    )
    assert res.status_code == 404


def test_patch_forbidden_for_read_only(client, readonly_headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    res = client.patch(
        f"/api/albums/{album.id}", json={"favorite": True}, headers=readonly_headers
    )
    assert res.status_code == 403


# --- delete ------------------------------------------------------------------


def test_delete_cascades_and_removes_cached_cover(
    client, headers, db_session, admin, cover_root
):
    album = make_album(db_session, admin["id"], cover_path="42.jpg")
    album_id = album.id
    add_tracks(db_session, album, (1, "One", 100))
    attach_tags(db_session, album, "chill", user_id=admin["id"])
    db_session.add(Play(album_id=album.id, user_id=admin["id"]))
    db_session.commit()
    cached = cover_root / "42.jpg"
    cached.write_bytes(JPEG_MAGIC)

    res = client.delete(f"/api/albums/{album_id}", headers=headers)
    assert res.status_code == 204
    assert client.get(f"/api/albums/{album_id}", headers=headers).status_code == 404
    assert (
        db_session.query(Track).filter_by(album_id=album_id).count() == 0
    )  # tracks cascaded
    assert (
        db_session.query(Play).filter_by(album_id=album_id).count() == 0
    )  # plays cascaded
    assert not cached.exists()  # best-effort cover cleanup


def test_delete_404_foreign(client, headers, other_user, db_session):
    theirs = make_album(db_session, other_user["id"])
    assert (
        client.delete(f"/api/albums/{theirs.id}", headers=headers).status_code == 404
    )
    assert db_session.get(Album, theirs.id) is not None  # untouched


def test_delete_forbidden_for_read_only(client, readonly_headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    res = client.delete(f"/api/albums/{album.id}", headers=readonly_headers)
    assert res.status_code == 403


# --- cover endpoint ----------------------------------------------------------


def test_cover_serves_bytes_with_type_and_cache_headers(
    client, headers, db_session, admin, cover_root
):
    album = make_album(db_session, admin["id"], cover_path="1.jpg")
    (cover_root / "1.jpg").write_bytes(JPEG_MAGIC)

    res = client.get(f"/api/albums/{album.id}/cover", headers=headers)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/jpeg")
    assert res.headers["cache-control"] == "public, max-age=86400"
    assert res.content == JPEG_MAGIC


def test_cover_404_when_never_fetched(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"], cover_path=None)
    res = client.get(f"/api/albums/{album.id}/cover", headers=headers)
    assert res.status_code == 404  # frontend falls back to cover_url


def test_cover_404_when_file_missing(client, headers, db_session, admin, cover_root):
    album = make_album(db_session, admin["id"], cover_path="1.jpg")
    res = client.get(f"/api/albums/{album.id}/cover", headers=headers)
    assert res.status_code == 404


def test_cover_404_for_foreign_album(
    client, headers, other_user, db_session, cover_root
):
    theirs = make_album(db_session, other_user["id"], cover_path="9.jpg")
    (cover_root / "9.jpg").write_bytes(JPEG_MAGIC)
    res = client.get(f"/api/albums/{theirs.id}/cover", headers=headers)
    assert res.status_code == 404


def test_cover_path_traversal_is_blocked(
    client, headers, db_session, admin, cover_root, tmp_path
):
    secret = tmp_path / "secret.jpg"
    secret.write_bytes(b"SECRET")
    album = make_album(db_session, admin["id"], cover_path="../secret.jpg")
    res = client.get(f"/api/albums/{album.id}/cover", headers=headers)
    assert res.status_code == 404
    assert b"SECRET" not in res.content

    album.cover_path = "/etc/passwd"
    db_session.commit()
    res = client.get(f"/api/albums/{album.id}/cover", headers=headers)
    assert res.status_code == 404


# --- artwork module unit tests (httpx.MockTransport, no network) -------------


def _client_with(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_download_cover_stores_sniffed_png(tmp_path):
    def handler(request):
        return httpx.Response(
            200, content=PNG_BYTES, headers={"content-type": "image/png"}
        )

    name = artwork.download_cover(
        "http://img.example/cover", 7, covers_dir=tmp_path, client=_client_with(handler)
    )
    assert name == "7.png"
    assert (tmp_path / "7.png").read_bytes() == PNG_BYTES


def test_download_cover_sniffs_bytes_over_header(tmp_path):
    # Header lies (octet-stream), magic bytes say webp.
    body = b"RIFF\x00\x00\x00\x00WEBP " + b"payload"

    def handler(request):
        return httpx.Response(200, content=body)

    name = artwork.download_cover(
        "http://img.example/c", 8, covers_dir=tmp_path, client=_client_with(handler)
    )
    assert name == "8.webp"
    assert (tmp_path / "8.webp").read_bytes() == body


def test_download_cover_http_error_returns_none(tmp_path):
    def handler(request):
        return httpx.Response(404, content=b"nope")

    assert (
        artwork.download_cover(
            "http://img.example/c", 9, covers_dir=tmp_path, client=_client_with(handler)
        )
        is None
    )


def test_download_cover_html_error_page_returns_none(tmp_path):
    def handler(request):
        return httpx.Response(
            200,
            content=b"<html>lol</html>",
            headers={"content-type": "text/html"},
        )

    assert (
        artwork.download_cover(
            "http://img.example/c", 10, covers_dir=tmp_path, client=_client_with(handler)
        )
        is None
    )


def test_download_cover_rejects_non_image_payload(tmp_path):
    def handler(request):
        return httpx.Response(
            200, content=b"{" * 32, headers={"content-type": "image/png"}
        )

    assert (
        artwork.download_cover(
            "http://img.example/c", 11, covers_dir=tmp_path, client=_client_with(handler)
        )
        is None
    )
    assert list(tmp_path.iterdir()) == []  # nothing written


def test_download_cover_enforces_size_cap(tmp_path):
    def handler(request):
        return httpx.Response(200, content=PNG_BYTES * 100)

    assert (
        artwork.download_cover(
            "http://img.example/c",
            12,
            covers_dir=tmp_path,
            client=_client_with(handler),
            max_bytes=16,
        )
        is None
    )
    assert list(tmp_path.iterdir()) == []


def test_download_cover_network_error_returns_none(tmp_path):
    def handler(request):
        raise httpx.ConnectError("boom")

    assert (
        artwork.download_cover(
            "http://img.example/c", 13, covers_dir=tmp_path, client=_client_with(handler)
        )
        is None
    )


def test_resolve_cover_file_safety(tmp_path):
    root = tmp_path / "covers"
    root.mkdir()
    (root / "1.jpg").write_bytes(JPEG_MAGIC)
    (tmp_path / "outside.jpg").write_bytes(b"OUT")

    assert artwork.resolve_cover_file("1.jpg", root) == (root / "1.jpg").resolve()
    assert artwork.resolve_cover_file(None, root) is None
    assert artwork.resolve_cover_file("", root) is None
    assert artwork.resolve_cover_file("missing.jpg", root) is None
    assert artwork.resolve_cover_file("../outside.jpg", root) is None
    assert artwork.resolve_cover_file("sub/1.jpg", root) is None
    assert artwork.resolve_cover_file("..", root) is None
