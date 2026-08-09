#!/usr/bin/env bash
# Run the whole app locally: database, queue, API, worker, and web.
# No homelab, no identity server, no API keys required.
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE=(docker compose -p watchpile-dev -f compose.local.yaml)

case "${1:-up}" in
  up)
    echo "Building and starting the stack"
    "${COMPOSE[@]}" up -d --build --wait
    echo "Seeding sample content"
    "${COMPOSE[@]}" exec -T api python -m app.seed
    echo
    echo "Watchpile is running at http://localhost:8080"
    echo "  sign in as Lordo (admin):  http://localhost:8080/auth/login"
    echo "  sign in as Nadia:          http://localhost:8080/auth/login?as=Nadia"
    echo
    echo "Add WD_TMDB_API_KEY and WD_OMDB_API_KEY to a .env file next to"
    echo "compose.local.yaml, then rerun this script, for the real catalog."
    ;;
  down)
    "${COMPOSE[@]}" down
    ;;
  reset)
    echo "Removing local database and uploads"
    "${COMPOSE[@]}" down -v
    ;;
  logs)
    "${COMPOSE[@]}" logs -f --tail=100 "${2:-api}"
    ;;
  seed)
    "${COMPOSE[@]}" exec -T api python -m app.seed
    ;;
  *)
    echo "usage: scripts/dev.sh [up|down|reset|logs [service]|seed]" >&2
    exit 1
    ;;
esac
