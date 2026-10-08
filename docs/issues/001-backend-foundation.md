# #1: Backend foundation — config, database, models, migrations, auth

- **Status:** done
- **Assignee:** agent-backend-1
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

- [x] `backend/` contains `requirements.txt` (pinned: fastapi, uvicorn, sqlalchemy,
      alembic, psycopg[binary], pydantic-settings, email-validator, bcrypt, PyJWT,
      **httpx**), `requirements-dev.txt` (+ pytest, httpx), `pytest.ini`,
      `Dockerfile` (python:3.12-slim, uvicorn on 8000), `alembic.ini`, `alembic/`.
- [x] `src/config.py` — pydantic-settings `Settings` with `database_url`,
      `jwt_secret`, `jwt_algorithm`, `access_token_expire_minutes`, `invite_code`,
      `musicbrainz_contact`, `covers_dir` (default `covers`), `env_file=".env"`.
- [x] `src/database.py` — engine with `pool_pre_ping`, `SessionLocal`, `get_db`
      (reference pattern).
- [x] `src/models.py` — **all** tables from PLAN §4: `users`, `albums`, `tracks`,
      `tags`, `album_tags`, `plays`, with the enums (`userrole`, `userstatus`),
      FK delete rules, JSONB `metadata`, unique `(user_id, source, external_id)`
      on albums, unique `(album_id, position)` on tracks, unique `(user_id, name)`
      on tags, indexes noted in PLAN §4.
- [x] `src/migrations.py` + Alembic env wired like the reference; initial revision
      `0001_initial.py` creates every table; migrations run on startup
      (`run_migrations()` in lifespan) with `compare_type=True`.
- [x] `src/auth.py` — bcrypt hash/verify, HS256 `create_access_token`,
      `get_current_user`, `get_admin_user`, `require_write` (copied semantics from
      reference; 401/403 handling identical).
- [x] `src/schemas.py` — `RegisterRequest`, `LoginRequest`, `UserOut`,
      `UserAdminOut`, `RegisterOut`, `TokenOut`, `RoleUpdate`, `PasswordReset`
      (from PLAN §5 auth table). Album/track/tag schemas belong to #3 — leave them
      out unless convenient.
- [x] `src/routers/auth.py` + `src/routers/users.py` — register (first account =
      admin+active, later accounts pending, invite code required), login,
      `GET /api/auth/me`, admin `GET/PATCH /api/users` (approve/deny, role,
      password reset, delete) — same behavior as reference.
- [x] `src/main.py` — FastAPI app titled `"vynl API"`, lifespan guards weak
      `JWT_SECRET` and runs migrations, CORS `*`, routers mounted under `/api`,
      `GET /api/health`.
- [x] `backend/tests/` — `conftest.py` from the reference (dispose/recreate
      `<db>_test`, session engine, `get_db` override, TestClient) plus
      `test_auth.py` covering register/login/me, wrong invite code, pending user
      cannot login, admin user approval flow. `pytest` passes locally against a
      running Postgres.
- [x] No provider or album/track/tag endpoint code — that's #2/#3.

## Notes

- Reference source: clone `https://github.com/tylern4/baby-tracking-app` and read
  `backend/src/{config,database,models,auth,migrations,main}.py`,
  `backend/src/routers/{auth,users}.py`, `backend/tests/conftest.py`.
- `httpx` in `requirements.txt` is deliberate: #2's music providers import it.
- `.env.example` already lists the env vars; config field names should map 1:1
  (UPPER_SNAKE env → lowercase attr via pydantic-settings).
- Do not create `src/providers/` or album routers — issues #2/#3.

### Implementation notes (agent-backend-1, 2026-10-08)

- **Invite code is required on every registration** (not just the first), per
  `.env.example` ("Anyone registering must supply this") and this issue's
  "invite code required". Wrong/missing code → `403 {"detail": "Invalid invite
  code"}` for first *and* later signups; the first account is still the only one
  created `admin`+`active`. The reference only checked the code for the setup
  account — this is a deliberate vynl divergence. Frontend: surface the 403
  detail on the register form for any signup.
- **User admin surface:** PLAN §5 shape is primary — `GET /api/users`,
  `PATCH /api/users/{id}` with body `{status?, role?, password?}` (approve =
  `{"status": "active"}`, deny = `{"status": "denied"}`, plus role/password),
  `DELETE /api/users/{id}` (204). The reference action routes
  (`POST /users/{id}/approve|deny`, `PATCH /users/{id}/role`,
  `POST /users/{id}/reset-password`) are also exposed and behave identically
  (shared helpers), so both the PLAN and "same as reference" readings work.
  Guards: last-admin demotion → 400, deny/delete self → 400.
- `albums.metadata` column is exposed as the Python attribute
  **`album.metadata_`** (SQLAlchemy reserves `metadata` on mapped classes).
  Column name in the DB is `metadata` as PLAN §4 specifies.
- `require_write` is in place for #3's write endpoints; its 403 detail reads
  "Read-only account cannot make changes" (reference said "…edit entries").
- Lifespan weak-secret guard rejects `dev-secret-change-me`, `change-me`, and
  `change-me-in-production` (the `.env.example` default).
- `tests/conftest.py` `register_user` fixture defaults `invite_code` to
  `settings.invite_code` (since every registration now needs one); tests that
  exercise bad codes pass `invite_code=None`/a wrong value explicitly.
- Verified beyond pytest: `alembic check` reports no model/migration drift, the
  lifespan guard + health boot via TestClient, and `docker build ./backend`
  produces a container that serves `/api/health` + register against the compose
  Postgres. Dev `vynl` DB left empty (schema dropped after the smoke test).
- No non-backend files needed changes.
