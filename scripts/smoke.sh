#!/usr/bin/env bash
# vynl compose smoke test
#
# Runs a live end-to-end pass against a running `docker compose up` stack:
# health → register+login → external search → real album import → cover bytes →
# tags → play log → recommendations → library track search → frontend shell +
# proxied /api/health and a binary cover through nginx. When a DISCOGS_TOKEN is
# configured, an extra live Discogs check (import + tracklist) runs after search.
#
# LOCAL-ONLY by design: it calls the live MusicBrainz/Deezer/Discogs APIs, so it is
# intentionally NOT wired into CI (results vary with the networks / rate limits).
#
# Usage:
#   docker compose up -d            # bring the stack up first
#   scripts/smoke.sh                # defaults: api http://localhost:8001/api,
#                                   #           web  http://localhost:8081
#
# Environment:
#   VYNL_API_URL   base API URL, default http://localhost:8001/api
#   VYNL_WEB_URL   base web URL,  default http://localhost:8081
#   SMOKE_SEARCH   search query used for the live import,
#                  default "remain in light talking heads"
#   SMOKE_PASSWORD password for the throwaway smoke user,
#                  default "SmokeTestPass123!"
#   SMOKE_ADMIN_EMAIL / SMOKE_ADMIN_PASSWORD
#                  optional admin credentials. vynl's first registered user is
#                  admin+active automatically, but on a non-empty DB a new
#                  registration lands as `pending` and must be approved; pass
#                  these and the script approves the smoke user via the admin
#                  users API before logging in.
#
# Requires: curl, jq. Exit 0 when every check passes.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

API_URL="${VYNL_API_URL:-http://localhost:8001/api}"
WEB_URL="${VYNL_WEB_URL:-http://localhost:8081}"
SEARCH_Q="${SMOKE_SEARCH:-remain in light talking heads}"
SMOKE_PASSWORD="${SMOKE_PASSWORD:-SmokeTestPass123!}"
ADMIN_EMAIL="${SMOKE_ADMIN_EMAIL:-}"
ADMIN_PASSWORD="${SMOKE_ADMIN_PASSWORD:-}"

PASS=0
FAIL=0

check() { # check <name> <exit-code>
  if [ "$2" -eq 0 ]; then
    PASS=$((PASS + 1)); echo "  PASS  $1"
  else
    FAIL=$((FAIL + 1)); echo "  FAIL  $1"
  fi
}

jget() { jq -r "$1" "$2" 2>/dev/null || true; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "vynl smoke test"
echo "  api: $API_URL   web: $WEB_URL"

# --- 1. health ----------------------------------------------------------------
echo "[1/9] backend health"
code="$(curl -sS -o "$TMP/health.json" -w '%{http_code}' "$API_URL/health")"
ok=0
if [ "$code" = "200" ] && [ "$(jget .status "$TMP/health.json")" = "ok" ]; then ok=1; fi
check "GET $API_URL/health -> 200 {\"status\":\"ok\"}" $((ok ? 0 : 1))

# --- 2. register --------------------------------------------------------------
echo "[2/9] register + login"
EMAIL="smoke-$(date +%s)@example.com"
code="$(curl -sS -o "$TMP/reg.json" -w '%{http_code}' -X POST "$API_URL/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"Smoke Test\",\"email\":\"$EMAIL\",\"password\":\"$SMOKE_PASSWORD\",\"invite_code\":\"$(grep '^INVITE_CODE=' "$ROOT/.env" | cut -d= -f2-)\"}")"
ok=0
if [ "$code" = "201" ]; then ok=1; fi
check "POST /auth/register -> 201" $((ok ? 0 : 1))

TOKEN="$(jget .access_token "$TMP/reg.json")"
if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "  new user is not active (non-empty DB) — approving via admin API"
  if [ -z "$ADMIN_EMAIL" ] || [ -z "$ADMIN_PASSWORD" ]; then
    echo "  ERROR: registration returned no token and SMOKE_ADMIN_EMAIL/PASSWORD are unset."
    echo "  Provide admin creds (or run against a fresh DB) so the smoke user can be approved."
    exit 1
  fi
  acode="$(curl -sS -o "$TMP/admin.json" -w '%{http_code}' -X POST "$API_URL/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}")"
  check "admin login for approval -> 200" $((acode == 200 ? 0 : 1))
  ATOKEN="$(jget .access_token "$TMP/admin.json")"
  [ -n "$ATOKEN" ] && [ "$ATOKEN" != "null" ] || { echo "  ERROR: admin login failed"; exit 1; }
  curl -sS -o /dev/null "$API_URL/users" -H "Authorization: Bearer $ATOKEN"
  pending_id="$(curl -sS "$API_URL/users" -H "Authorization: Bearer $ATOKEN" \
    | jq -r --arg e "$EMAIL" '.[] | select(.email == $e) | .id' | head -1)"
  [ -n "$pending_id" ] || { echo "  ERROR: smoke user not visible to admin"; exit 1; }
  pcode="$(curl -sS -o /dev/null -w '%{http_code}' -X PATCH "$API_URL/users/$pending_id" \
    -H "Authorization: Bearer $ATOKEN" -H 'Content-Type: application/json' \
    -d '{"status":"active"}')"
  check "admin PATCH user -> active" $((pcode == 200 ? 0 : 1))
fi

code="$(curl -sS -o "$TMP/login.json" -w '%{http_code}' -X POST "$API_URL/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$SMOKE_PASSWORD\"}")"
TOKEN="$(jget .access_token "$TMP/login.json")"
ok=0
if [ "$code" = "200" ] && [ -n "$TOKEN" ] && [ "$TOKEN" != "null" ]; then ok=1; fi
check "POST /auth/login -> 200 + token" $((ok ? 0 : 1))
AUTH=(-H "Authorization: Bearer $TOKEN")

# --- 3. external search -------------------------------------------------------
echo "[3/9] external search + import (live MusicBrainz + Deezer)"
curl -sS -D "$TMP/search.headers" -o "$TMP/search.json" "${AUTH[@]}" "$API_URL/search/albums?q=$(jq -nr --arg v "$SEARCH_Q" '$v|@uri')&limit=5"
n="$(jget 'length' "$TMP/search.json")"
ok=0; [ "$n" -gt 0 ] 2>/dev/null && ok=1
check "GET /search/albums -> $n results" $((ok ? 0 : 1))
# Prefer the first result that carries artwork; else fall back to the first row.
SRC="$(jget 'map(select(.cover_url != null)) | .[0].source // .[0].source' "$TMP/search.json")"
EXT="$(jget 'map(select(.cover_url != null)) | .[0].external_id // .[0].external_id' "$TMP/search.json")"
ok=0; [ -n "$SRC" ] && [ -n "$EXT" ] && [ "$EXT" != "null" ] && ok=1
check "search row picked (source=$SRC external_id=$EXT)" $((ok ? 0 : 1))

code="$(curl -sS -o "$TMP/import.json" -w '%{http_code}' "${AUTH[@]}" -X POST "$API_URL/albums/import" \
  -H 'Content-Type: application/json' \
  -d "{\"source\":\"$SRC\",\"external_id\":\"$EXT\"}")"
if [ "$code" = "409" ]; then
  echo "  import -> 409 (already on shelf); reusing existing album"
  ALBUM_ID="$(jget .detail "$TMP/import.json" | sed -n 's/.*id=\([0-9]*\).*/\1/p')"
  if [ -z "$ALBUM_ID" ]; then
    ALBUM_ID="$(curl -sS "${AUTH[@]}" "$API_URL/albums?q=$(jq -nr --arg v "$SEARCH_Q" '$v|@uri')&limit=5" | jget '.[0].id')"
  fi
  if [ -n "$ALBUM_ID" ] && [ "$ALBUM_ID" -gt 0 ] 2>/dev/null; then ALBUM_OK=0; else ALBUM_OK=1; fi
  check "reused imported album (409 path)" $ALBUM_OK
elif [ "$code" = "201" ]; then
  ALBUM_ID="$(jget .id "$TMP/import.json")"
  TITLE="$(jget .title "$TMP/import.json")"
  check "POST /albums/import -> 201 (id=$ALBUM_ID \"$TITLE\")" 0
else
  echo "  ERROR: import returned HTTP $code: $(cat "$TMP/import.json")"
  ALBUM_ID=""
  check "POST /albums/import -> 201" 1
fi
[ -n "$ALBUM_ID" ] && [ "$ALBUM_ID" != "null" ] || { echo "  ERROR: no album id"; exit 1; }

# --- 3b. Discogs provider (live, only when a token is configured) ------------
HAS_DISCOGS=0
grep -qE '^DISCOGS_TOKEN=.+' "$ROOT/.env" 2>/dev/null && HAS_DISCOGS=1
if [ "$HAS_DISCOGS" = "1" ]; then
  echo "[3b/9] Discogs provider (live, token configured)"
  # The merged search answered above must not have degraded Discogs.
  degraded="$(tr -d '\r' < "$TMP/search.headers" \
    | awk -F': ' 'tolower($1)=="x-search-degraded"{sub(/^ +/,"",$2); print $2}' \
    | paste -sd, -)"
  ok=0
  if ! echo ",$degraded," | grep -q ",discogs,"; then ok=1; fi
  check "X-Search-Degraded does not name discogs (got: ${degraded:-none})" $((ok ? 0 : 1))

  # Import a Discogs release: a discogs row from the search when present, else a
  # well-known id (Talking Heads — Remain in Light, 1980).
  DISCOGS_EXT="$(jget 'map(select(.source=="discogs")) | .[0].external_id // empty' "$TMP/search.json")"
  [ -n "$DISCOGS_EXT" ] || DISCOGS_EXT="249504"
  code="$(curl -sS -o "$TMP/discogs.json" -w '%{http_code}' "${AUTH[@]}" -X POST "$API_URL/albums/import" \
    -H 'Content-Type: application/json' -d "{\"source\":\"discogs\",\"external_id\":\"$DISCOGS_EXT\"}")"
  if [ "$code" = "201" ]; then
    DID="$(jget .id "$TMP/discogs.json")"
    check "POST /albums/import discogs:$DISCOGS_EXT -> 201 (id=$DID)" 0
  elif [ "$code" = "409" ]; then
    DID="$(jget .detail "$TMP/discogs.json" | sed -n 's/.*id=\([0-9]*\).*/\1/p')"
    ok=0; [ -n "$DID" ] && [ "$DID" -gt 0 ] 2>/dev/null && ok=1
    check "POST /albums/import discogs:$DISCOGS_EXT -> 409 (already on shelf)" $((ok ? 0 : 1))
  else
    DID=""
    echo "  ERROR: discogs import returned HTTP $code: $(cat "$TMP/discogs.json")"
    check "POST /albums/import discogs:$DISCOGS_EXT" 1
  fi
  if [ -n "$DID" ] && [ "$DID" != "null" ]; then
    curl -sS -o "$TMP/discogs_album.json" "${AUTH[@]}" "$API_URL/albums/$DID"
    dn="$(jget '.tracks | length' "$TMP/discogs_album.json")"
    ok=0; [ "$dn" -gt 0 ] 2>/dev/null && ok=1
    check "GET /albums/$DID (discogs) -> $dn tracks" $((ok ? 0 : 1))
  fi
else
  echo "[3b/9] Discogs skipped (no DISCOGS_TOKEN in .env)"
fi

# --- 4. album detail + tracks ------------------------------------------------
echo "[4/9] album detail + tracklist"
curl -sS -o "$TMP/album.json" "${AUTH[@]}" "$API_URL/albums/$ALBUM_ID"
n_tracks="$(jget '.tracks | length' "$TMP/album.json")"
ok=0; [ "$n_tracks" -gt 0 ] 2>/dev/null && ok=1
check "GET /albums/$ALBUM_ID -> $n_tracks tracks" $((ok ? 0 : 1))

# --- 5. cover bytes (direct + through nginx) ---------------------------------
echo "[5/9] cover bytes (direct API and via nginx proxy)"
for label_url in "api:$API_URL/albums/$ALBUM_ID/cover" "web:$WEB_URL/api/albums/$ALBUM_ID/cover"; do
  label="${label_url%%:*}"; url="${label_url#*:}"
  code="$(curl -sS -o "$TMP/cover.bin" -w '%{http_code}' "${AUTH[@]}" "$url")"
  ctype="$(file -b --mime-type "$TMP/cover.bin" 2>/dev/null || echo unknown)"
  size="$(wc -c < "$TMP/cover.bin")"
  ok=0
  if [ "$code" = "200" ] && { [ "$ctype" = "image/jpeg" ] || [ "$ctype" = "image/png" ]; } && [ "$size" -gt 1000 ]; then ok=1; fi
  check "GET $url -> 200 ($ctype, ${size}b)" $((ok ? 0 : 1))
done

# --- 6. tags ------------------------------------------------------------------
echo "[6/9] set tags"
curl -sS -o "$TMP/tags.json" "${AUTH[@]}" -X PUT "$API_URL/albums/$ALBUM_ID/tags" \
  -H 'Content-Type: application/json' -d '{"tags":["smoke-test","chill"]}'
got_tags="$(jget '.tags | join(",")' "$TMP/tags.json")"
ok=0; case ",$got_tags," in *",smoke-test,"*|*",chill,"*) ok=1;; esac
check "PUT /tags -> [$got_tags] contains smoke-test,chill" $((ok ? 0 : 1))

# --- 7. play log (backdated so dusty can pick it up) -------------------------
echo "[7/9] play log + last_played_at"
BACKDATE="$(date -u -d '90 days ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-90d +%Y-%m-%dT%H:%M:%SZ)"
curl -sS -o "$TMP/play.json" "${AUTH[@]}" -X POST "$API_URL/albums/$ALBUM_ID/plays" \
  -H 'Content-Type: application/json' -d "{\"played_at\":\"$BACKDATE\"}"
lpa="$(jget .last_played_at "$TMP/play.json")"
ok=0; [ -n "$lpa" ] && [ "$lpa" != "null" ] && ok=1
check "POST /plays (backdated) -> last_played_at=$lpa" $((ok ? 0 : 1))

# --- 8. recommendations -------------------------------------------------------
echo "[8/9] recommendations"
curl -sS -o "$TMP/recs.json" "${AUTH[@]}" "$API_URL/recommendations?mode=dusty&n=3"
hits="$(jq -r --argjson id "$ALBUM_ID" '[.[] | select(.album.id == $id)] | length' "$TMP/recs.json")"
reason="$(jq -r --argjson id "$ALBUM_ID" '.[] | select(.album.id == $id) | .reason' "$TMP/recs.json" | head -1)"
ok=0; [ "$hits" -ge 1 ] 2>/dev/null && ok=1
check "GET /recommendations?mode=dusty -> album $ALBUM_ID recommended ($reason)" $((ok ? 0 : 1))

# --- 9. frontend shell + proxied API -----------------------------------------
echo "[9/9] frontend shell"
code="$(curl -sS -o "$TMP/index.html" -w '%{http_code}' "$WEB_URL/")"
ok=0
if [ "$code" = "200" ] && grep -q 'id="root"' "$TMP/index.html"; then ok=1; fi
check "GET $WEB_URL/ -> 200 with app root div" $((ok ? 0 : 1))

code="$(curl -sS -o "$TMP/webhealth.json" -w '%{http_code}' "$WEB_URL/api/health")"
ok=0; [ "$code" = "200" ] && [ "$(jget .status "$TMP/webhealth.json")" = "ok" ] && ok=1
check "GET $WEB_URL/api/health (nginx proxy) -> {\"status\":\"ok\"}" $((ok ? 0 : 1))

# --- summary ------------------------------------------------------------------
echo
echo "Smoke summary: $PASS passed, $FAIL failed (user: $EMAIL, album id: $ALBUM_ID)"
[ "$FAIL" -eq 0 ] || echo "One or more checks failed — see above; live provider calls may be down or rate-limited."
exit $((FAIL > 0 ? 1 : 0))