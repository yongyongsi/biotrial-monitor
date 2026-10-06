#!/usr/bin/env bash
# 새 서버를 한 번에 준비한다. Ubuntu 22.04 / 24.04 기준.
#
#   curl -fsSL https://raw.githubusercontent.com/... 같은 것 없이,
#   파일을 서버에 올린 뒤 실행하면 된다:
#     sudo bash deploy/setup-server.sh
set -euo pipefail

say() { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "root 로 실행해야 합니다:  sudo bash $0" >&2
  exit 1
fi

say "1/4 시스템 업데이트"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq curl ca-certificates rsync >/dev/null

say "2/4 스왑 메모리 확보 (무료 서버는 RAM 이 1GB 인 경우가 많습니다)"
TOTAL_MB=$(free -m | awk '/^Mem:/{print $2}')
SWAP_MB=$(free -m | awk '/^Swap:/{print $2}')
echo "    현재 RAM ${TOTAL_MB}MB / 스왑 ${SWAP_MB}MB"
if [ "$SWAP_MB" -lt 1024 ] && [ ! -f /swapfile ]; then
  # RAM 이 작을수록 스왑을 넉넉히. 최소 2GB.
  SIZE=2G
  [ "$TOTAL_MB" -lt 1500 ] && SIZE=3G
  echo "    ${SIZE} 스왑 파일을 만듭니다 (빌드 중 메모리 부족을 막습니다)"
  fallocate -l "$SIZE" /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=3072
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -q vm.swappiness=10
  grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
else
  echo "    스왑이 이미 충분합니다. 건너뜁니다."
fi

say "3/4 Docker 설치"
if command -v docker >/dev/null 2>&1; then
  echo "    이미 설치되어 있습니다: $(docker --version)"
else
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true

say "4/4 방화벽 (22 / 80 / 443 만 엽니다)"
if command -v ufw >/dev/null 2>&1; then
  ufw allow 22/tcp  >/dev/null
  ufw allow 80/tcp  >/dev/null
  ufw allow 443/tcp >/dev/null
  ufw --force enable >/dev/null
  echo "    ufw 적용 완료"
else
  echo "    ufw 가 없습니다. 건너뜁니다."
fi

# Oracle Cloud 등은 iptables 규칙이 따로 있어 위 ufw 만으로는 부족할 수 있다.
if iptables -L INPUT -n 2>/dev/null | grep -q REJECT; then
  echo ""
  echo "    ⚠️  iptables 에 REJECT 규칙이 있습니다 (Oracle Cloud 기본값)."
  echo "        80/443 을 직접 열어줍니다."
  iptables -I INPUT 5 -p tcp --dport 80  -j ACCEPT 2>/dev/null || true
  iptables -I INPUT 6 -p tcp --dport 443 -j ACCEPT 2>/dev/null || true
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq iptables-persistent >/dev/null 2>&1 || true
  netfilter-persistent save >/dev/null 2>&1 || true
  echo "        ⚠️  클라우드 콘솔의 '보안 목록(Security List)' 에서도 80/443 을 열어야 합니다."
fi

echo ""
echo "─────────────────────────────────────────────"
echo " 서버 준비 완료"
echo ""
free -h | awk '/^Mem:|^Swap:/{printf "   %-6s %s\n", $1, $2}'
echo "   Docker $(docker --version | awk '{print $3}' | tr -d ,)"
echo ""
echo " 다음 단계: docs/DEPLOY.md 의 5번(비밀번호 정하기) 부터"
echo "─────────────────────────────────────────────"
