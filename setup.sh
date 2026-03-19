#!/usr/bin/env bash
# setup.sh — Prerequisite validation and stack startup for chronovista
# Usage: ./setup.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Colour helpers (degrade gracefully when not a TTY)
# ---------------------------------------------------------------------------
if [ -t 1 ]; then
  RED='\033[0;31m'
  YELLOW='\033[1;33m'
  GREEN='\033[0;32m'
  BOLD='\033[1m'
  RESET='\033[0m'
else
  RED='' YELLOW='' GREEN='' BOLD='' RESET=''
fi

ok()   { printf "${GREEN}[OK]${RESET}   %s\n" "$*"; }
warn() { printf "${YELLOW}[WARN]${RESET} %s\n" "$*"; }
err()  { printf "${RED}[ERR]${RESET}  %s\n" "$*" >&2; }
die()  { err "$1"; shift; for line in "$@"; do printf "       %s\n" "$line" >&2; done; exit 1; }
info() { printf "       %s\n" "$*"; }

# ---------------------------------------------------------------------------
# 1. Docker installed
# ---------------------------------------------------------------------------
if ! command -v docker &>/dev/null; then
  die "Docker is not installed." \
      "Install Docker Desktop from https://www.docker.com/products/docker-desktop/" \
      "or follow the engine install guide at https://docs.docker.com/engine/install/"
fi

DOCKER_VERSION=$(docker --version 2>/dev/null | head -n1)
ok "Docker is installed (${DOCKER_VERSION})"

# ---------------------------------------------------------------------------
# 2. Docker Compose available (plugin or standalone)
# ---------------------------------------------------------------------------
if ! docker compose version &>/dev/null 2>&1; then
  die "Docker Compose is not available." \
      "Docker Compose v2 ships bundled with Docker Desktop." \
      "If using Docker Engine, install the Compose plugin:" \
      "  https://docs.docker.com/compose/install/linux/"
fi

ok "Docker Compose is available"

# ---------------------------------------------------------------------------
# 3. Docker daemon is running
# ---------------------------------------------------------------------------
if ! docker info >/dev/null 2>&1; then
  die "Docker daemon is not running." \
      "Start Docker Desktop, or on Linux run: sudo systemctl start docker"
fi

ok "Docker daemon is running"

# ---------------------------------------------------------------------------
# 4. .env file exists
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

if [ ! -f "${ENV_FILE}" ]; then
  die ".env file not found at repo root." \
      "Copy the example file and fill in your credentials:" \
      "  cp .env.example .env" \
      "  # then edit .env and set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET"
fi

ok ".env file found"

# ---------------------------------------------------------------------------
# 5. OAuth credentials are populated (not empty and not placeholder values)
# ---------------------------------------------------------------------------
# Source only the specific vars we care about — avoid executing arbitrary code.
_CLIENT_ID=$(grep -E '^YOUTUBE_CLIENT_ID=' "${ENV_FILE}" | head -n1 | cut -d'=' -f2- | tr -d '[:space:]')
_CLIENT_SECRET=$(grep -E '^YOUTUBE_CLIENT_SECRET=' "${ENV_FILE}" | head -n1 | cut -d'=' -f2- | tr -d '[:space:]')

_PLACEHOLDER_PATTERN="^(your_.*|<.*>|CHANGE_ME|changeme|todo|TODO|placeholder|)$"

if [[ -z "${_CLIENT_ID}" || "${_CLIENT_ID}" =~ ${_PLACEHOLDER_PATTERN} ]]; then
  die "YOUTUBE_CLIENT_ID in .env is empty or still a placeholder." \
      "Create OAuth 2.0 credentials at https://console.cloud.google.com/" \
      "  1. Go to APIs & Services > Credentials" \
      "  2. Create credentials > OAuth client ID > Desktop App" \
      "  3. Copy the Client ID and Client Secret into .env"
fi

if [[ -z "${_CLIENT_SECRET}" || "${_CLIENT_SECRET}" =~ ${_PLACEHOLDER_PATTERN} ]]; then
  die "YOUTUBE_CLIENT_SECRET in .env is empty or still a placeholder." \
      "Create OAuth 2.0 credentials at https://console.cloud.google.com/" \
      "  1. Go to APIs & Services > Credentials" \
      "  2. Create credentials > OAuth client ID > Desktop App" \
      "  3. Copy the Client ID and Client Secret into .env"
fi

ok "OAuth credentials configured"

# ---------------------------------------------------------------------------
# 6. (Optional / non-blocking) OAuth token warning
# ---------------------------------------------------------------------------
DATA_DIR="${SCRIPT_DIR}/data"
TOKEN_FILE="${DATA_DIR}/youtube_token.json"

if [ ! -f "${TOKEN_FILE}" ]; then
  warn "No OAuth token found at ./data/youtube_token.json"
  printf "\n"
  printf "  ${BOLD}To authenticate with YouTube, follow these steps:${RESET}\n"
  printf "\n"
  printf "  ${BOLD}Step 1${RESET}  Run the login command on your host machine (not inside Docker):\n"
  printf "\n"
  printf "            poetry run chronovista auth login\n"
  printf "\n"
  printf "  ${BOLD}Step 2${RESET}  A browser window will open to Google's OAuth consent screen.\n"
  printf "          Sign in with the Google account that owns your YouTube data.\n"
  printf "\n"
  printf "  ${BOLD}Step 3${RESET}  After granting access, the token is saved to:\n"
  printf "\n"
  printf "            ./data/youtube_token.json\n"
  printf "\n"
  printf "          This file is bind-mounted into the container automatically.\n"
  printf "          You only need to authenticate once — the token persists across\n"
  printf "          container restarts and rebuilds.\n"
  printf "\n"
  printf "  ${BOLD}Re-authentication${RESET}  If the token expires or is revoked by Google,\n"
  printf "          re-run ${BOLD}poetry run chronovista auth login${RESET} to refresh it.\n"
  printf "          Token expiry typically occurs after 7 days for apps in testing mode,\n"
  printf "          or when you revoke access at https://myaccount.google.com/permissions\n"
  printf "\n"
  printf "  ${YELLOW}Setup will continue. Some features will be unavailable until you authenticate.${RESET}\n"
  printf "\n"
fi

# ---------------------------------------------------------------------------
# 7. Build the Docker image
# ---------------------------------------------------------------------------
printf "${BOLD}Building chronovista image...${RESET}\n"
docker compose build

# ---------------------------------------------------------------------------
# 8. Start the stack
# ---------------------------------------------------------------------------
printf "${BOLD}Starting containers...${RESET}\n"
docker compose up -d

# ---------------------------------------------------------------------------
# 9. Health-check polling
# ---------------------------------------------------------------------------
APP_PORT="${APP_PORT:-8765}"
HEALTH_URL="http://localhost:${APP_PORT}/api/v1/health"
MAX_RETRIES=30   # 30 × 2 s = 60 s timeout
RETRY_INTERVAL=2

printf "Waiting for Chronovista to be ready"
_attempt=0
_healthy=false

while [ "${_attempt}" -lt "${MAX_RETRIES}" ]; do
  if curl -sf "${HEALTH_URL}" >/dev/null 2>&1; then
    _healthy=true
    break
  fi
  printf "."
  sleep "${RETRY_INTERVAL}"
  _attempt=$(( _attempt + 1 ))
done

printf "\n"

if [ "${_healthy}" = false ]; then
  err "Chronovista did not become healthy within $(( MAX_RETRIES * RETRY_INTERVAL )) seconds."
  info "Check container logs with: docker compose logs app"
  exit 1
fi

# ---------------------------------------------------------------------------
# 10. Success
# ---------------------------------------------------------------------------
ok "Chronovista is running at http://localhost:${APP_PORT}"
printf "\n"
printf "Open ${BOLD}http://localhost:${APP_PORT}/onboarding${RESET} to begin setting up your data.\n"
printf "\n"
