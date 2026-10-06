#!/data/data/com.termux/files/usr/bin/bash
# 배너 알림이 제대로 뜨는지 확인합니다.
echo "3초 뒤 알림을 띄웁니다. 화면 위에 배너가 떠야 정상입니다."
sleep 3
termux-notification \
  --title "🔴 페니트리움 임상시험 승인" \
  --content "고형암 임상 2a상 임상시험계획이 미국 FDA 승인을 받았습니다" \
  --priority max --sound --vibrate "500,200,500" \
  --group biotrial --id biotrial-test \
  --button1 "앱 열기" --button1-action "termux-open-url http://localhost:8000"
echo ""
echo "배너가 안 보였다면:"
echo "  설정 → 알림 → Termux → 알림 표시 방식 → '팝업'(배너) 켜기"
