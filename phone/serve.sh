#!/data/data/com.termux/files/usr/bin/bash
# 화면 서버를 켠다.
#   serve.sh            앞에서 실행 (Ctrl+C 로 종료)
#   serve.sh --ensure   꺼져 있을 때만 뒤에서 조용히 실행
set -uo pipefail

HOME_DIR="$HOME/biotrial"
PIDFILE="$HOME_DIR/server.pid"

alive() {
  [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null
}

run() {
  proot-distro login ubuntu --bind "$HOME_DIR:/opt/biotrial" -- bash -lc '
    cd /opt/biotrial
    set -a; [ -f .env ] && . ./.env; set +a
    export DATABASE_URL="sqlite:////opt/biotrial/biotrial.db"
    export STATIC_DIR="/opt/biotrial/static"
    export TZ="Asia/Seoul"
    export SCHEDULER_ENABLED=false
    exec /opt/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
  '
}

if [ "${1:-}" = "--ensure" ]; then
  alive && exit 0
  run >> "$HOME_DIR/run.log" 2>&1 &
  echo $! > "$PIDFILE"
  echo "   화면 서버를 다시 켰습니다"
  exit 0
fi

if alive; then
  echo "이미 켜져 있습니다.  http://localhost:8000"
  exit 0
fi

echo "바이오 임상 모니터"
echo "  주소: http://localhost:8000"
echo "  종료: Ctrl+C  (볼륨↓ 키가 Ctrl 입니다)"
echo ""
run &
echo $! > "$PIDFILE"
wait
