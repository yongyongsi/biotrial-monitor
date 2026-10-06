#!/data/data/com.termux/files/usr/bin/bash
# 뭔가 이상할 때 이것만 실행하면 됩니다:  bash ~/biotrial/fix.sh
HOME_DIR="$HOME/biotrial"

echo ""
echo "  상태를 확인하고 고칩니다..."
echo ""

ok()   { printf "  ✅ %s\n" "$1"; }
warn() { printf "  ⚠️  %s\n" "$1"; }

# 1. 자동 수집이 등록돼 있는가
if termux-job-scheduler --pending 2>/dev/null | grep -q 4242; then
  ok "자동 수집: 등록되어 있습니다 (1시간마다)"
else
  warn "자동 수집이 꺼져 있어 다시 등록합니다"
  termux-job-scheduler --script "$HOME_DIR/collect.sh" \
    --period-ms 3600000 --persisted true --network any --job-id 4242 >/dev/null 2>&1 \
    && ok "자동 수집: 다시 등록했습니다" \
    || warn "등록 실패 — Termux:API 앱이 설치되어 있는지 확인해 주세요"
fi

# 2. 알림 기능
if command -v termux-notification >/dev/null 2>&1; then
  ok "알림: 사용할 수 있습니다"
else
  warn "알림을 쓸 수 없습니다 — Termux:API 앱을 설치해 주세요"
fi

# 3. 화면 서버
bash "$HOME_DIR/serve.sh" --ensure >/dev/null 2>&1
sleep 2
if curl -s -o /dev/null -m 5 http://localhost:8000/api/health 2>/dev/null; then
  ok "화면: http://localhost:8000 정상"
else
  warn "화면이 안 열립니다. 잠시 뒤 다시 시도해 주세요"
fi

# 4. 저장된 정보
proot-distro login ubuntu --bind "$HOME_DIR:/opt/biotrial" -- bash -lc '
  cd /opt/biotrial
  export DATABASE_URL="sqlite:////opt/biotrial/biotrial.db"
  /opt/venv/bin/python -c "
from sqlalchemy import func, select
from app.db import session_scope
from app.models import ClinicalTrial, Disclosure
with session_scope() as db:
    t = db.scalar(select(func.count()).select_from(ClinicalTrial))
    d = db.scalar(select(func.count()).select_from(Disclosure))
    print(f\"  ✅ 저장된 정보: 임상시험 {t}건 / 공시 {d}건\")
" 2>/dev/null' || echo "  ⚠️  저장된 정보를 읽지 못했습니다"

echo ""
echo "  ─────────────────────────────────────"
echo "  화면 보기:  http://localhost:8000"
echo "  그래도 이상하면 이 화면을 그대로 찍어서 보여주세요."
echo "  ─────────────────────────────────────"
echo ""
