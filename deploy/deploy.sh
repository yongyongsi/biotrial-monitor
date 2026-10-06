#!/usr/bin/env bash
# 집 컴퓨터에서 실행. 소스를 서버로 보내고 재시작까지 한 번에.
#
#   ./deploy/deploy.sh root@서버IP
set -euo pipefail

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  echo "사용법:  ./deploy/deploy.sh root@서버IP" >&2
  exit 1
fi

HERE="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_DIR=/opt/biotrial

echo "==> 소스 전송  ($TARGET:$REMOTE_DIR)"
ssh "$TARGET" "mkdir -p $REMOTE_DIR"
rsync -az --delete \
  --exclude node_modules --exclude .next --exclude __pycache__ \
  --exclude .pytest_cache --exclude .git --exclude .env --exclude .gstack \
  "$HERE/" "$TARGET:$REMOTE_DIR/"

# .env 는 --delete 대상에서 빠져 있으므로 서버에 있던 것이 유지된다.
if [ -f "$HERE/.env" ] && ! ssh "$TARGET" "test -f $REMOTE_DIR/.env"; then
  echo "==> .env 최초 전송"
  scp "$HERE/.env" "$TARGET:$REMOTE_DIR/.env"
  echo "    ⚠️  서버의 .env 에 SITE_ADDRESS / APP_PASSWORD_HASH / POSTGRES_PASSWORD 를 채우세요."
fi

echo "==> 빌드 및 재시작"
ssh "$TARGET" "cd $REMOTE_DIR && docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build"

echo "==> 상태"
ssh "$TARGET" "cd $REMOTE_DIR && docker compose -f deploy/docker-compose.prod.yml ps"
