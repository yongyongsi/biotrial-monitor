#!/data/data/com.termux/files/usr/bin/bash
# 갤럭시(Termux)에서 한 번만 실행합니다.
set -euo pipefail

say()  { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }
fail() { printf "\n\033[1;31m!! %s\033[0m\n" "$1"; exit 1; }

HOME_DIR="$HOME/biotrial"
SRC="$(cd "$(dirname "$0")" && pwd)"

say "1/6 준비 중"
pkg update -y >/dev/null 2>&1 || true
pkg install -y proot-distro termux-api >/dev/null
command -v termux-notification >/dev/null \
  || echo "    ⚠️  Termux:API 앱이 없습니다. 알림이 안 옵니다 (나중에 설치해도 됩니다)"

say "2/6 기본 프로그램 받는 중 (오래 걸립니다)"
if proot-distro list --installed 2>/dev/null | grep -q ubuntu; then
  echo "    이미 설치되어 있습니다"
else
  proot-distro install ubuntu
fi

say "3/6 앱 파일 정리 중"
mkdir -p "$HOME_DIR"
cp -R "$SRC/app" "$SRC/static" "$SRC/requirements-phone.txt" "$HOME_DIR"/
cp "$SRC"/*.sh "$HOME_DIR"/
[ -f "$SRC/.env" ] && cp "$SRC/.env" "$HOME_DIR"/
chmod +x "$HOME_DIR"/*.sh
echo "    $HOME_DIR"

say "4/6 앱 설치 중 (가장 오래 걸립니다)"
proot-distro login ubuntu -- bash -lc '
  set -e
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3 python3-pip python3-venv ca-certificates tzdata >/dev/null
  [ -d /opt/venv ] || python3 -m venv /opt/venv
  /opt/venv/bin/pip install -q --upgrade pip
' || fail "우분투 준비 실패 - 인터넷을 확인하고 다시 실행해 주세요"

proot-distro login ubuntu --bind "$HOME_DIR:/opt/biotrial" -- bash -lc '
  /opt/venv/bin/pip install -q -r /opt/biotrial/requirements-phone.txt
' || fail "파이썬 패키지 설치 실패 - 다시 실행하면 이어서 진행됩니다"
echo "    완료"

say "5/6 임상시험 정보 받아오는 중"
proot-distro login ubuntu --bind "$HOME_DIR:/opt/biotrial" -- bash -lc '
  cd /opt/biotrial
  set -a; [ -f .env ] && . ./.env; set +a
  export DATABASE_URL="sqlite:////opt/biotrial/biotrial.db"
  export TZ="Asia/Seoul"
  /opt/venv/bin/python -m app.seed 2>&1 | grep -i 완료 || true
  /opt/venv/bin/python -m app.collect_once --force --quiet
  /opt/venv/bin/python -c "
from sqlalchemy import func, select
from app.db import session_scope
from app.models import ClinicalTrial, Disclosure
with session_scope() as db:
    t = db.scalar(select(func.count()).select_from(ClinicalTrial))
    d = db.scalar(select(func.count()).select_from(Disclosure))
    print(f\"    임상시험 {t}건 / 공시 {d}건 저장됨\")
"
'

say "6/6 자동 확인 예약 중"
# 안드로이드 기본 스케줄러에 맡긴다.
#   - 앱을 24시간 띄워둘 필요가 없어 배터리에 유리하다
#   - --persisted 라 폰을 껐다 켜도 유지된다 (자동시작 전용 앱이 필요 없다)
if termux-job-scheduler --script "$HOME_DIR/collect.sh" \
     --period-ms 3600000 --persisted true --network any --job-id 4242 >/dev/null 2>&1; then
  echo "    1시간마다 자동 수집 등록됨 (재부팅해도 유지)"
else
  echo "    ⚠️  등록 실패 - Termux:API 앱을 설치한 뒤 아래를 실행하세요:"
  echo "        bash ~/biotrial/install.sh"
fi

# Termux 를 열면 화면 서버가 알아서 켜지도록
grep -q 'biotrial/serve.sh --ensure' "$HOME/.bashrc" 2>/dev/null || \
  echo 'bash ~/biotrial/serve.sh --ensure 2>/dev/null' >> "$HOME/.bashrc"

bash "$HOME_DIR/serve.sh" --ensure

rm -rf "$HOME/biotrial-setup"

cat <<'DONE'

═════════════════════════════════════════════

  설치가 끝났습니다

  이제 폰 브라우저 주소창에 이렇게 입력하세요

        localhost:8000

  그다음 메뉴(⋮) → 현재 페이지 추가 → 홈 화면

═════════════════════════════════════════════

  남은 것이 하나 있습니다

  설정 → 애플리케이션 → Termux → 배터리
       → '제한 없음' 으로 바꿔주세요

  이걸 안 하면 폰이 이 앱을 꺼버립니다.

═════════════════════════════════════════════

  나중에 뭔가 이상하면 이것만 실행하세요

        bash ~/biotrial/fix.sh

═════════════════════════════════════════════
DONE
