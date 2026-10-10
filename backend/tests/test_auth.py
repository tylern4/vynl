def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_register_first_user_creates_active_admin(client, register_user):
    res = register_user(email="admin@example.com")
    assert res.status_code == 201
    body = res.json()
    assert body["user"]["role"] == "admin"
    assert body["user"]["status"] == "active"
    assert body["access_token"]


def test_register_first_user_requires_invite_code(client, register_user):
    res = register_user(email="admin@example.com", invite_code=None)
    assert res.status_code == 403
    assert res.json()["detail"] == "Invalid invite code"
    # A wrong code is just as fatal for the bootstrap account.
    res = register_user(email="admin2@example.com", invite_code="wrong-code")
    assert res.status_code == 403
    assert res.json()["detail"] == "Invalid invite code"


def test_later_signups_do_not_need_invite_code(client, register_user, admin):
    res = register_user(email="bob@example.com", invite_code=None)
    assert res.status_code == 201
    body = res.json()
    assert body["user"]["role"] == "user"  # not admin
    assert body["user"]["status"] == "pending"
    assert body["access_token"] is None

    # Any code is fine once the first account exists — it is ignored.
    res = register_user(email="carol@example.com", invite_code="wrong-code")
    assert res.status_code == 201
    assert res.json()["user"]["status"] == "pending"


def test_register_second_user_is_pending(client, register_user, admin):
    res = register_user(email="bob@example.com")
    assert res.status_code == 201
    body = res.json()
    assert body["user"]["role"] == "user"
    assert body["user"]["status"] == "pending"
    assert body["access_token"] is None


def test_register_duplicate_email_conflicts(client, register_user, admin):
    assert register_user(email="bob@example.com").status_code == 201
    assert register_user(email="bob@example.com").status_code == 409


def test_register_rejects_short_password(client, register_user):
    assert register_user(password="short").status_code == 422


def test_login_success(client, register_user, admin):
    res = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "admin@example.com"


def test_login_wrong_password(client, register_user, admin):
    res = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "wrongpass1"},
    )
    assert res.status_code == 401


def test_login_unknown_user(client):
    res = client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "password123"},
    )
    assert res.status_code == 401


def test_login_pending_user_forbidden(client, register_user, admin):
    register_user(email="bob@example.com")
    res = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "password123"},
    )
    assert res.status_code == 403


def test_login_denied_user_forbidden(client, register_user, admin, auth_headers):
    register_user(email="bob@example.com")
    headers = auth_headers("admin@example.com")
    res = client.patch("/api/users/2", json={"status": "denied"}, headers=headers)
    assert res.status_code == 200
    res = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "password123"},
    )
    assert res.status_code == 403


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_token(client, register_user, admin, auth_headers):
    res = client.get("/api/auth/me", headers=auth_headers("admin@example.com"))
    assert res.status_code == 200
    assert res.json()["email"] == "admin@example.com"


def test_me_rejects_bad_token(client, register_user, admin):
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert res.status_code == 401


def test_me_rejects_token_of_deleted_user(client, register_user, admin, auth_headers):
    register_user(email="bob@example.com")
    admin_headers = auth_headers("admin@example.com")
    client.patch("/api/users/2", json={"status": "active"}, headers=admin_headers)
    bob_headers = auth_headers("bob@example.com")
    assert client.delete("/api/users/2", headers=admin_headers).status_code == 204
    res = client.get("/api/auth/me", headers=bob_headers)
    assert res.status_code == 401


def test_me_rejects_token_of_deactivated_user(
    client, register_user, admin, auth_headers
):
    register_user(email="bob@example.com")
    admin_headers = auth_headers("admin@example.com")
    client.patch("/api/users/2", json={"status": "active"}, headers=admin_headers)
    bob_headers = auth_headers("bob@example.com")
    client.patch("/api/users/2", json={"status": "denied"}, headers=admin_headers)
    res = client.get("/api/auth/me", headers=bob_headers)
    assert res.status_code == 403


def test_admin_approval_flow(client, register_user, admin, auth_headers):
    register_user(email="bob@example.com")
    res = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "password123"},
    )
    assert res.status_code == 403

    headers = auth_headers("admin@example.com")
    res = client.patch("/api/users/2", json={"status": "active"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "active"

    res = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "password123"},
    )
    assert res.status_code == 200
    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {res.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "bob@example.com"


def test_list_users_requires_auth(client):
    assert client.get("/api/users").status_code == 401


def test_list_users_requires_admin(client, register_user, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    register_user(email="bob@example.com")
    client.patch("/api/users/2", json={"status": "active"}, headers=headers)
    res = client.get("/api/users", headers=auth_headers("bob@example.com"))
    assert res.status_code == 403


def test_admin_lists_users(client, register_user, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    register_user(email="bob@example.com")
    res = client.get("/api/users", headers=headers)
    assert res.status_code == 200
    emails = {u["email"] for u in res.json()}
    assert emails == {"admin@example.com", "bob@example.com"}


def test_admin_updates_role(client, register_user, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    register_user(email="bob@example.com")
    res = client.patch("/api/users/2", json={"role": "read_only"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["role"] == "read_only"


def test_cannot_demote_last_admin(client, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    res = client.patch("/api/users/1", json={"role": "user"}, headers=headers)
    assert res.status_code == 400


def test_admin_resets_password(client, register_user, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    register_user(email="bob@example.com")
    client.patch("/api/users/2", json={"status": "active"}, headers=headers)
    res = client.patch(
        "/api/users/2", json={"password": "newpass123"}, headers=headers
    )
    assert res.status_code == 200
    assert res.json()["email"] == "bob@example.com"
    login = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "newpass123"},
    )
    assert login.status_code == 200
    stale = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "password123"},
    )
    assert stale.status_code == 401


def test_reset_password_rejects_short_password(client, register_user, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    register_user(email="bob@example.com")
    res = client.patch("/api/users/2", json={"password": "short"}, headers=headers)
    assert res.status_code == 422


def test_non_admin_cannot_update_users(client, register_user, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    register_user(email="bob@example.com")
    client.patch("/api/users/2", json={"status": "active"}, headers=headers)
    bob_headers = auth_headers("bob@example.com")
    res = client.patch(
        "/api/users/1", json={"password": "sneakypass1"}, headers=bob_headers
    )
    assert res.status_code == 403
    res = client.delete("/api/users/1", headers=bob_headers)
    assert res.status_code == 403


def test_cannot_deny_or_delete_self(client, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    res = client.patch("/api/users/1", json={"status": "denied"}, headers=headers)
    assert res.status_code == 400
    assert client.delete("/api/users/1", headers=headers).status_code == 400


def test_delete_user(client, register_user, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    register_user(email="bob@example.com")
    assert client.delete("/api/users/2", headers=headers).status_code == 204
    res = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "password123"},
    )
    assert res.status_code == 401


def test_reference_action_routes(client, register_user, admin, auth_headers):
    """Approve/deny/role/reset-password action routes mirror the reference project."""
    register_user(email="bob@example.com")
    headers = auth_headers("admin@example.com")

    res = client.post("/api/users/2/approve", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "active"

    res = client.post("/api/users/2/deny", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "denied"
    assert client.post("/api/users/1/deny", headers=headers).status_code == 400

    res = client.patch("/api/users/2/role", json={"role": "read_only"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["role"] == "read_only"

    res = client.post(
        "/api/users/2/reset-password",
        json={"password": "newpass123"},
        headers=headers,
    )
    assert res.status_code == 200
    client.post("/api/users/2/approve", headers=headers)
    login = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "newpass123"},
    )
    assert login.status_code == 200
    stale = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "password123"},
    )
    assert stale.status_code == 401


# --- admin user creation (issue #9) -----------------------------------------


def test_admin_creates_active_user(client, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    res = client.post(
        "/api/users",
        json={"name": "Carol", "email": "carol@example.com", "password": "password123"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["email"] == "carol@example.com"
    assert body["role"] == "user"
    assert body["status"] == "active"
    assert body["created_at"]
    # Usable immediately — no admin approval step.
    login = client.post(
        "/api/auth/login",
        json={"email": "carol@example.com", "password": "password123"},
    )
    assert login.status_code == 200


def test_admin_creates_user_with_custom_role(client, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    res = client.post(
        "/api/users",
        json={
            "name": "Reader",
            "email": "reader@example.com",
            "password": "password123",
            "role": "read_only",
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    assert res.json()["role"] == "read_only"


def test_admin_can_create_second_admin(client, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    res = client.post(
        "/api/users",
        json={
            "name": "Second",
            "email": "second@example.com",
            "password": "password123",
            "role": "admin",
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    assert res.json()["role"] == "admin"


def test_create_user_requires_admin(client, register_user, admin, auth_headers):
    register_user(email="bob@example.com")
    headers = auth_headers("admin@example.com")
    client.patch("/api/users/2", json={"status": "active"}, headers=headers)
    res = client.post(
        "/api/users",
        json={"name": "Mallory", "email": "mallory@example.com", "password": "password123"},
        headers=auth_headers("bob@example.com"),
    )
    assert res.status_code == 403


def test_create_user_unauthenticated(client):
    res = client.post(
        "/api/users",
        json={"name": "Anon", "email": "anon@example.com", "password": "password123"},
    )
    assert res.status_code == 401


def test_create_user_duplicate_email_conflicts(client, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    payload = {"name": "Dup", "email": "dup@example.com", "password": "password123"}
    assert client.post("/api/users", json=payload, headers=headers).status_code == 201
    assert client.post("/api/users", json=payload, headers=headers).status_code == 409


def test_create_user_rejects_short_password(client, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    res = client.post(
        "/api/users",
        json={"name": "Short", "email": "short@example.com", "password": "short"},
        headers=headers,
    )
    assert res.status_code == 422


def test_create_user_rejects_bad_email(client, admin, auth_headers):
    headers = auth_headers("admin@example.com")
    res = client.post(
        "/api/users",
        json={"name": "Bad", "email": "not-an-email", "password": "password123"},
        headers=headers,
    )
    assert res.status_code == 422
