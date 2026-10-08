# #7: Integration — compose hardening, CI, README, smoke test, screenshots

- **Status:** done
- **Assignee:** agent-integration-7
- **Labels:** infra, ci, docs
- **Depends on:** #3, #5, #6 (all features landed)
- **Wave:** 5

## Summary

Take the assembled app from "works in dev" to "one command in production": finalize
Docker Compose, add the GitHub Actions CI (tests + GHCR image builds), run a real
`docker compose up` smoke test, and finish the README with screenshots.

## Acceptance criteria

**Compose**

- [x] `docker-compose.yml` matches PLAN §8: three services, `db_data` +
      `covers_data` volumes, healthcheck-gated backend start, `restart:
      unless-stopped`, ports 5432/8000/8080, env from `.env` with `:?` required
      guards for `JWT_SECRET`/`INVITE_CODE`, `COVERS_DIR=/app/covers` volume
      mounted, `MUSICBRAINZ_CONTACT` passed through. (Already correct as
      committed — verified `docker compose config`; only change was the
      optional `MUSICBRAINZ_CONTACT` default `:-`.)
- [x] Backend `Dockerfile` copies `covers/` dir creation (or create at startup);
      artwork survives container recreation (verify volume write). Added
      `RUN mkdir -p /app/covers`; artwork.py also mkdirs at write time. Verified:
      cover hash identical across `docker compose restart backend`.
- [x] Frontend nginx proxies `/api/` incl. binary cover responses (no buffering
      weirdness); verify `GET /api/albums/1/cover` through :8080. Verified
      through the local override port **:8081** (8000/8080 are occupied on this
      host) — `GET http://localhost:8081/api/albums/3/cover` → 200 image/jpeg,
      136 KB, byte-identical to the direct `:8001` response.
- [x] `cp .env.example .env && docker compose up --build -d` brings everything up
      from a clean machine state; `docker compose ps` all healthy. Verified on
      this host with the gitignored override (ports 8001/8081); note that a
      literal copy of `.env.example` keeps the placeholder `JWT_SECRET` which the
      backend **refuses at startup by design** — README quickstart + troubleshooting
      document setting a strong secret (see Notes).

**CI** (`.github/workflows/ci.yml`, pattern from the reference)

- [x] `backend-tests` job: Postgres 16 service container, Python 3.12, pip cache
      on `requirements-dev.txt`, `pytest` in `backend/`.
- [x] `frontend-tests` job: Node 20, `npm ci`, `npm test`, `npm run build`.
- [x] `build-and-push` job on push to `main` only: buildx, GHCR login via
      `GITHUB_TOKEN`, push `backend` + `frontend` images tagged `latest` and
      `${{ github.sha }}`; `permissions: contents: read, packages: write`;
      concurrency group cancels superseded runs.
- [x] Local sanity: `act` optional — at minimum every command in the workflow is
      run and green locally/in compose. Verified: backend `pytest` → 172 passed
      against the compose Postgres service container (same setup as CI);
      frontend `npm ci` → `npm test` → 92 passed → `npm run build` green. GHCR
      push can only run on GitHub.

**Smoke test**

- [x] Script `scripts/smoke.sh` (or `make smoke`) that, against a running stack:
      asserts `/api/health`, registers+logs in, imports a known album (live
      provider call is OK here — it's outside CI), fetches cover bytes, sets a
      tag, logs a play, fetches recommendations, and greps the frontend shell at
      `:8080`. Document it; wire it as a manual/dispatch CI job only if it can
      stay deterministic (else leave it local-only and say so). Local-only by
      design (live APIs); documented in README; **16/16 checks passed** live.

**Docs**

- [x] README "First-time setup" verified end-to-end; architecture table; API
      pointer to `docs/PLAN.md`; development + testing sections accurate;
      troubleshooting note (ports in use, weak JWT secret refusal, provider rate
      limit).
- [x] Screenshots in `docs/screenshots/` (shelf, album detail, add flow, find,
      recommend) referenced from the README — capture from the running stack
      (browser or static render). Captured with **Playwright (chromium
      headless)** against the live stack at 1280 px; see Notes.
- [x] `.env.example` matches what compose actually requires. Verified: all
      `:?`-required vars (`POSTGRES_*`, `JWT_SECRET`, `INVITE_CODE`) present;
      `MUSICBRAINZ_CONTACT` optional (`:-`); no missing/extra keys.

## Notes

- **Ports 8000/8080 occupied on this machine:** 8000 was held by an unrelated
  `python3 -m http.server` and 8080 by the `cadvisor` monitoring container —
  do not kill either. Solution: a **gitignored**
  `docker-compose.override.yml` remaps **host ports only** (backend `8001:8000`,
  frontend `8081:80`) and is auto-merged by compose locally; the committed
  `docker-compose.yml` keeps the reference conventions 8000/8080. Compose on
  this host needs the `!override` merge directive (plain override entries
  *append* to `ports`; `!reset` is not supported by the installed compose).
  `.gitignore` gained `docker-compose.override.yml`.
- **Smoke-test approval path:** with a non-empty DB a new registration lands
  `pending` (no token). `scripts/smoke.sh` handles both cases: on a fresh DB the
  first user is an active admin and logs in directly; otherwise it takes
  `SMOKE_ADMIN_EMAIL/SMOKE_ADMIN_PASSWORD`, approves the smoke user via the
  admin `GET/PATCH /api/users` surface, then logs in. The admin-approval path
  was exercised live during the run.
- **Screenshot approach:** installed `playwright@1.64.0` (devDep only in a
  scratch dir under /tmp, **not** in the frontend package.json) + `npx
  playwright install chromium` (headless shell ~120 MB) and drove the real UI:
  login form → shelf → album detail → add search → find → recommend. Seeded a
  demo catalog (`shelf-demo@example.com` — a dev-only user, see env/DB) with 7
  live-imported albums, tags, backdated plays, and a note so the shelf/detail/
  recommend shots look real. Recommended (dusty) shot is filtered to a tag so
  every card shows the reason + "N days since spun" badge. PNGs verified
  programmatically (element waits + text assertions, not by eye).
- **`cp .env.example .env` alone won't boot the backend** — by design the
  lifespan refuses the placeholder `JWT_SECRET`s (`dev-secret-change-me`,
  `change-me`, `change-me-in-production`). The README quickstart says to set a
  strong secret and troubleshooting explains the refusal; no code change made.
- **No PLAN.md changes needed** — §5/§6 contract matches the shipped routers and
  `frontend/src/api.ts` (verified while writing docs).
- **Open items for the coordinator/user:** push a branch → PR so GitHub runs
  `backend-tests` / `frontend-tests`, then merge to `main` for the GHCR image
  push (needs `packages: write` — default GITHUB_TOKEN; no extra secrets).
  Consider refreshing screenshots after any future UI polish (#8). Dev DB now
  holds smoke/demo users + albums for future screenshot regeneration.
- **Command reference (this machine):** stack = `docker compose up -d` (override
  ports 8001/8081); smoke = `scripts/smoke.sh` with
  `VYNL_API_URL=http://localhost:8001/api VYNL_WEB_URL=http://localhost:8081`
  and the dev admin creds. Screenshot harness lives in /tmp (playwright),
  `docs/screenshots/` is committed.