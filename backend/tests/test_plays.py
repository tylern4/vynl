"""Play logging: backdating, future rejection, last_played_at recompute (PLAN §5)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from src.models import Album


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


def days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def parse_ts(value: str) -> datetime:
    """Parse a serialized timestamp (pydantic emits ``...Z`` for UTC; Python
    3.10's fromisoformat doesn't know the Z suffix)."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# --- auth --------------------------------------------------------------------


def test_play_endpoints_require_auth(client):
    assert client.post("/api/albums/1/plays", json={}).status_code == 401
    assert client.get("/api/albums/1/plays").status_code == 401
    assert client.delete("/api/albums/1/plays/1").status_code == 401


# --- POST /api/albums/{id}/plays ---------------------------------------------


def test_log_play_defaults_to_now(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    before = datetime.now(timezone.utc) - timedelta(seconds=5)
    res = client.post(f"/api/albums/{album.id}/plays", headers=headers)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["last_played_at"] is not None
    played = parse_ts(body["last_played_at"])
    assert played.tzinfo is not None
    assert played >= before

    plays = client.get(f"/api/albums/{album.id}/plays", headers=headers).json()
    assert len(plays) == 1
    assert set(plays[0].keys()) == {"id", "played_at"}

    db_session.refresh(album)
    assert album.last_played_at is not None


def test_log_play_accepts_backdate_keeps_max(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    now_play = client.post(f"/api/albums/{album.id}/plays", headers=headers)
    assert now_play.status_code == 201
    newest = now_play.json()["last_played_at"]

    backdate = days_ago(100)
    res = client.post(
        f"/api/albums/{album.id}/plays",
        json={"played_at": backdate},
        headers=headers,
    )
    assert res.status_code == 201
    # backdated play does not move last_played_at backwards (max semantics)
    assert res.json()["last_played_at"] == newest

    plays = client.get(f"/api/albums/{album.id}/plays", headers=headers).json()
    assert len(plays) == 2
    # newest first: the "now" play, then the backdated one
    assert parse_ts(plays[0]["played_at"]) >= parse_ts(plays[1]["played_at"])
    assert parse_ts(plays[1]["played_at"]) == parse_ts(backdate)


def test_log_play_only_backdated_sets_last_played(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    res = client.post(
        f"/api/albums/{album.id}/plays",
        json={"played_at": days_ago(30)},
        headers=headers,
    )
    assert res.status_code == 201
    last = parse_ts(res.json()["last_played_at"])
    assert (datetime.now(timezone.utc) - last).days in (29, 30)


def test_log_play_rejects_far_future(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    res = client.post(
        f"/api/albums/{album.id}/plays", json={"played_at": future}, headers=headers
    )
    assert res.status_code == 422
    assert client.get(f"/api/albums/{album.id}/plays", headers=headers).json() == []


def test_log_play_allows_small_future_skew(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    soon = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    res = client.post(
        f"/api/albums/{album.id}/plays", json={"played_at": soon}, headers=headers
    )
    assert res.status_code == 201


def test_log_play_accepts_naive_datetime_as_utc(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    res = client.post(
        f"/api/albums/{album.id}/plays",
        json={"played_at": "2020-05-05T12:00:00"},
        headers=headers,
    )
    assert res.status_code == 201
    assert res.json()["last_played_at"].startswith("2020-05-05")


def test_log_and_list_play_on_shared_album(client, headers, other_user, db_session):
    theirs = make_album(db_session, other_user["id"], title="Bobs Record")
    res = client.post(f"/api/albums/{theirs.id}/plays", headers=headers)
    assert res.status_code == 201
    res = client.get(f"/api/albums/{theirs.id}/plays", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 1  # the shared play is visible to everyone


def test_log_play_forbidden_for_read_only(
    client, headers, readonly_headers, db_session, admin
):
    album = make_album(db_session, admin["id"])
    res = client.post(f"/api/albums/{album.id}/plays", headers=readonly_headers)
    assert res.status_code == 403


def test_log_play_missing_body_is_ok(client, headers, db_session, admin):
    """No JSON body at all → played_at defaults to now (frontend sends {})."""
    album = make_album(db_session, admin["id"])
    res = client.post(f"/api/albums/{album.id}/plays", headers=headers)
    assert res.status_code == 201


# --- GET /api/albums/{id}/plays ----------------------------------------------


def test_list_plays_newest_first(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    for n in (30, 10, 20):  # deliberately out of chronological order
        res = client.post(
            f"/api/albums/{album.id}/plays",
            json={"played_at": days_ago(n)},
            headers=headers,
        )
        assert res.status_code == 201
    plays = client.get(f"/api/albums/{album.id}/plays", headers=headers).json()
    assert len(plays) == 3
    times = [p["played_at"] for p in plays]
    assert times == sorted(times, reverse=True)  # newest first


def test_list_plays_empty(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    assert client.get(f"/api/albums/{album.id}/plays", headers=headers).json() == []


# --- DELETE /api/albums/{id}/plays/{play_id} ---------------------------------


def test_delete_play_updates_max_then_null(
    client, headers, db_session, admin
):
    album = make_album(db_session, admin["id"])
    old_played_at = None
    client.post(
        f"/api/albums/{album.id}/plays",
        json={"played_at": days_ago(100)},
        headers=headers,
    )
    client.post(f"/api/albums/{album.id}/plays", headers=headers)
    # plays are newest-first: [new, old]
    plays = client.get(f"/api/albums/{album.id}/plays", headers=headers).json()
    assert len(plays) == 2
    new_id, old_id = plays[0]["id"], plays[1]["id"]
    old_played_at = plays[1]["played_at"]

    # delete the newest → last_played_at falls back to the old play
    res = client.delete(
        f"/api/albums/{album.id}/plays/{new_id}", headers=headers
    )
    assert res.status_code == 204
    album_out = client.get(f"/api/albums/{album.id}", headers=headers).json()
    assert album_out["last_played_at"] == old_played_at

    # delete the last remaining → null again
    res = client.delete(
        f"/api/albums/{album.id}/plays/{old_id}", headers=headers
    )
    assert res.status_code == 204
    album_out = client.get(f"/api/albums/{album.id}", headers=headers).json()
    assert album_out["last_played_at"] is None
    assert client.get(f"/api/albums/{album.id}/plays", headers=headers).json() == []


def test_delete_play_404_when_play_belongs_to_other_album(
    client, headers, db_session, admin
):
    a = make_album(db_session, admin["id"], title="A")
    b = make_album(db_session, admin["id"], title="B")
    client.post(f"/api/albums/{b.id}/plays", headers=headers)
    play_b_id = client.get(f"/api/albums/{b.id}/plays", headers=headers).json()[0]["id"]
    res = client.delete(f"/api/albums/{a.id}/plays/{play_b_id}", headers=headers)
    assert res.status_code == 404
    # untouched
    assert len(client.get(f"/api/albums/{b.id}/plays", headers=headers).json()) == 1


def test_delete_play_on_shared_album_from_any_account(
    client, headers, other_user, db_session
):
    theirs = make_album(db_session, other_user["id"])
    client.post(f"/api/albums/{theirs.id}/plays", headers=other_user["headers"])
    theirs_play_id = client.get(
        f"/api/albums/{theirs.id}/plays", headers=other_user["headers"]
    ).json()[0]["id"]
    res = client.delete(
        f"/api/albums/{theirs.id}/plays/{theirs_play_id}", headers=headers
    )
    assert res.status_code == 204
    assert (
        client.get(
            f"/api/albums/{theirs.id}/plays", headers=other_user["headers"]
        ).json()
        == []
    )


def test_delete_play_forbidden_for_read_only(
    client, headers, readonly_headers, db_session, admin
):
    album = make_album(db_session, admin["id"])
    play = client.post(f"/api/albums/{album.id}/plays", headers=readonly_headers)
    assert play.status_code == 403
    # no play was created by the rejected write
    assert client.get(f"/api/albums/{album.id}/plays", headers=headers).json() == []
