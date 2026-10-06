# 🧬 바이오 임상시험 모니터 (Phase 0 PoC)

관심 신약의 **임상시험 상태 변화를 뉴스보다 먼저 잡아내는** 개인용 모바일 웹앱.

뉴스 수집기가 아니라 **변화 감지 시스템**이다.
매번 공식 등록정보 전체를 스냅샷으로 저장하고, 이전 스냅샷과 비교해 달라진 부분만 골라
50~60대도 바로 읽을 수 있는 한국어 한 문장으로 만들어 보여준다.

```
제프티 댕기열 임상시험이 환자 모집을 시작했습니다
  기존  모집 전
  현재  환자 모집 중
```

---

## 지금 수집하는 것

| 소스 | 방식 | 주기 | 내용 |
|---|---|---|---|
| **ClinicalTrials.gov** | 공식 API | 60분 (`dataTimestamp` 변화 시에만 실제 수집) | 임상시험 상태·인원·기관·날짜 변화 |
| **DART 전자공시** | 공식 API | 30분 | 임상시험 승인/신청, 품목허가, 기술이전 등 |

첫 화면은 **오늘**만 보여준다. 위쪽 `오늘 / 3일 / 7일 / 30일` 버튼으로 기간을 바꿀 수 있고
고른 값은 기기에 기억된다. '오늘'은 최근 24시간이 아니라 **한국시간 자정부터**다 —
아침에 열었을 때 어제 저녁 소식이 섞이면 "오늘 무슨 일이 있었나"를 알 수 없기 때문이다.

---

## 지금 추적 중인 임상시험

2026-09-27 ClinicalTrials.gov 에서 실제로 확인한 2건이다. 추측으로 만든 데이터는 없다.

| 등록번호 | 약물 | 질환 | 단계 | 상태 | 기관 |
|---|---|---|---|---|---|
| [NCT07576868](https://clinicaltrials.gov/study/NCT07576868) | 제프티 (Xafty / CP-COV03) | 댕기열 | 2·3상 | 환자 모집 중 | 🇻🇳 베트남 2곳 |
| [NCT07683013](https://clinicaltrials.gov/study/NCT07683013) | 페니트리움 (Penitrium / CP-PCA07) | 거세저항성 전립선암 | 1상 | 모집 전 | 🇰🇷 서울대병원 |

사전 조사 결과 전문은 [`docs/00_RESEARCH.md`](docs/00_RESEARCH.md) 참조.

---

## 실행

```bash
docker compose up -d          # DB + 백엔드 + 프론트엔드
docker compose exec backend python -m app.seed     # 최초 1회: 초기 데이터
curl -X POST http://localhost:8000/api/collect     # 최초 1회: 데이터 수집
```

| 주소 | 용도 |
|---|---|
| http://localhost:3000 | 📱 앱 화면 |
| http://localhost:8000/docs | API 문서 |

### 휴대폰에서 보기

PC 와 휴대폰이 같은 와이파이에 있으면 바로 열린다.

```bash
ipconfig getifaddr en0      # 예: 192.168.0.12
```

휴대폰 브라우저에서 `http://192.168.0.12:3000` 접속 →
**공유 → 홈 화면에 추가** 하면 앱처럼 쓸 수 있다 (PWA).

API 주소는 접속한 호스트에서 자동으로 유추하므로 따로 설정할 필요가 없다.

---

## 알림 설정 (선택)

설정하지 않아도 동작하며, 이 경우 알림은 서버 로그로만 남는다.

```bash
cp .env.example .env
# TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 를 채운다 (@BotFather)
docker compose up -d backend
```

기본값은 `ALERT_MIN_SEVERITY=HIGH` — 중요 이상만 알림이 간다.

---

## 변화 감지 직접 확인해 보기

실제 데이터가 바뀌기를 기다리지 않고 지금 바로 확인할 수 있다.

```bash
# 1) '어제는 이랬다'는 과거 스냅샷을 주입
curl -X POST http://localhost:8000/api/demo/simulate-previous \
  -H 'Content-Type: application/json' \
  -d '{"registry_id":"NCT07576868","overall_status":"NOT_YET_RECRUITING",
       "enrollment_count":100,"primary_completion_date":"2026-12",
       "drop_last_location":true}'

# 2) 실제 ClinicalTrials.gov 데이터를 다시 받아온다
curl -X POST "http://localhost:8000/api/collect?force=true"

# 3) 앱 화면 새로고침 → 변화 4건이 한국어로 표시된다
```

초기화는 `curl -X POST http://localhost:8000/api/demo/reset`.

---

## 설계에서 중요한 것 3가지

### 1. ClinicalTrials.gov 는 실시간이 아니다

API 가 `dataTimestamp` 로 데이터 기준시각을 알려준다. 하루 1회 배치 갱신이라
시간 단위 폴링은 의미가 없다. **값이 바뀌었을 때만 실제 수집**하므로 호출량이 1/10 이하다.

```bash
curl -s https://clinicaltrials.gov/api/v2/version
# {"apiVersion":"2.0.5","dataTimestamp":"2026-09-25T09:00:04"}
```

### 2. 한국어 문장은 LLM 이 만들지 않는다

`app/core/diff.py` 가 상태 매핑 테이블 + 템플릿으로 생성한다.
없는 사실을 만들어낼 수 없고, 비용/지연이 없고, 같은 입력에 항상 같은 문장이 나온다.
LLM 은 Phase 2 에서 **뉴스 본문 요약에만** 쓴다.

### 3. 과거 데이터를 지우지 않는다

`raw_document` 와 `clinical_trial_snapshot` 은 append-only 다.
변화 감지가 이 앱의 존재 이유이므로 과거 스냅샷이 곧 자산이다.

---

## 구조

```
backend/app/
  core/korean.py     영어 임상 용어 -> 한국어 (의존성 없는 순수 함수)
  core/severity.py   중요도 분류 규칙 (CRITICAL/HIGH/MEDIUM/LOW)
  core/diff.py       ★ 스냅샷 비교 엔진 + 한국어 문장 생성
  collectors/ctgov.py  ClinicalTrials.gov API v2 (수집 Level 1)
  pipeline.py        수집 -> 스냅샷 -> diff -> 변화 저장 -> 알림
  models.py          DB 스키마
  api/routes.py      REST API (한국어 표시를 서버에서 완성해 내려보낸다)
  api/demo.py        변화 감지 검증용
  notify/telegram.py 알림
  scheduler.py       APScheduler

frontend/
  app/page.tsx                   첫 화면
  app/trial/[registryId]/page.tsx 임상시험 상세
  app/globals.css                ★ 글자 크기 등 디자인 토큰
  components/                    카드 컴포넌트
```

### 어디서 돌릴 수 있나

| 환경 | DB | 화면 | 알림 |
|---|---|---|---|
| **GitHub Actions + Pages** | **SQLite (gh-pages 에 보관)** | **정적 파일** | **이메일** |
| 집 PC / 클라우드 (Docker) | PostgreSQL | Next.js 서버 | 이메일 · 텔레그램 |
| 갤럭시 폰 (Termux) | SQLite | 정적 파일 + FastAPI | 폰 알림창 |

알림은 설정한 것을 **모두** 보낸다 (`app/notify/telegram.py` 의 `_send`).
하나가 실패해도 나머지는 간다.

화면이 데이터를 읽는 주소는 **세 방식 모두 `data/*.json` 하나뿐이다.**
서버가 있는 쪽(FastAPI)이 같은 주소로 내려주도록 맞췄다 — 경로를 나누면 한 군데만 틀려도 조용히 깨진다.

스키마와 수집 로직은 **하나만 유지한다.** SQLAlchemy 의 방언 변형으로
`JSONB↔JSON`, `ARRAY↔JSON`, `BIGINT↔INTEGER` 만 자동으로 바뀐다
(`tests/test_sqlite.py` 가 양쪽 동작을 고정한다).

### 글자 크기 바꾸기

`frontend/app/globals.css` 상단 `:root` 변수만 고치면 전체에 반영된다.

```css
--fs-title: 26px;     /* 화면 제목 */
--fs-number: 30px;    /* 중요 숫자 */
--fs-headline: 21px;  /* 변화 헤드라인 */
--fs-body: 18px;      /* 주요 정보 */
--fs-label: 16px;     /* 보조 정보 */
```

---

## 테스트

```bash
docker compose exec backend python -m pytest tests/ -v
```

69개. 핵심은 `tests/test_diff.py` 로, 요구사항 11항의 예시 시나리오
(`Recruiting → Active, not recruiting` / `100 → 120` / `2026-12 → 2027-02`)를
그대로 재현해 검증한다.

---

## ⭐ GitHub 에서 돌리기 (컴퓨터도 폰 앱도 필요 없음)

GitHub Actions 가 1시간마다 수집하고, GitHub Pages 가 화면을 제공한다.
**무료이고 카드도 필요 없다.** 폰에는 홈 화면 바로가기만 두면 된다.

> ### https://yongyongsi.github.io/biotrial-monitor/

```
GitHub Actions (1시간마다)
  ├─ gh-pages 에서 지난 데이터베이스 가져오기   ← 과거 스냅샷이 있어야 변화를 안다
  ├─ ClinicalTrials.gov / DART 수집
  ├─ 화면용 JSON 생성 (site/ + data/)
  └─ gh-pages 로 force push (항상 1커밋 = 저장소가 안 커진다)
```

- DART 인증키는 저장소 Secrets 에만 있고 공개 파일에는 들어가지 않는다
- `site/` 는 미리 빌드해 둔 화면이다. 화면을 고쳤을 때만 다시 만든다:
  ```bash
  cd frontend && NEXT_EXPORT=1 NEXT_PUBLIC_BASE_PATH=/biotrial-monitor npm run build
  cd .. && rm -rf site && cp -R frontend/out site && git add -A && git commit && git push
  ```
- **알림**: 이메일이 가장 간단하다 (앱 등록·토큰 만료 없음). [docs/ALERT.md](docs/ALERT.md) 참고.
  `EMAIL_USER` / `EMAIL_PASSWORD` / `EMAIL_TO` 를 Secrets 에 넣으면 끝.
- 한계: GitHub 사정으로 실행이 10~20분 늦을 수 있다.

---

## 갤럭시 폰 안에서만 돌리기 (서버 없이)

클라우드 서버도, 집 컴퓨터도 없이 **폰 하나로** 전부 돌릴 수 있다.
안드로이드는 Termux 로 리눅스가 그대로 돌아가기 때문이다. (아이폰은 불가능)

폰에 설치할 앱은 **Termux + Termux:API 2개**뿐이고, 명령은 두 줄이다.

```bash
./phone/build-bundle.sh      # 컴퓨터에서 -> biotrial-install.sh (약 450KB, 파일 하나)
```
```bash
# 폰 Termux 에서 (파일을 카톡 등으로 옮긴 뒤)
termux-setup-storage
bash $(find ~/storage -name biotrial-install.sh | head -1)
```

설치 파일은 스스로 풀리는 형태라 압축 해제도, 경로 입력도 필요 없다.
설치 후 문제가 생기면 `bash ~/biotrial/fix.sh` 하나로 진단과 복구를 한다.

- PostgreSQL 대신 **SQLite** (DB 서버가 필요 없다)
- Next.js 를 **정적 파일로 미리 만들어** FastAPI 가 그대로 서빙한다 (폰에 Node.js 불필요)
- 알림은 텔레그램 없이 **폰 알림창에 배너로 직접** (Termux:API)
- 수집은 **안드로이드 기본 스케줄러**가 1시간마다 깨워서 몇 초 돌리고 재운다
  (앱을 24시간 띄워두지 않으므로 배터리 소모가 거의 없다)
- 스케줄러가 `--persisted` 라 재부팅 후에도 살아난다 -> **자동시작 전용 앱(Termux:Boot)이 필요 없다**
- 비용 0원, 카드 등록 없음, 데이터는 전부 폰 안에

실측 부하: **1회 수집 CPU 0.25초 / 30KB**, 하루 약 **CPU 6초 / 데이터 0.8MB / 메모리 70MB(볼 때만)**.

설치 방법은 **[docs/PHONE.md](docs/PHONE.md)** 참고.
단점은 폰이 꺼져 있는 동안 수집이 멈춘다는 것뿐이다.

---

## 클라우드 배포 (컴퓨터를 꺼도 24시간 감시)

집 컴퓨터가 켜져 있어야만 감시가 되므로, 실사용하려면 클라우드에 올리는 것이 맞다.
**[docs/DEPLOY.md](docs/DEPLOY.md)** 에 단계별 안내가 있다. 전부 무료로 구성할 수 있다
(Oracle Cloud Always Free + DuckDNS 무료 도메인).

```bash
./deploy/deploy.sh ubuntu@서버IP          # 집 컴퓨터에서
sudo bash /opt/biotrial/deploy/setup-server.sh   # 서버에서 최초 1회
```

로컬과 다른 점은 Caddy 리버스 프록시가 앞에 붙어 **자동 HTTPS + 비밀번호 잠금**이 걸리고,
80/443 외의 포트는 외부에 열리지 않는다는 것뿐이다. 나머지 구성은 동일하다.

> **왜 폰 단독으로는 안 되는가**
> 이 앱의 가치는 화면이 아니라 "내가 안 볼 때도 30분마다 DART 와 FDA 를 감시하는 것"에 있다.
> iOS/안드로이드는 배터리 정책상 앱의 주기적 백그라운드 통신을 허용하지 않으므로,
> 폰에 다 넣으면 앱을 열어야만 수집된다 = 감시자가 없어진다.
> 그래서 **항상 켜진 서버 + 폰은 화면(PWA) + 텔레그램 알림** 구조가 맞다.

---

## 다음 단계 (Phase 1)

`docs/00_RESEARCH.md` 15항 참조. 요약하면:

1. **DART 공시 수집기** — 국내에서 가장 빠른 소스. 무료 키 발급 필요
2. **현대바이오사이언스 `/notice` 크롤러** — robots.txt 허용 확인됨, BeautifulSoup 로 충분
3. **국내 뉴스 RSS 5종** — 연합뉴스·메디파나·데일리팜·히트뉴스·약사공론 (전부 동작 확인)

Phase 1 이 필요한 이유는 실증되어 있다.
NCT07683013 은 CT.gov 상 아직 "모집 전"이지만 국내 뉴스로는 **2026-08-12 에 이미 첫 투약**이 끝났다.
ClinicalTrials.gov 만 봐서는 국내 임상 변화를 놓친다.

---

## 보안

- 폰 단독 실행 시 서버는 **`127.0.0.1` 에만** 바인딩한다. 외부에서 닿을 경로가 없다
- 통신은 나가는 방향만 있으며 대상은 ClinicalTrials.gov / DART / FDA 뿐이다
- 알림 버튼 주소는 Termux 가 셸로 실행하므로 **도메인 허용목록 + 셸 인용**으로 이중 차단한다
  (`app/notify/android.py` 의 `safe_url`, `tests/test_notify_security.py`)
- DART 인증키가 로그에 남지 않도록 httpx 로거를 낮춰 두었다
- `.env` 는 `.gitignore` 에 있다. 폰 번들(zip)에는 키가 들어가므로 남에게 보내지 말 것

자세한 점검 내역은 [docs/PHONE.md](docs/PHONE.md) 의 '보안' 절 참고.

---

## 주의

이 앱은 투자 판단 보조 도구이며 투자 권유가 아니다.
화면의 모든 정보에는 출처와 원문 링크가 붙어 있으니 중요한 판단은 반드시 원문을 확인할 것.
`공식 등록정보`와 `기업 발표`, `언론 보도`는 서로 다른 것으로 표시된다.
