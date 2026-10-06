# 클라우드 서버에 올리기

컴퓨터를 꺼도 24시간 감시하도록 만드는 방법입니다.
집 컴퓨터에서 돌던 것과 **완전히 같은 구성**이 그대로 올라갑니다.

```
지금 (집 컴퓨터)                     배포 후 (클라우드)
─────────────────────              ─────────────────────
PC 켜져 있을 때만 감시                24시간 감시
집 와이파이에서만 접속                 어디서나 접속
http://192.168.0.21:3000            https://내주소/
누구나 접속 가능(집 안)                비밀번호 잠금
```

---

## 0. 무엇이 필요한가

| 항목 | 설명 | 비용 |
|---|---|---|
| 서버 1대 | 가장 작은 것으로 충분 (CPU 1개 / RAM 1GB 이상) | **무료** (Oracle Cloud) |
| 도메인 주소 | HTTPS 인증서를 받으려면 필요 | **무료** (DuckDNS) |
| DART 인증키 | 이미 발급받으셨습니다 | 무료 |

**전부 무료로 구성할 수 있습니다.** 카드 등록은 본인 확인용으로만 필요합니다.

> 이 앱은 하루 종일 돌아도 CPU 를 거의 쓰지 않습니다. 30분에 한 번 API 를 부르는 게 전부입니다.
> **가장 싼 서버로 충분합니다.**

---

## 1. 무료 서버 고르기

### ⭐ 1순위 — Oracle Cloud "Always Free"

진짜 **영구 무료**입니다. 체험판 기간이 끝나도 계속 무료입니다.

| | 내용 |
|---|---|
| 주소 | https://www.oracle.com/kr/cloud/free/ |
| 사양 | ARM(Ampere) **4 CPU / 24GB RAM** 까지, 또는 AMD 1/8 CPU · 1GB × 2대 |
| 비용 | **0원** (영구) |
| 필요한 것 | 카드 등록 (**본인 확인용, 청구되지 않습니다**) |

가입 시 **Ubuntu 24.04** 와 **Ampere(ARM)** 를 고르세요. 이 앱에는 1 CPU / 6GB 면 충분합니다.

**알아두실 점 (솔직하게):**

- 카드 등록이 필요합니다. Always Free 등급만 쓰면 청구되지 않지만,
  실수로 유료 자원을 만들지 않도록 **"업그레이드" 버튼은 누르지 마세요.**
- ARM 인스턴스는 인기가 많아 **`Out of capacity`** 가 자주 뜹니다.
  그때는 (a) 다른 가용 도메인(AD)으로 바꾸거나, (b) 시간을 두고 다시 시도하거나,
  (c) **AMD 1GB 짜리**로 만드세요. AMD 도 이 앱을 돌리기엔 충분합니다(스왑 자동 설정됨).
- Oracle 은 **아주 오랫동안 놀고 있는** 무료 인스턴스를 회수할 수 있다고 안내합니다.
  이 앱은 30분마다 수집을 돌리므로 해당되지 않을 가능성이 큽니다.

### 2순위 — Google Cloud 무료 등급

`e2-micro` 1대가 미국 리전(us-west1 / us-central1 / us-east1)에서 영구 무료입니다.
RAM 1GB 라 빠듯하지만 스왑을 잡아주면 동작합니다. 역시 카드 등록이 필요합니다.

### 3순위 — 집에 안 쓰는 기기 (카드도 필요 없음)

낡은 노트북, 미니PC, 라즈베리파이를 집에 두고 켜두는 방법입니다.

- **완전 무료**, 카드 등록도 필요 없음
- 전기료는 노트북 기준 월 몇 백 원 수준
- 데이터가 전부 집 안에 남음
- 공유기 포트 개방이 부담스러우면 **Tailscale Funnel**(무료)을 쓰면
  포트를 열지 않고도 `https://...ts.net` 주소가 생깁니다

> 노트북은 덮개를 닫아도 안 꺼지게 설정해야 합니다.
> (설정 → 전원 → 덮개를 닫을 때: 아무 것도 안 함)

### 무료가 잘 안 될 때 — 월 5~7천원

Hetzner / Vultr / DigitalOcean / Linode 어디든 가장 작은 요금제(1 vCPU / 1~2GB)면 됩니다.
가입이 훨씬 단순하고 바로 만들어집니다. 나중에 무료 서버로 옮기는 것도
`deploy/deploy.sh` 한 번이면 끝입니다.

---

## 2. 무료 도메인 만들기 (DuckDNS)

HTTPS 인증서는 IP 주소로는 못 받습니다. 무료 주소를 하나 만듭니다.

1. https://www.duckdns.org 접속 → 구글/깃허브 계정으로 로그인
2. 원하는 이름 입력 (예: `biotrial-hb`) → **add domain**
3. `current ip` 칸에 **서버 IP 주소**를 넣고 **update ip**

이제 `biotrial-hb.duckdns.org` 가 서버를 가리킵니다.

---

## 3. 프로젝트 올리고 서버 준비

집 컴퓨터에서 **한 줄**이면 됩니다.

```bash
cd /Users/pje/Downloads/father_project
./deploy/deploy.sh ubuntu@서버IP      # Oracle Cloud 는 보통 ubuntu 계정
```

> 이 명령은 소스를 `/opt/biotrial` 로 보내고, `.env` 가 없으면 함께 보내고,
> 빌드 후 실행까지 합니다. 처음에는 `.env` 를 채워야 하므로 **에러가 나는 것이 정상**입니다.
> 4번까지 마친 뒤 같은 명령을 다시 실행하면 됩니다.

그다음 서버에 접속해 준비 스크립트를 한 번 돌립니다.
Docker 설치 · 스왑 메모리 확보 · 방화벽을 알아서 처리합니다.

```bash
ssh ubuntu@서버IP
sudo bash /opt/biotrial/deploy/setup-server.sh
```

> ⚠️ **Oracle Cloud 를 쓰신다면** 서버 안의 방화벽만으로는 부족합니다.
> 웹 콘솔에서 **네트워킹 → 가상 클라우드 네트워크 → 보안 목록 → 수신 규칙 추가** 로
> `0.0.0.0/0` 의 **TCP 80, 443** 을 열어주세요. 이걸 빠뜨리면 접속이 안 됩니다.

---

## 4. 비밀번호 정하기

서버에서 실행합니다.

```bash
cd /opt/biotrial

# 앱 접속 비밀번호 해시 만들기 (원하는 비밀번호로 바꾸세요)
docker run --rm caddy caddy hash-password --plaintext '원하는비밀번호'
# -> $2a$14$... 로 시작하는 긴 문자열이 나옵니다. 통째로 복사하세요.

# 데이터베이스 비밀번호도 하나 만듭니다
openssl rand -base64 24
```

`.env` 파일을 열어 채웁니다.

```bash
nano .env
```

```ini
SITE_ADDRESS=biotrial-hb.duckdns.org
SITE_URL=https://biotrial-hb.duckdns.org
APP_USER=father
APP_PASSWORD_HASH=$2a$14$여기에붙여넣기
POSTGRES_PASSWORD=여기에붙여넣기
```

> `APP_PASSWORD_HASH` 에는 **비밀번호가 아니라 해시 문자열**을 넣습니다.
> 저장은 `Ctrl+O` → `Enter`, 종료는 `Ctrl+X` 입니다.

---

## 5. 실행

```bash
cd /opt/biotrial
docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build
```

처음 한 번만 데이터를 넣습니다.

```bash
docker compose -f deploy/docker-compose.prod.yml exec backend python -m app.seed
docker compose -f deploy/docker-compose.prod.yml exec backend \
  python -c "
from app.db import session_scope
from app.pipeline import collect_ctgov, collect_dart
with session_scope() as db:
    print('임상시험:', collect_ctgov(db, force=True).changes_detected, '건')
    print('공시:', collect_dart(db).changes_detected, '건')
"
```

---

## 6. 휴대폰에서 열기

> ### `https://biotrial-hb.duckdns.org`

1. 처음 열면 **아이디/비밀번호**를 물어봅니다 (`father` + 정하신 비밀번호)
2. 한 번 입력하면 폰이 기억합니다
3. **공유(⬆️) → 홈 화면에 추가**

이제 집 컴퓨터를 꺼도, 여행을 가도, 언제든 열립니다.

---

## 확인 · 관리

```bash
cd /opt/biotrial
P="docker compose -f deploy/docker-compose.prod.yml"

$P ps                      # 잘 돌고 있는지
$P logs -f backend         # 수집 기록 보기 (Ctrl+C 로 나감)
$P restart backend         # 다시 시작
$P down                    # 전부 끄기
```

**서버가 재부팅되어도 자동으로 다시 켜집니다** (`restart: unless-stopped`).

### 코드를 고친 뒤 다시 올리기

```bash
./deploy/deploy.sh ubuntu@서버IP
```

`.env` 는 서버에 있는 것이 그대로 유지되므로 인증키가 지워지지 않습니다.

---

## 데이터 백업

임상시험 스냅샷은 지우지 않고 쌓는 것이 이 앱의 전제입니다(요구사항 29-4).
가끔 받아두세요.

```bash
docker compose -f deploy/docker-compose.prod.yml exec -T db \
  pg_dump -U bio biotrial | gzip > ~/biotrial-$(date +%Y%m%d).sql.gz
```

---

## 자주 겪는 문제

| 증상 | 원인 / 해결 |
|---|---|
| 주소를 열어도 안 뜸 | DuckDNS 의 IP 가 서버 IP 와 같은지 확인. 바꾼 뒤 5분 기다립니다 |
| `인증서 오류` | 80 포트가 막혀 있으면 발급이 안 됩니다. 방화벽(및 클라우드 콘솔)을 확인하세요 |
| 비밀번호를 계속 물어봄 | 해시(`$2a$...`)가 아니라 비밀번호 원문을 넣었을 가능성이 큽니다 |
| 공시가 안 들어옴 | `$P logs backend | grep DART` 로 확인. 인증키가 `.env` 에 있는지 보세요 |
| 화면은 뜨는데 내용이 빔 | 5번의 seed 와 수집을 실행했는지 확인하세요 |
| 빌드 중 멈추거나 죽음 | RAM 부족입니다. `setup-server.sh` 를 실행해 스왑을 잡으세요 |
| Oracle 에서 `Out of capacity` | 다른 가용 도메인(AD)으로 바꾸거나, AMD 1GB 로 만드세요 |
| 접속이 아예 안 됨 (Oracle) | 콘솔의 **보안 목록**에서 80/443 을 열었는지 확인하세요 |

---

## 보안 메모

- 앱 전체가 비밀번호로 잠겨 있고 HTTPS 로 암호화됩니다
- DB 와 백엔드 포트는 **외부에 열려 있지 않습니다** (프록시를 통해서만 접근)
- `.env` 에 DART 인증키가 들어 있으니 **깃에 올리지 마세요** (`.gitignore` 에 이미 포함)
- 이 앱은 투자 판단 보조 도구이며 투자 권유가 아닙니다
