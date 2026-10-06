#!/data/data/com.termux/files/usr/bin/bash
# 안드로이드 스케줄러가 1시간마다 부르는 스크립트.
# 수집 -> 알림 -> 화면 서버가 꺼져 있으면 다시 켜기. 평소 몇 초면 끝난다.
HOME_DIR="$HOME/biotrial"
LOG="$HOME_DIR/run.log"

termux-wake-lock 2>/dev/null || true
trap 'termux-wake-unlock 2>/dev/null || true' EXIT

{
  echo "── $(date '+%m-%d %H:%M') 수집"
  proot-distro login ubuntu --bind "$HOME_DIR:/opt/biotrial" -- bash -lc '
    cd /opt/biotrial
    set -a; [ -f .env ] && . ./.env; set +a
    export DATABASE_URL="sqlite:////opt/biotrial/biotrial.db"
    export TZ="Asia/Seoul"
    exec /opt/venv/bin/python -m app.collect_once
  '
} >> "$LOG" 2>&1

# 화면 서버가 죽어 있으면 되살린다.
# 폰을 껐다 켠 뒤에도 이 스케줄러가 알아서 다시 띄워주므로
# 자동 시작 전용 앱(Termux:Boot)을 따로 깔지 않아도 된다.
bash "$HOME_DIR/serve.sh" --ensure >> "$LOG" 2>&1

tail -n 1500 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
