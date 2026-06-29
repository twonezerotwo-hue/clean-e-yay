#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/clean-e-yay}"
BRANCH="${DEPLOY_BRANCH:-main}"
LOCK_FILE="${DEPLOY_LOCK_FILE:-/tmp/clean-e-yay-deploy.lock}"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "deploy already running"
  exit 1
fi

cd "$APP_DIR"

echo "deploy: fetch origin/${BRANCH}"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git reset --hard "origin/${BRANCH}"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

echo "deploy: python deps"
. .venv/bin/activate
pip install --upgrade pip
pip install -e .

echo "deploy: web deps"
pnpm install --filter web --frozen-lockfile

echo "deploy: web build"
(
  cd apps/web
  NEXT_DIST_DIR=.next-prod pnpm build
)

echo "deploy: restart services"
sudo systemctl restart eyay-supervisor.service
sudo systemctl restart eyay-web.service

sleep 6
systemctl is-active --quiet eyay-supervisor.service
systemctl is-active --quiet eyay-web.service
curl -fsS http://127.0.0.1:9000/api/v1/health >/dev/null
curl -fsSI http://127.0.0.1:3000/ >/dev/null

echo "deploy: ok $(git rev-parse --short HEAD)"
