#!/usr/bin/env bash
# vynl quickstart — guided first-time setup, and a one-command updater.
#
# First-time setup: creates .env from .env.example, fills in strong random
# secrets, prompts for the values only you can choose (invite code, contact
# email, Discogs token, host ports), then optionally builds and starts the
# stack with Docker Compose.
#
# Updating (--update): keeps the existing .env untouched, git pulls the latest
# code, rebuilds the images, and recreates the stack (DB migrations run on
# backend startup and are confirmed afterwards).
#
# Usage:
#   scripts/quickstart.sh [--yes] [--no-start]
#   scripts/quickstart.sh -u, --update [--no-pull] [--no-start] [--yes]
#
#   -y, --yes      accept the defaults for every prompt (no interaction)
#       --no-start quickstart: write .env but do NOT run docker compose;
#                  update: pull + build but do NOT restart the stack
#       --no-pull  update: don't git pull (use the code already on disk)
#   -u, --update   update an existing install (see above)
#   -h, --help     show this help
#
# Interactive by default. In a non-interactive shell (no TTY) the quickstart
# uses the defaults and does not start the stack unless --yes is given;
# `--update` carries out every step (each piece is skippable with --no-pull /
# --no-start, or by answering no to the per-step prompts).
#
# Requires: Docker with the Compose plugin. --update additionally uses curl
# only for the post-restart health check (skipped when curl is missing).
#
# Environment overrides (mostly for testing/automation):
#   QUICKSTART_ENV_FILE   path to the .env to write (default <repo>/.env)
#   QUICKSTART_FORCE      set to 1 to overwrite an existing .env without a backup
#   QUICKSTART_UPDATE_TIMEOUT
#                         seconds to wait for backend health before warning
#                         during --update (default 60)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${QUICKSTART_ENV_FILE:-$ROOT/.env}"
EXAMPLE_FILE="$ROOT/.env.example"
OVERRIDE_FILE="$ROOT/docker-compose.override.yml"

ASSUME_YES=0
NO_START=0
NO_PULL=0
UPDATE=0
INTERACTIVE=0
if [ -t 0 ]; then INTERACTIVE=1; fi

usage() {
  cat <<'EOF'
vynl quickstart — guided first-time setup and one-command updater.

First-time setup: creates .env from .env.example, fills in strong random
secrets, prompts for the values only you can choose (invite code, contact
email, Discogs token, host ports), then optionally builds + starts the stack.

Updating (--update): keeps the current .env, git pulls the latest code,
rebuilds the images, and recreates the stack (DB migrations run on backend
startup and are confirmed afterwards).

Usage:
  scripts/quickstart.sh [--yes] [--no-start]
  scripts/quickstart.sh -u|--update [--no-pull] [--no-start] [--yes]

  -y, --yes      accept the defaults for every prompt (no interaction)
      --no-start quickstart: write .env only; update: pull + build, no restart
      --no-pull  update: don't git pull
  -u, --update   update an existing install
  -h, --help     show this help

Interactive by default. In a non-interactive shell (no TTY) the quickstart
uses the defaults; --update carries out every step (skip pieces with
--no-pull / --no-start / answering no to the prompts).

Requires: Docker with the Compose plugin. --update uses curl when available
for the post-restart health check.
EOF
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    --no-start) NO_START=1 ;;
    --no-pull) NO_PULL=1 ;;
    -u|--update) UPDATE=1 ;;
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

# --- confirm_yes <question> <default: yes|no> ---------------------------------
# Returns 0 on yes. Non-interactive runs fall through to the given default;
# `--yes` always returns yes.
confirm_yes() {
  local q="$1" d="${2:-yes}" ans=""
  [ "$ASSUME_YES" = 1 ] && return 0
  if [ "$INTERACTIVE" = 1 ]; then
    local suffix="[y/N]"; [ "$d" = "yes" ] && suffix="[Y/n]"
    read -r -p "$q $suffix " ans || true
    case "$ans" in
      [yY]|[yY][eE][sS]) return 0 ;;
      [nN]|[nN][oO]) return 1 ;;
      *) [ "$d" = "yes" ] && return 0 || return 1 ;;
    esac
  fi
  [ "$d" = "yes" ] && return 0 || return 1
}

# --- update mode (--update): keep .env, pull, rebuild, restart, migrate -------
if [ "$UPDATE" = 1 ]; then
  head_ "vynl update"
  say "Updating an existing install. Your .env and data volumes are kept as-is."

  if ! command -v docker >/dev/null 2>&1; then
    say "ERROR: docker was not found on your PATH." >&2
    say "Install Docker (with the Compose plugin): https://docs.docker.com/engine/install/" >&2
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    say "ERROR: the 'docker compose' plugin was not found." >&2
    say "Install Docker Compose v2: https://docs.docker.com/compose/install/" >&2
    exit 1
  fi
  if [ ! -f "$ENV_FILE" ]; then
    say "ERROR: $ENV_FILE not found — run the quickstart first to create one." >&2
    exit 1
  fi
  api_port=""

  # --- pull -------------------------------------------------------------------
  if [ "$NO_PULL" = 1 ]; then
    note "Skipping 'git pull' (--no-pull)."
  elif [ ! -d "$ROOT/.git" ]; then
    note "This is not a git checkout of the repo — skipping 'git pull'."
  elif confirm_yes "Pull the latest changes from git?" yes; then
    head_ "Pulling latest changes"
    say "  git -C $(printf '%q' "$ROOT") pull --ff-only"
    if ! git -C "$ROOT" pull --ff-only; then
      say "ERROR: 'git pull' failed (check your remote/credentials or uncommitted"
      say "local changes). Resolve it, then re-run: scripts/quickstart.sh --update" >&2
      exit 1
    fi
  else
    note "Skipping 'git pull'."
  fi

  # --- build ------------------------------------------------------------------
  if confirm_yes "Rebuild the images (docker compose build --pull)?" yes; then
    head_ "Building images (this can take a few minutes)"
    ( cd "$ROOT" && docker compose build --pull )
  else
    note "Skipping the image build."
  fi

  # --- restart + migrations ---------------------------------------------------
  if [ "$NO_START" = 1 ]; then
    note "Leaving the stack as-is (--no-start)."
  elif confirm_yes "Restart the compose stack now?" yes; then
    head_ "Recreating the stack"
    ( cd "$ROOT" && docker compose up -d )

    healthy=0
    backend_id="$(cd "$ROOT" && docker compose ps -q backend 2>/dev/null | head -1 || true)"
    if [ -n "$backend_id" ]; then
      api_port="$(docker port "$backend_id" 8000/tcp 2>/dev/null | sed -n 's/.*://p' | head -1 || true)"
    fi
    if [ -n "$api_port" ] && command -v curl >/dev/null 2>&1; then
      head_ "Waiting for the backend (migrations run on startup)"
      deadline=$((SECONDS + ${QUICKSTART_UPDATE_TIMEOUT:-60}))
      while [ "$SECONDS" -lt "$deadline" ]; do
        if curl -fsS "http://localhost:$api_port/api/health" 2>/dev/null | grep -q '"ok"'; then
          healthy=1; break
        fi
        sleep 2
      done
      if [ "$healthy" = 1 ]; then
        say "Backend healthy at http://localhost:$api_port/api/health"
      else
        say "WARNING: backend did not answer /api/health within ${QUICKSTART_UPDATE_TIMEOUT:-60}s." >&2
        say "         Check: docker compose logs backend" >&2
      fi
    fi

    if [ "$healthy" = 1 ]; then
      head_ "Confirming database migrations"
      if ( cd "$ROOT" && docker compose exec -T backend alembic upgrade head ); then
        say "Database is at the latest migration head."
      else
        say "WARNING: could not confirm the migration head (see: docker compose logs backend)." >&2
      fi
    fi

    head_ "Stack status"
    ( cd "$ROOT" && docker compose ps )
  else
    note "Skipping the restart."
  fi

  head_ "Update complete"
  say "  Status:  docker compose ps"
  if [ -n "$api_port" ]; then
    say "  Health:  curl http://localhost:$api_port/api/health"
  fi
  say "  Logs:    docker compose logs -f backend"
  say ""
  say "If the update changed .env.example, review it for new optional config keys"
  say "and add any you want to customize to .env, then: docker compose up -d"
  exit 0
fi

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
