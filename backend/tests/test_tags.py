"""Tags: list/create (idempotent), replace-semantics PUT, delete (PLAN §5)."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from src.models import Album, Tag


@pytest.fixture()
def headers(admin, auth_headers):
    return auth_headers("admin@example.com")


@pytest.fixture()
def other_user(client, admin, register_user, auth_headers):
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


# --- GET/POST /api/tags ------------------------------------------------------


def test_get_tags_empty(client, headers):
    res = client.get("/api/tags", headers=headers)
    assert res.status_code == 200
    assert res.json() == []


def test_create_tag_normalizes_and_returns_exact_shape(client, headers):
    res = client.post("/api/tags", json={"name": "  Chill "}, headers=headers)
    assert res.status_code == 201, res.text
    body = res.json()
    assert set(body.keys()) == {"id", "name", "album_count"}
    assert body["name"] == "chill"  # lowercased + trimmed
    assert body["album_count"] == 0


def test_create_tag_is_idempotent(client, headers):
    first = client.post("/api/tags", json={"name": "chill"}, headers=headers)
    second = client.post("/api/tags", json={"name": "  CHILL "}, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 200  # existing name returned as-is
    assert second.json()["id"] == first.json()["id"]
    assert len(client.get("/api/tags", headers=headers).json()) == 1


def test_create_tag_rejects_empty(client, headers):
    assert (
        client.post("/api/tags", json={"name": ""}, headers=headers).status_code
        == 422
    )
    # whitespace-only passes pydantic's min_length but is rejected after trim
    assert (
        client.post("/api/tags", json={"name": "   "}, headers=headers).status_code
        == 422
    )


def test_get_tags_counts_linked_albums(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    res = client.post("/api/tags", json={"name": "summer"}, headers=headers)
    summer = res.json()
    client.post("/api/tags", json={"name": "unused"}, headers=headers)
    assert summer["album_count"] == 0

    res = client.put(
        f"/api/albums/{album.id}/tags", json={"tags": ["summer"]}, headers=headers
    )
    assert res.status_code == 200

    res = client.get("/api/tags", headers=headers)
    body = res.json()
    assert [t["name"] for t in body] == ["summer", "unused"]  # sorted by name
    assert {t["name"]: t["album_count"] for t in body} == {
        "summer": 1,
        "unused": 0,
    }


def test_tags_are_per_user(client, headers, other_user):
    mine = client.post("/api/tags", json={"name": "chill"}, headers=headers)
    theirs = client.post(
        "/api/tags", json={"name": "chill"}, headers=other_user["headers"]
    )
    assert mine.status_code == 201
    assert theirs.status_code == 201
    assert mine.json()["id"] != theirs.json()["id"]
    assert [t["name"] for t in client.get("/api/tags", headers=headers).json()] == [
        "chill"
    ]
    assert [
        t["name"] for t in client.get("/api/tags", headers=other_user["headers"]).json()
    ] == ["chill"]


def test_create_tag_forbidden_for_read_only(client, readonly_headers):
    res = client.post("/api/tags", json={"name": "nope"}, headers=readonly_headers)
    assert res.status_code == 403


# --- PUT /api/albums/{id}/tags (replace semantics) ---------------------------


def test_put_tags_replaces_the_set(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])

    res = client.put(
        f"/api/albums/{album.id}/tags",
        json={"tags": ["chill", "vinyl-33"]},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["tags"] == ["chill", "vinyl-33"]
    assert "tracks" in res.json()  # still an AlbumOut

    # Replacing with a different set unlinks the old tags entirely.
    res = client.put(
        f"/api/albums/{album.id}/tags", json={"tags": ["summer"]}, headers=headers
    )
    assert res.json()["tags"] == ["summer"]

    # The album itself is unchanged; orphaned tags remain but lose their count.
    res = client.get(f"/api/albums/{album.id}", headers=headers)
    assert res.json()["tags"] == ["summer"]
    counts = {
        t["name"]: t["album_count"]
        for t in client.get("/api/tags", headers=headers).json()
    }
    assert counts == {"chill": 0, "summer": 1, "vinyl-33": 0}


def test_put_tags_empty_clears(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    client.put(
        f"/api/albums/{album.id}/tags", json={"tags": ["a", "b"]}, headers=headers
    )
    res = client.put(f"/api/albums/{album.id}/tags", json={"tags": []}, headers=headers)
    assert res.status_code == 200
    assert res.json()["tags"] == []


def test_put_tags_normalizes_and_dedupes(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    res = client.put(
        f"/api/albums/{album.id}/tags",
        json={"tags": ["  Jazz ", "JAZZ", "blue"]},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["tags"] == ["blue", "jazz"]


def test_put_tags_creates_missing_and_reuses_existing(
    client, headers, db_session, admin
):
    existing = client.post("/api/tags", json={"name": "chill"}, headers=headers).json()
    album = make_album(db_session, admin["id"])
    res = client.put(
        f"/api/albums/{album.id}/tags",
        json={"tags": ["chill", "brand-new"]},
        headers=headers,
    )
    assert res.status_code == 200
    tags = {t["name"]: t["id"] for t in client.get("/api/tags", headers=headers).json()}
    assert tags["chill"] == existing["id"]  # reused, not duplicated
    assert "brand-new" in tags


def test_put_tags_rejects_empty_entry(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    url = f"/api/albums/{album.id}/tags"
    assert client.put(url, json={"tags": [""]}, headers=headers).status_code == 422
    assert client.put(url, json={"tags": ["  "]}, headers=headers).status_code == 422


def test_put_tags_404_foreign_album(client, headers, other_user, db_session):
    theirs = make_album(db_session, other_user["id"])
    res = client.put(
        f"/api/albums/{theirs.id}/tags", json={"tags": ["x"]}, headers=headers
    )
    assert res.status_code == 404


def test_put_tags_forbidden_for_read_only(client, readonly_headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    res = client.put(
        f"/api/albums/{album.id}/tags",
        json={"tags": ["x"]},
        headers=readonly_headers,
    )
    assert res.status_code == 403


# --- DELETE /api/tags/{id} ---------------------------------------------------


def test_delete_tag_everywhere(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    tag_id = client.post("/api/tags", json={"name": "chill"}, headers=headers).json()[
        "id"
    ]
    client.put(
        f"/api/albums/{album.id}/tags", json={"tags": ["chill"]}, headers=headers
    )

    res = client.delete(f"/api/tags/{tag_id}", headers=headers)
    assert res.status_code == 204
    assert client.get("/api/tags", headers=headers).json() == []
    # unlinked from the album too (FK cascade)
    assert client.get(f"/api/albums/{album.id}", headers=headers).json()["tags"] == []
    assert db_session.get(Tag, tag_id) is None


def test_delete_tag_404_foreign(client, headers, other_user):
    theirs = client.post(
        "/api/tags", json={"name": "bobs"}, headers=other_user["headers"]
    ).json()
    assert client.delete(f"/api/tags/{theirs['id']}", headers=headers).status_code == 404
    assert (
        client.get("/api/tags", headers=other_user["headers"]).json()[0]["name"]
        == "bobs"
    )


def test_delete_tag_requires_auth(client, admin):
    assert client.delete("/api/tags/1").status_code == 401
