# #1: Backend foundation — config, database, models, migrations, auth

- **Status:** open
- **Assignee:** unassigned
- **Labels:** backend, foundation
- **Depends on:** none
- **Wave:** 1 (runs in parallel with #4; touches only `backend/`)

## Summary

Stand up the FastAPI backend skeleton exactly in the style of
[baby-tracking-app](https://github.com/tylern4/baby-tracking-app): settings, engine/
session, the **complete data model** from [PLAN.md §4](../PLAN.md#4-data-model),
Alembic migrations, JWT/invite-code auth, admin user management, and a health
endpoint. Issues #2 and #3 build on top of this, so the models and auth must be in
place and stable.

## Acceptance criteria

- [ ] `backend/` contains `requirements.txt` (pinned: fastapi, uvicorn, sqlalchemy,
      alembic, psycopg[binary], pydantic-settings, email-validator, bcrypt, PyJWT,
      **httpx**), `requirements-dev.txt` (+ pytest, httpx), `pytest.ini`,
      `Dockerfile` (python:3.12-slim, uvicorn on 8000), `alembic.ini`, `alembic/`.
- [ ] `src/config.py` — pydantic-settings `Settings` with `database_url`,
      `jwt_secret`, `jwt_algorithm`, `access_token_expire_minutes`, `invite_code`,
      `musicbrainz_contact`, `covers_dir` (default `covers`), `env_file=".env"`.
- [ ] `src/database.py` — engine with `pool_pre_ping`, `SessionLocal`, `get_db`
      (reference pattern).
- [ ] `src/models.py` — **all** tables from PLAN §4: `users`, `albums`, `tracks`,
      `tags`, `album_tags`, `plays`, with the enums (`userrole`, `userstatus`),
      FK delete rules, JSONB `metadata`, unique `(user_id, source, external_id)`
      on albums, unique `(album_id, position)` on tracks, unique `(user_id, name)`
      on tags, indexes noted in PLAN §4.
- [ ] `src/migrations.py` + Alembic env wired like the reference; initial revision
      `0001_initial.py` creates every table; migrations run on startup
      (`run_migrations()` in lifespan) with `compare_type=True`.
- [ ] `src/auth.py` — bcrypt hash/verify, HS256 `create_access_token`,
      `get_current_user`, `get_admin_user`, `require_write` (copied semantics from
      reference; 401/403 handling identical).
- [ ] `src/schemas.py` — `RegisterRequest`, `LoginRequest`, `UserOut`,
      `UserAdminOut`, `RegisterOut`, `TokenOut`, `RoleUpdate`, `PasswordReset`
      (from PLAN §5 auth table). Album/track/tag schemas belong to #3 — leave them
      out unless convenient.
- [ ] `src/routers/auth.py` + `src/routers/users.py` — register (first account =
      admin+active, later accounts pending, invite code required), login,
      `GET /api/auth/me`, admin `GET/PATCH /api/users` (approve/deny, role,
      password reset, delete) — same behavior as reference.
- [ ] `src/main.py` — FastAPI app titled `"vynl API"`, lifespan guards weak
      `JWT_SECRET` and runs migrations, CORS `*`, routers mounted under `/api`,
      `GET /api/health`.
- [ ] `backend/tests/` — `conftest.py` from the reference (dispose/recreate
      `<db>_test`, session engine, `get_db` override, TestClient) plus
      `test_auth.py` covering register/login/me, wrong invite code, pending user
      cannot login, admin user approval flow. `pytest` passes locally against a
      running Postgres.
- [ ] No provider or album/track/tag endpoint code — that's #2/#3.

## Notes

- Reference source: clone `https://github.com/tylern4/baby-tracking-app` and read
  `backend/src/{config,database,models,auth,migrations,main}.py`,
  `backend/src/routers/{auth,users}.py`, `backend/tests/conftest.py`.
- `httpx` in `requirements.txt` is deliberate: #2's music providers import it.
- `.env.example` already lists the env vars; config field names should map 1:1
  (UPPER_SNAKE env → lowercase attr via pydantic-settings).
- Do not create `src/providers/` or album routers — issues #2/#3.
