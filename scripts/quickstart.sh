#!/usr/bin/env bash
# vynl quickstart — guided first-time setup.
#
# Creates .env from .env.example, fills in strong random secrets, prompts for
# the values only you can choose (invite code, contact email, Discogs token,
# host ports), then optionally builds and starts the stack with Docker Compose.
#
# Usage:
#   scripts/quickstart.sh [--yes] [--no-start]
#
#   -y, --yes     accept the defaults for every prompt (no interaction)
#       --no-start  write .env but do NOT run docker compose
#   -h, --help     show this help
#
# Interactive by default. In a non-interactive shell (no TTY) it uses the
# defaults and does not start the stack unless --yes is given.
#
# Requires: Docker with the Compose plugin.
#
# Environment overrides (mostly for testing/automation):
#   QUICKSTART_ENV_FILE   path to the .env to write (default <repo>/.env)
#   QUICKSTART_FORCE      set to 1 to overwrite an existing .env without a backup

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${QUICKSTART_ENV_FILE:-$ROOT/.env}"
EXAMPLE_FILE="$ROOT/.env.example"
OVERRIDE_FILE="$ROOT/docker-compose.override.yml"

ASSUME_YES=0
NO_START=0
INTERACTIVE=0
if [ -t 0 ]; then INTERACTIVE=1; fi

usage() {
  cat <<'EOF'
vynl quickstart — guided first-time setup.

Creates .env from .env.example, fills in strong random secrets, prompts for the
values only you can choose (invite code, contact email, Discogs token, host
ports), then optionally builds and starts the stack with Docker Compose.

Usage:
  scripts/quickstart.sh [--yes] [--no-start]

  -y, --yes      accept the defaults for every prompt (no interaction)
      --no-start write .env but do NOT run docker compose
  -h, --help     show this help

Interactive by default. In a non-interactive shell (no TTY) it uses the
defaults and does not start the stack unless --yes is given.

Requires: Docker with the Compose plugin.
EOF
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    --no-start) NO_START=1 ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

# --- pretty output -----------------------------------------------------------
if [ -t 1 ]; then BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'; else BOLD=""; DIM=""; RESET=""; fi
say()  { printf '%s\n' "$*"; }
head_() { printf '\n%s%s%s\n' "$BOLD" "$*" "$RESET"; }
note() { printf '%s%s%s\n' "$DIM" "$*" "$RESET"; }

# --- random values (openssl → python3 → /dev/urandom) ------------------------
rand_hex() { # rand_hex <bytes>
  local n="${1:-32}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$n"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import secrets,sys; sys.stdout.write(secrets.token_hex($n))"
  else
    head -c "$((n * 2))" /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

# --- prompt <varname> <question> <default> -----------------------------------
prompt() {
  local __var="$1" __q="$2" __d="${3:-}" __a=""
  if [ "$INTERACTIVE" = 1 ] && [ "$ASSUME_YES" = 0 ]; then
    if [ -n "$__d" ]; then
      read -r -p "$__q [$__d]: " __a || true
    else
      read -r -p "$__q: " __a || true
    fi
  fi
  [ -z "$__a" ] && __a="$__d"
  printf -v "$__var" '%s' "$__a"
}

# --- set_var <key> <value>: replace the key's line in .env -------------------
set_var() {
  local key="$1" value="$2" escaped
  escaped="$(printf '%s' "$value" | sed 's/\\/\\\\/g')"
  awk -v k="$key" -v v="$escaped" '
    index($0, k "=") == 1 { print k "=" v; next }
    { print }
  ' "$ENV_FILE" > "$ENV_FILE.tmp"
  mv "$ENV_FILE.tmp" "$ENV_FILE"
}

# --- prerequisites -----------------------------------------------------------
head_ "vynl quickstart"
say "This sets up a .env with secure random secrets, walks you through the"
say "optional settings, and can build + start the stack with Docker Compose."

if ! command -v docker >/dev/null 2>&1; then
  say ""
  say "ERROR: docker was not found on your PATH." >&2
  say "Install Docker (with the Compose plugin): https://docs.docker.com/engine/install/" >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  say ""
  say "ERROR: the 'docker compose' plugin was not found." >&2
  say "Install Docker Compose v2: https://docs.docker.com/compose/install/" >&2
  exit 1
fi

if [ ! -f "$EXAMPLE_FILE" ]; then
  say "ERROR: $EXAMPLE_FILE not found — run this from inside the vynl repo." >&2
  exit 1
fi

# --- existing .env -----------------------------------------------------------
if [ -f "$ENV_FILE" ] && [ "${QUICKSTART_FORCE:-0}" != "1" ]; then
  backup="$ENV_FILE.bak.$(date +%Y%m%d%H%M%S)"
  proceed=0
  if [ "$ASSUME_YES" = 1 ]; then
    proceed=1
  elif [ "$INTERACTIVE" = 1 ]; then
    say ""
    read -r -p "An .env already exists ($ENV_FILE). Overwrite it (a backup is kept)? [y/N]: " ans || true
    case "$ans" in [yY]|[yY][eE][sS]) proceed=1 ;; esac
  fi
  if [ "$proceed" != 1 ]; then
    say "Keeping the existing .env. Nothing changed."
    exit 0
  fi
  cp "$ENV_FILE" "$backup"
  note "Backed up existing .env → $backup"
fi

# --- values ------------------------------------------------------------------
head_ "Secrets (generated automatically)"
POSTGRES_PASSWORD="$(rand_hex 24)"
JWT_SECRET="$(rand_hex 32)"
say "  POSTGRES_PASSWORD  ${POSTGRES_PASSWORD:0:6}…  (random, 48 hex chars)"
say "  JWT_SECRET         ${JWT_SECRET:0:6}…  (random, 64 hex chars)"

head_ "Your settings"
prompt INVITE_CODE "Registration invite code (share only with people you trust)" "$(rand_hex 8)"
prompt MUSICBRAINZ_CONTACT "Contact email for MusicBrainz requests (strongly recommended)" ""
prompt ITUNES_COUNTRIES "iTunes storefronts to search (comma-separated, order = query order)" "US,JP,GB"

say ""
note "Discogs is optional and disabled until you add a token."
note "To get one:"
note "  1. Sign in at https://www.discogs.com"
note "  2. Go to https://www.discogs.com/settings/developers"
note "  3. Click \"Generate new token\" and copy it"
note "  (or: Settings → Developers → Generate new token)"
prompt DISCOGS_TOKEN "Discogs personal access token (blank disables Discogs)" ""

head_ "Host ports"
say "The app is served on the frontend port; the backend also publishes a port."
say "If 8080/8000 are already taken on this machine, pick others here."
prompt FRONTEND_PORT "Frontend (web UI) host port" "8080"
prompt BACKEND_PORT "Backend (API) host port" "8000"

# --- write .env --------------------------------------------------------------
cp "$EXAMPLE_FILE" "$ENV_FILE"
set_var POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
set_var JWT_SECRET "$JWT_SECRET"
set_var INVITE_CODE "$INVITE_CODE"
set_var MUSICBRAINZ_CONTACT "$MUSICBRAINZ_CONTACT"
set_var ITUNES_COUNTRIES "$ITUNES_COUNTRIES"
set_var DISCOGS_TOKEN "$DISCOGS_TOKEN"
note "Wrote $ENV_FILE (from .env.example)"

if [ "$FRONTEND_PORT" != "8080" ] || [ "$BACKEND_PORT" != "8000" ]; then
  if [ -f "$OVERRIDE_FILE" ]; then
    cp "$OVERRIDE_FILE" "$OVERRIDE_FILE.bak.$(date +%Y%m%d%H%M%S)"
  fi
  cat > "$OVERRIDE_FILE" <<YAML
# Generated by scripts/quickstart.sh (host-port remap only).
services:
  backend:
    ports: !override
      - "$BACKEND_PORT:8000"
  frontend:
    ports: !override
      - "$FRONTEND_PORT:80"
YAML
  note "Wrote $OVERRIDE_FILE (frontend :$FRONTEND_PORT, backend :$BACKEND_PORT)"
elif [ -f "$OVERRIDE_FILE" ]; then
  note "Note: an existing docker-compose.override.yml is still in effect."
fi

# --- summary -----------------------------------------------------------------
head_ "Ready"
say "  Web UI:      http://localhost:$FRONTEND_PORT"
say "  API:         http://localhost:$BACKEND_PORT/api"
say "  Invite code: $INVITE_CODE"
if [ -n "$MUSICBRAINZ_CONTACT" ]; then
  say "  MB contact:  $MUSICBRAINZ_CONTACT"
else
  say ""
  say "  ⚠ No MusicBrainz contact set — provider requests may be throttled."
  say "    Add MUSICBRAINZ_CONTACT=<you@example.com> to .env later if needed."
fi
say ""
say "First account you register becomes the admin; later signups need approval"
say "from Settings → Manage users."

# --- start? ------------------------------------------------------------------
start=0
if [ "$NO_START" = 1 ]; then
  start=0
elif [ "$ASSUME_YES" = 1 ]; then
  start=1
elif [ "$INTERACTIVE" = 1 ]; then
  read -r -p $'\nBuild and start the stack now? [Y/n]: ' ans || true
  case "$ans" in [nN]|[nN][oO]) start=0 ;; *) start=1 ;; esac
fi

if [ "$start" = 1 ]; then
  head_ "Building and starting (this can take a few minutes the first time)"
  ( cd "$ROOT" && docker compose up --build -d )
  head_ "Done"
  say "Check status:   docker compose ps"
  say "Health:         curl http://localhost:$BACKEND_PORT/api/health"
  say "Open the app:   http://localhost:$FRONTEND_PORT"
else
  head_ "Next step"
  say "  cd $(printf '%q' "$ROOT") && docker compose up --build -d"
fi
