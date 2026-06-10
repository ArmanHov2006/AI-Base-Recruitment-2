#!/usr/bin/env bash
# One-command launcher for the AI Recruitment platform (bash / WSL / Linux / macOS).
#
#   ./run.sh              start everything (infra + backend + frontend)
#   ./run.sh --infra      docker infra only
#   ./run.sh --no-frontend  infra + backend only
#
# Backend and frontend run in the background; logs go to logs/backend.log and
# logs/frontend.log. Stop with ./run.sh stop.
set -euo pipefail
cd "$(dirname "$0")"

step() { printf '\n==> %s\n' "$1"; }

if [[ "${1:-}" == "stop" ]]; then
  step "Stopping host processes"
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  pkill -f "vite" 2>/dev/null || true
  step "Stopping docker infra"
  docker compose down
  echo "Done."
  exit 0
fi

INFRA_ONLY=false
NO_FRONTEND=false
[[ "${1:-}" == "--infra" ]] && INFRA_ONLY=true
[[ "${1:-}" == "--no-frontend" ]] && NO_FRONTEND=true

mkdir -p logs

[[ -f .env ]] || { echo "[!] .env missing — copying .env.example"; cp .env.example .env; }

step "Checking Docker daemon"
docker info >/dev/null 2>&1 || { echo "Docker daemon is not running. Start Docker and retry."; exit 1; }

step "Starting infra (postgres, minio, redis, mailpit, elasticsearch, worker, beat)"
docker compose up -d

step "Waiting for postgres to be healthy"
for _ in $(seq 1 60); do
  s=$(docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q postgres)" 2>/dev/null || echo "")
  [[ "$s" == "healthy" ]] && break
  sleep 2
done

step "Applying migrations (alembic upgrade head)"
uv run alembic upgrade head

if $INFRA_ONLY; then
  echo "Infra-only mode — done.  MinIO: http://localhost:9001  Mailpit: http://localhost:8025"
  exit 0
fi

step "Starting backend (uvicorn :8000) -> logs/backend.log"
nohup uv run uvicorn app.main:app --reload --port 8000 > logs/backend.log 2>&1 &

if ! $NO_FRONTEND; then
  step "Starting frontend (vite :3000) -> logs/frontend.log"
  [[ -d frontend/node_modules ]] || (cd frontend && npm install)
  (cd frontend && nohup npm run dev > ../logs/frontend.log 2>&1 &)
fi

cat <<EOF

All set.
  Frontend     : http://localhost:3000
  API docs     : http://localhost:8000/docs
  MinIO console: http://localhost:9001
  Mailpit      : http://localhost:8025

  Tail logs : tail -f logs/backend.log logs/frontend.log
  Stop      : ./run.sh stop
EOF
