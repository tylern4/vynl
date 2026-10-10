"""Recommendations: dusty invariants, random uniformity, tag filter, n clamps.

The RNG is injected via the ``get_rng`` FastAPI dependency — tests override it
with ``random.Random(seed)`` for deterministic picks (PLAN §5).
"""

import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from src.main import app
from src.models import Album, Tag
from src.routers.recommendations import get_rng


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


def use_seeded_rng(seed: int = 42):
    """Pin the injected RNG so every request replays the same sequence."""
    app.dependency_overrides[get_rng] = lambda: random.Random(seed)


def make_album(db, user_id, *, title=None, last_played_at=None, **fields):
    album = Album(
        user_id=user_id,
        title=title or f"Album {uuid4().hex[:8]}",
        artist="Artist",
        source="deezer",
        external_id=f"ext-{uuid4().hex[:12]}",
        last_played_at=last_played_at,
        **fields,
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


def attach_tag(db, album, name):
    tag = db.scalar(select(Tag).where(Tag.name == name))
    if tag is None:
        tag = Tag(name=name)
        db.add(tag)
    album.tags.append(tag)
    db.commit()


def ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


# --- general -----------------------------------------------------------------


def test_requires_auth(client):
    assert client.get("/api/recommendations").status_code == 401


def test_empty_shelf_returns_empty_list(client, headers):
    res = client.get("/api/recommendations", headers=headers)
    assert res.status_code == 200
    assert res.json() == []


def test_invalid_mode_is_422(client, headers):
    res = client.get(
        "/api/recommendations", params={"mode": "sideways"}, headers=headers
    )
    assert res.status_code == 422


def test_result_shape(client, headers, db_session, admin):
    album = make_album(db_session, admin["id"])
    res = client.get("/api/recommendations", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert set(body[0].keys()) == {"album", "reason", "days_since_played"}
    assert body[0]["album"]["id"] == album.id
    assert body[0]["album"]["tracks"] == []  # AlbumOut without tracks
    assert body[0]["reason"] == "Never played"
    assert body[0]["days_since_played"] is None


# --- dusty invariants --------------------------------------------------------


def test_dusty_never_played_ranks_first(client, headers, db_session, admin):
    fresh = make_album(db_session, admin["id"], last_played_at=ago(1))
    never = make_album(db_session, admin["id"])
    old = make_album(db_session, admin["id"], last_played_at=ago(100))
    make_album(db_session, admin["id"], last_played_at=ago(2))
    use_seeded_rng(7)

    res = client.get(
        "/api/recommendations", params={"mode": "dusty", "n": 1}, headers=headers
    )
    assert res.status_code == 200
    picks = res.json()
    assert len(picks) == 1
    # bottom of the dusty ranking (never-played, id tiebreak) beats everything
    assert picks[0]["album"]["id"] == never.id
    assert picks[0]["reason"] == "Never played"
    assert fresh.id and old.id  # fixture albums existed


def test_dusty_never_played_before_played_when_n_grows(
    client, headers, db_session, admin
):
    played_ids = {
        make_album(db_session, admin["id"], last_played_at=ago(d)).id
        for d in (100, 90, 80, 1, 2, 3)
    }
    never_ids = {make_album(db_session, admin["id"]).id for _ in range(4)}
    use_seeded_rng(3)

    res = client.get(
        "/api/recommendations", params={"mode": "dusty", "n": 4}, headers=headers
    )
    picks = res.json()
    assert len(picks) == 4
    picked = {p["album"]["id"] for p in picks}
    assert picked == never_ids  # all 4 never-played come before any played
    assert not picked & played_ids


def test_dusty_skips_recent_plays_when_alternatives_exist(
    client, headers, db_session, admin
):
    old = make_album(db_session, admin["id"], last_played_at=ago(60))
    for _ in range(7):
        make_album(db_session, admin["id"], last_played_at=ago(1))
    use_seeded_rng(11)

    res = client.get(
        "/api/recommendations", params={"mode": "dusty", "n": 1}, headers=headers
    )
    picks = res.json()
    assert len(picks) == 1
    # the only non-fresh candidate wins even though 7 fresher ones exist
    assert picks[0]["album"]["id"] == old.id
    assert picks[0]["days_since_played"] is not None
    assert picks[0]["days_since_played"] >= 59


def test_dusty_keeps_fresh_when_no_alternatives(client, headers, db_session, admin):
    make_album(db_session, admin["id"], last_played_at=ago(1))
    make_album(db_session, admin["id"], last_played_at=ago(2))
    use_seeded_rng(5)

    res = client.get(
        "/api/recommendations", params={"mode": "dusty", "n": 1}, headers=headers
    )
    assert res.status_code == 200
    assert len(res.json()) == 1  # still answers from fresh-only shelf


def test_dusty_has_no_duplicates(client, headers, db_session, admin):
    for _ in range(8):
        make_album(db_session, admin["id"])
    use_seeded_rng(99)

    res = client.get(
        "/api/recommendations", params={"mode": "dusty", "n": 5}, headers=headers
    )
    ids = [p["album"]["id"] for p in res.json()]
    assert len(ids) == 5
    assert len(set(ids)) == 5


def test_dusty_reason_and_days_for_played_album(client, headers, db_session, admin):
    make_album(db_session, admin["id"], last_played_at=ago(60))
    res = client.get(
        "/api/recommendations", params={"mode": "dusty", "n": 1}, headers=headers
    )
    pick = res.json()[0]
    assert pick["reason"].startswith("Haven't spun this since ")
    assert pick["days_since_played"] in (59, 60)


# --- random mode -------------------------------------------------------------


def test_random_no_duplicates(client, headers, db_session, admin):
    for _ in range(10):
        make_album(db_session, admin["id"])
    use_seeded_rng(2)

    res = client.get(
        "/api/recommendations", params={"mode": "random", "n": 5}, headers=headers
    )
    ids = [p["album"]["id"] for p in res.json()]
    assert len(ids) == 5
    assert len(set(ids)) == 5


def test_random_reason_is_random_pick(client, headers, db_session, admin):
    make_album(db_session, admin["id"], last_played_at=ago(10))
    res = client.get(
        "/api/recommendations", params={"mode": "random", "n": 1}, headers=headers
    )
    pick = res.json()[0]
    assert pick["reason"] == "Random pick"
    assert pick["days_since_played"] in (9, 10)


# --- tag filter --------------------------------------------------------------


def test_tag_filter_applies_in_both_modes(client, headers, db_session, admin):
    tagged = [
        make_album(db_session, admin["id"]) for _ in range(3)
    ]
    for album in tagged:
        attach_tag(db_session, album, "chill")
    for _ in range(3):
        make_album(db_session, admin["id"])  # untagged
    use_seeded_rng(4)

    for mode in ("dusty", "random"):
        res = client.get(
            "/api/recommendations",
            params={"mode": mode, "tag": "CHILL", "n": 3},
            headers=headers,
        )
        assert res.status_code == 200
        picks = res.json()
        assert len(picks) == 3
        assert {p["album"]["id"] for p in picks} == {a.id for a in tagged}


def test_tag_filter_no_match_returns_empty(client, headers, db_session, admin):
    make_album(db_session, admin["id"])
    res = client.get(
        "/api/recommendations", params={"tag": "nope"}, headers=headers
    )
    assert res.status_code == 200
    assert res.json() == []


# --- n clamping --------------------------------------------------------------


def test_n_clamped_to_one_for_zero_or_negative(client, headers, db_session, admin):
    for _ in range(5):
        make_album(db_session, admin["id"])
    for n in (0, -3):
        res = client.get(
            "/api/recommendations", params={"n": n}, headers=headers
        )
        assert res.status_code == 200
        assert len(res.json()) == 1


def test_n_clamped_to_twenty(client, headers, db_session, admin):
    for _ in range(25):
        make_album(db_session, admin["id"])
    for mode in ("dusty", "random"):
        res = client.get(
            "/api/recommendations",
            params={"mode": mode, "n": 100},
            headers=headers,
        )
        assert res.status_code == 200
        ids = [p["album"]["id"] for p in res.json()]
        assert len(ids) == 20
        assert len(set(ids)) == 20


def test_returns_fewer_than_n_when_shelf_is_small(client, headers, db_session, admin):
    only = make_album(db_session, admin["id"])
    res = client.get(
        "/api/recommendations", params={"n": 10}, headers=headers
    )
    assert [p["album"]["id"] for p in res.json()] == [only.id]


# --- determinism (injected RNG) ----------------------------------------------


def test_seeded_rng_is_deterministic(client, headers, db_session, admin):
    for _ in range(8):
        make_album(db_session, admin["id"])

    use_seeded_rng(123)
    first = client.get(
        "/api/recommendations", params={"mode": "random", "n": 4}, headers=headers
    ).json()
    second = client.get(
        "/api/recommendations", params={"mode": "random", "n": 4}, headers=headers
    ).json()
    assert [p["album"]["id"] for p in first] == [p["album"]["id"] for p in second]

    first = client.get(
        "/api/recommendations", params={"mode": "dusty", "n": 3}, headers=headers
    ).json()
    second = client.get(
        "/api/recommendations", params={"mode": "dusty", "n": 3}, headers=headers
    ).json()
    assert [p["album"]["id"] for p in first] == [p["album"]["id"] for p in second]


# --- ownership scoping -------------------------------------------------------


def test_recommends_from_shared_shelf(client, headers, other_user, db_session):
    theirs = make_album(db_session, other_user["id"], last_played_at=None)
    # The shared shelf means every user recommends from the same pool.
    res = client.get("/api/recommendations", headers=headers)
    assert [p["album"]["id"] for p in res.json()] == [theirs.id]
    res = client.get("/api/recommendations", headers=other_user["headers"])
    assert [p["album"]["id"] for p in res.json()] == [theirs.id]
