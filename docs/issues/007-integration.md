# #7: Integration — compose hardening, CI, README, smoke test, screenshots

- **Status:** open
- **Assignee:** unassigned
- **Labels:** infra, ci, docs
- **Depends on:** #3, #5, #6 (all features landed)
- **Wave:** 5

## Summary

Take the assembled app from "works in dev" to "one command in production": finalize
Docker Compose, add the GitHub Actions CI (tests + GHCR image builds), run a real
`docker compose up` smoke test, and finish the README with screenshots.

## Acceptance criteria

**Compose**

- [ ] `docker-compose.yml` matches PLAN §8: three services, `db_data` +
      `covers_data` volumes, healthcheck-gated backend start, `restart:
      unless-stopped`, ports 5432/8000/8080, env from `.env` with `:?` required
      guards for `JWT_SECRET`/`INVITE_CODE`, `COVERS_DIR=/app/covers` volume
      mounted, `MUSICBRAINZ_CONTACT` passed through.
- [ ] Backend `Dockerfile` copies `covers/` dir creation (or create at startup);
      artwork survives container recreation (verify volume write).
- [ ] Frontend nginx proxies `/api/` incl. binary cover responses (no buffering
      weirdness); verify `GET /api/albums/1/cover` through :8080.
- [ ] `cp .env.example .env && docker compose up --build -d` brings everything up
      from a clean machine state; `docker compose ps` all healthy.

**CI** (`.github/workflows/ci.yml`, pattern from the reference)

- [ ] `backend-tests` job: Postgres 16 service container, Python 3.12, pip cache
      on `requirements-dev.txt`, `pytest` in `backend/`.
- [ ] `frontend-tests` job: Node 20, `npm ci`, `npm test`, `npm run build`.
- [ ] `build-and-push` job on push to `main` only: buildx, GHCR login via
      `GITHUB_TOKEN`, push `backend` + `frontend` images tagged `latest` and
      `${{ github.sha }}`; `permissions: contents: read, packages: write`;
      concurrency group cancels superseded runs.
- [ ] Local sanity: `act` optional — at minimum every command in the workflow is
      run and green locally/in compose.

**Smoke test**

- [ ] Script `scripts/smoke.sh` (or `make smoke`) that, against a running stack:
      asserts `/api/health`, registers+logs in, imports a known album (live
      provider call is OK here — it's outside CI), fetches cover bytes, sets a
      tag, logs a play, fetches recommendations, and greps the frontend shell at
      `:8080`. Document it; wire it as a manual/dispatch CI job only if it can
      stay deterministic (else leave it local-only and say so).

**Docs**

- [ ] README "First-time setup" verified end-to-end; architecture table; API
      pointer to `docs/PLAN.md`; development + testing sections accurate;
      troubleshooting note (ports in use, weak JWT secret refusal, provider rate
      limit).
- [ ] Screenshots in `docs/screenshots/` (shelf, album detail, add flow, find,
      recommend) referenced from the README — capture from the running stack
      (browser or static render).
- [ ] `.env.example` matches what compose actually requires.

## Notes

- Baseline compose was committed with the plan — harden, don't rewrite.
- Reference CI: `baby-tracking-app/.github/workflows/ci.yml` — copy structure,
  rename services (`vynl-*`), swap test dirs.
- If any feature needed a contract change, PLAN.md was updated by its issue —
  re-read it before writing docs.
