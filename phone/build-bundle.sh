#!/usr/bin/env bash
# 집 컴퓨터에서 실행. 갤럭시에 넣을 파일 한 개를 만든다.
#
#   ./phone/build-bundle.sh
#   -> biotrial-install.sh  (이 파일 하나만 폰으로 옮기면 끝)
#
# 압축을 푸는 단계를 없애려고 '스스로 풀리는 설치 파일' 로 만든다.
# 폰에서는 명령 한 줄이면 된다.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$(mktemp -d)"
OUT="$HERE/biotrial-install.sh"
trap 'rm -rf "$STAGE"' EXIT

say() { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }

say "1/3 화면을 정적 파일로 만듭니다 (폰에는 Node.js 를 깔지 않습니다)"
cd "$HERE/frontend"
[ -d node_modules ] || npm install --no-audit --no-fund
NEXT_EXPORT=1 NEXT_PUBLIC_API_BASE=/ npm run build >/dev/null
echo "    화면 파일 $(find out -type f | wc -l | tr -d ' ')개"

say "2/3 꾸러미 구성"
PKG="$STAGE/biotrial-setup"
mkdir -p "$PKG"
rsync -a --exclude __pycache__ --exclude .pytest_cache \
      "$HERE/backend/app" "$HERE/backend/requirements-phone.txt" "$PKG/"
cp -R "$HERE/frontend/out" "$PKG/static"
cp "$HERE"/phone/install.sh "$HERE"/phone/collect.sh \
   "$HERE"/phone/serve.sh "$HERE"/phone/test-alert.sh "$HERE"/phone/fix.sh "$PKG/"
chmod +x "$PKG"/*.sh
if [ -f "$HERE/.env" ]; then
  grep -E '^(OPENDART_API_KEY|ALERT_MIN_SEVERITY|TELEGRAM_)' "$HERE/.env" > "$PKG/.env" || true
  echo "    .env 포함 (DART 인증키)"
fi
# macOS 의 tar 는 확장 속성(xattr)을 함께 넣는데, 안드로이드에서 풀 때
# 경고가 쏟아져 사용자가 오류로 오해한다. 넣지 않도록 한다.
TAR_OPTS=""
for opt in --no-mac-metadata --no-xattrs; do
  tar -cf /dev/null $opt -T /dev/null 2>/dev/null && TAR_OPTS="$TAR_OPTS $opt"
done
COPYFILE_DISABLE=1 tar $TAR_OPTS -czf "$STAGE/payload.tgz" -C "$STAGE" biotrial-setup

say "3/3 스스로 풀리는 설치 파일 만들기"
cat > "$OUT" <<'HEADER'
#!/data/data/com.termux/files/usr/bin/bash
# 바이오 임상 모니터 — 갤럭시 설치 파일
# 이 파일 하나만 실행하면 됩니다:  bash biotrial-install.sh
set -euo pipefail

echo ""
echo "  바이오 임상 모니터를 설치합니다"
echo "  15~25분쯤 걸립니다. 화면이 멈춘 것처럼 보여도 기다려 주세요."
echo ""

WORK="$HOME/biotrial-setup"
rm -rf "$WORK"
LINE=$(awk '/^__PAYLOAD__$/ {print NR + 1; exit 0; }' "$0")
tail -n +"$LINE" "$0" | base64 -d | tar -xz -C "$HOME"
chmod +x "$WORK"/*.sh
exec bash "$WORK/install.sh"
exit 0   # exec 이 실패하더라도 아래 압축 내용이 실행되지 않도록
__PAYLOAD__
HEADER
base64 < "$STAGE/payload.tgz" >> "$OUT"
chmod +x "$OUT"

echo ""
echo "─────────────────────────────────────────────"
echo " 완성:  biotrial-install.sh   ($(du -h "$OUT" | cut -f1))"
echo ""
echo " 이 파일 하나만 갤럭시로 보내세요 (카톡 '나에게 보내기')"
echo " 폰에서는 명령 한 줄이면 됩니다."
echo "─────────────────────────────────────────────"
