#!/usr/bin/env sh
# Development entry point for Python containers. Runtime images install dependencies at build time.
#
#   start-python-service.sh <dependency-group> <command> [args...]
#
# Examples (see docker-compose.yml):
#   start-python-service.sh backend       uvicorn backend.main:app --host 0.0.0.0 --port 8080
#   start-python-service.sh backend       python -m backend.core.startup.provision
#   start-python-service.sh embedding-gpu uvicorn embedding_service.main:app --host 0.0.0.0 --port 8001
#
# Development flow: source is bind-mounted at /app and each service keeps its own venv volume.
# `uv sync` makes the venv match uv.lock for that group (near-instant when nothing changed),
# including installing the goldenguide project itself, so `backend` and `embedding_service` import.
set -eu

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <dependency-group> <command> [args...]" >&2
  exit 64
fi

GROUP="$1"
COMMAND="$2"
shift 2

# --locked: fail if uv.lock is out of date instead of silently re-resolving versions.
# --no-default-groups: install only the requested group (dev-backend explicitly includes tools).
uv sync --locked --no-default-groups --group "$GROUP"

# exec replaces this shell, so the Python process receives Docker's SIGTERM directly
# and shuts down gracefully (flushing logs and traces).
exec "${UV_PROJECT_ENVIRONMENT:-/venv}/bin/$COMMAND" "$@"
