# 바이오 임상시험 모니터링 앱 — 사전 조사 보고서

- 작성일: 2026-09-27
- 조사 방식: ClinicalTrials.gov API v2 직접 호출, 각 소스 엔드포인트 실제 curl 검증, robots.txt 확인, 웹 검색 교차 확인
- 표기 규칙: `FACT`(공식 1차 데이터 확인) / `COMPANY CLAIM`(기업 발표) / `NEWS`(언론) / `UNVERIFIED`(미확인)

---

## 1. 요구사항 분석

### 1-1. 이 프로젝트의 본질

요구사항 24항이 정확합니다. 이것은 **뉴스 수집기가 아니라 상태 변화 감지 시스템(Change Detection System)** 입니다.
기술적으로 이 차이는 결정적입니다.

| 구분 | 뉴스 Aggregator | 이 프로젝트 |
|---|---|---|
| 저장 단위 | 기사(불변) | 임상시험 객체(가변) + 시점별 스냅샷 |
| 핵심 연산 | 수집·중복제거 | **이전 스냅샷과의 diff** |
| 가치 | 많이 모으기 | 남들보다 먼저 "바뀐 것"만 잡아내기 |
| 실패 모드 | 누락 | **변화를 놓치거나, 없는 변화를 만들어냄** |

따라서 설계의 중심축은 `clinical_trial_snapshot` 테이블과 diff 엔진이며, 뉴스는 보조 지표입니다.

### 1-2. 조사 중 발견한 3가지 구조적 제약 (설계에 반드시 반영)

**제약 A — ClinicalTrials.gov는 실시간이 아니다**

API가 스스로 데이터 기준시각을 알려줍니다.

```
GET https://clinicaltrials.gov/api/v2/version
→ {"apiVersion":"2.0.5","dataTimestamp":"2026-09-25T09:00:04"}
```

조회 시점은 2026-09-27 03:30 UTC인데 데이터 기준은 **2026-09-25**입니다.
즉 CT.gov는 약 1일 1회 배치로 갱신되며, 최대 2일 가까운 지연이 존재합니다.

> **영향**: 요구사항 23항의 "CT.gov 1~3시간 폴링"은 실효가 없습니다.
> 대신 **`dataTimestamp`를 먼저 확인하고, 값이 바뀌었을 때만 전체 재수집**하는 방식이 정확하고 비용도 훨씬 낮습니다.
> 이 한 줄로 API 호출량이 1/10 이하로 줄어듭니다.

**제약 B — 국내 임상시험은 ClinicalTrials.gov에 없다**

현대바이오사이언스 이름으로 CT.gov에 등록된 임상은 **전 세계 통틀어 2건뿐**입니다(3항 참조).
국내에서 진행된 제프티 COVID-19 2/3상은 CT.gov에 **등록되어 있지 않습니다**.
→ 국내 임상 추적은 **MFDS 의약품안전나라 / 공공데이터포털 OpenAPI / DART 공시**가 유일한 1차 경로입니다.

**제약 C — 가장 빠른 신호는 CT.gov가 아니라 DART 공시일 가능성이 높다**

10항에서 실증되듯, 페니트리움 임상은 **CT.gov 등록정보보다 DART 공시·국내 뉴스가 몇 달 앞섰습니다.**
따라서 "공식 = 가장 빠름"이라는 가정은 틀립니다. 정확한 우선순위는:

```
DART 공시(국내, 법적 강제 · 즉시)
  > 기업 보도자료
  > MFDS 승인정보
  > ClinicalTrials.gov (권위 최고, 속도는 느림)
  > 뉴스
```

**즉 "권위 순위"와 "속도 순위"는 다르며, 앱은 두 축을 따로 표시해야 합니다.**

### 1-3. UI 요구사항(33항) 분석

50~60대 대상이라는 제약은 오히려 설계를 단순화합니다. 핵심은 **"카드 1장 = 변화 1건"** 이고,
카드의 제목은 기사 제목이 아니라 **변화를 서술한 한국어 문장**이어야 합니다.

```
❌  ClinicalTrials.gov updates study status
⭕  베트남 댕기열 임상시험이 '환자 모집 중'으로 바뀌었습니다
```

이 문장은 LLM 요약이 아니라 **diff 결과에서 규칙 기반(템플릿)으로 생성**해야 합니다.
LLM에 맡기면 없는 사실을 만들어낼 수 있고(요구사항 29-5 위반), 비용·지연도 발생합니다.
LLM은 "뉴스 본문 요약"에만 제한적으로 사용합니다.

---

## 2. 제프티(Xafty)의 실제 임상시험 목록  `FACT`

### 2-1. 약물 식별자 정리

| 항목 | 값 | 근거 |
|---|---|---|
| 한글 제품명 | 제프티 | 국내 뉴스·기업 발표 |
| 영문 제품명 | Xafty | 국내 뉴스·기업 발표 |
| 개발코드 | **CP-COV03** | CT.gov 등록 intervention 명칭 `FACT` |
| 기반 물질 | 니클로사마이드(niclosamide) 기반 무기 나노하이브리드 | PMC 논문 제목에서 확인 |
| 기전 | 오토파지(자가포식) 활성화를 통한 바이러스 증식 억제 | `COMPANY CLAIM` / `NEWS` |

> **검색어 사전에 반드시 포함**: `Xafty`, `제프티`, `CP-COV03`, `CP COV03`, `CPCOV03`, `niclosamide`, `니클로사마이드`

### 2-2. ClinicalTrials.gov 등록 현황 (2026-09-27 조회) `FACT`

`query.spons=Hyundai Bioscience` 결과 — **총 2건**:

| NCT ID | 약물 | 적응증 | Phase | Status | 국가 |
|---|---|---|---|---|---|
| **NCT07576868** | CP-COV03 (제프티) | Dengue | Phase 2/3 | **RECRUITING** | 베트남 |
| **NCT07683013** | CP-PCA07 (페니트리움) | 거세저항성 전립선암 | Phase 1 | NOT_YET_RECRUITING | 대한민국 |

`query.intr=CP-COV03` 결과도 **NCT07576868 1건뿐**입니다.

> **중요**: 제프티의 국내 COVID-19 임상시험은 ClinicalTrials.gov에서 **검색되지 않습니다**.
> 미등록 상태이거나 국내 등록시스템(MFDS/CRIS)에만 존재합니다. → `UNVERIFIED`, MFDS API로 확인 필요.

---

## 3. 베트남 댕기열 임상시험 — **요구사항 전제 정정 필요** `FACT`

요구사항 26항은 "베트남 댕기열 임상시험 **2건**"을 찾으라고 되어 있습니다.
실제 공식 등록정보를 확인한 결과는 다음과 같습니다.

> ### 임상시험은 **1건**이며, **베트남 2개 기관**에서 진행 중입니다.
> 또한 이 1건은 내부적으로 **Part 1 / Part 2 두 파트**로 구성되어 있습니다.
> "2개 기관" 및 "2파트" 구조가 "2건"으로 전달된 것으로 보입니다.

별도의 제2 임상시험은 ClinicalTrials.gov에서 확인되지 않았습니다 → `UNVERIFIED`
(WHO ICTRP 및 베트남 자국 등록시스템 추가 확인이 필요하나, 두 사이트 모두 robots.txt에서 크롤링을 금지하고 있어 8항의 대안 경로를 사용해야 합니다.)

### 3-1. NCT07576868 공식 등록정보 전문 `FACT`

| 필드 | 값 |
|---|---|
| **Clinical Trial ID** | `NCT07576868` |
| **공식 URL** | https://clinicaltrials.gov/study/NCT07576868 |
| **API URL** | https://clinicaltrials.gov/api/v2/studies/NCT07576868 |
| Sponsor 자체 과제번호 | `DEN-201` |
| Brief Title | A Study of CP-COV03 Compared With Placebo in Participants With Dengue (Part 1) and Dengue-like Illness (Part 2) |
| Official Title | A Randomized, Double-blinded, Placebo-controlled Clinical Trial to Evaluate Safety and Efficacy of CP-COV03 in Dengue Patients (Part 1) / Dengue and Dengue-like Illness Patients (Part 2) |
| **Sponsor** | Hyundai Bioscience Co., Ltd. (INDUSTRY) |
| Responsible Party | SPONSOR |
| **Phase** | **Phase 2 / Phase 3** |
| Study Type | INTERVENTIONAL |
| **현재 Status** | **RECRUITING (환자 모집 중)** |
| Status 확인 기준월 | 2026-05 |
| **Enrollment** | **210명 (ESTIMATED)** |
| 설계 | Randomized / Parallel / Treatment / **Quadruple masking** (참여자·의료진·연구자·평가자) |
| Condition | Dengue |
| Keywords | dengue, dengue treatment, dengue antiviral |
| **Start Date** | **2026-04-09 (ACTUAL)** |
| **Primary Completion Date** | **2027-01 (ESTIMATED)** |
| **Study Completion Date** | **2027-05 (ESTIMATED)** |
| Study First Submitted | 2026-04-27 |
| Study First Posted | 2026-05-08 (ACTUAL) |
| Last Update Submitted | 2026-07-08 |
| **Last Update Posted** | **2026-07-10 (ACTUAL)** |
| Results Posted | **FALSE** (hasResults: false) |
| Expanded Access | 없음 |
| 대표 연락처 | +82-1544-3194 / clinical@hyundaibio.com |

**투여군 (4개 arm)**

| Arm | 유형 | 용량 |
|---|---|---|
| CP-COV03 low dose | 실험군 | 450 mg/day |
| CP-COV03 mid dose | 실험군 | 900 mg/day |
| CP-COV03 high dose | 실험군 | 1,350 mg/day |
| Placebo | 위약 대조군 | Matching placebo |

**1차 평가변수 (Primary Outcomes)**

1. [Part 1] 이상반응(AE)·중대이상반응(SAE) 발생률 및 중증도 — 투여 시작(Day 1) ~ 안전성 추적 종료(Day 29)
2. [Part 1] Day 3 시점의 뎅기 바이러스 부하 평균 — Baseline, Day 1, 2, 3
3. [Part 2] Day 15까지의 지속적 증상 개선까지 소요 시간

**임상시험 실시기관 — 베트남 2개 기관** `FACT`

| # | 기관명 | 도시 | 국가 | 기관별 Status |
|---|---|---|---|---|
| 1 | **The National Hospital of Tropical Diseases (NHTD)** (국립열대질환병원) | 하노이 (Hanoi) | 베트남 | **RECRUITING** |
| 2 | **Tien Giang Provincial General Hospital** (띠엔장성 종합병원) | 미토 (Mỹ Tho) | 베트남 | **RECRUITING** |

> 요구사항의 "베트남 내 2개 기관/병원"과 **정확히 일치**합니다.

### 3-2. 규제 승인 경로 `NEWS` / `COMPANY CLAIM`

- 베트남 보건부(MOH) 산하 과학기술교육국(ASTT) Pre-IND 승인 (12월 9일)
- 중앙 윤리위원회(EC) IND 승인 (12월 20일)
- 이후 베트남 국립병원에서 **과립형 제형 변경 승인** — 고열·구토·연하곤란 환자 투약 편의 목적
- 뎅기열·지카 등 모기매개 바이러스와 COVID-19·인플루엔자A를 하나의 약물로 다루는 "범용 항바이러스제" 설계 → **이는 기업 주장이며 임상으로 입증된 사실이 아님** `COMPANY CLAIM`

> **앱 설계 반영**: 제형 변경 승인 같은 이벤트는 CT.gov 필드에 나타나지 않습니다.
> 즉 **레지스트리 diff만으로는 잡히지 않는 변화**가 존재하며, 뉴스/공시 채널이 이를 보완해야 합니다.

---

## 4~7. 요약 (공식 URL / ID / Status / 최종 업데이트)

| 항목 | NCT07576868 (제프티·댕기열) | NCT07683013 (페니트리움·전립선암) |
|---|---|---|
| **4. 공식 URL** | https://clinicaltrials.gov/study/NCT07576868 | https://clinicaltrials.gov/study/NCT07683013 |
| **5. Trial ID** | NCT07576868 (`DEN-201`) | NCT07683013 (`ADM-PC-001`) |
| **6. 현재 Status** | **RECRUITING** (환자 모집 중) | **NOT_YET_RECRUITING** (모집 전) |
| **7. 마지막 업데이트** | **2026-07-10** (posted) | **2026-07-06** (posted) |
| Start Date | 2026-04-09 (ACTUAL) | 2026-07 (ESTIMATED) |
| Primary Completion | 2027-01 | 2027-09 |
| Study Completion | 2027-05 | 2027-12 |
| Enrollment | 210명 | 18명 |
| 기관 | 베트남 2개소 | 서울대학교병원 (CT.gov 등재 기준 1개소) |

---

## 8. 사용 가능한 공식 API — **실제 호출 검증 결과**

각 엔드포인트를 실제로 호출한 결과입니다. (✅ 즉시 사용 / ⚠️ 조건부 / ❌ 불가)

### Tier 1 — 임상시험 등록

| Source | 엔드포인트 | API | 인증 | 검증 결과 | 갱신주기 | robots |
|---|---|---|---|---|---|---|
| ✅ **ClinicalTrials.gov v2** | `clinicaltrials.gov/api/v2/studies` | REST/JSON | **불필요** | **HTTP 200, 정상** | **1일 1회 배치** (`dataTimestamp` 확인) | API는 공식 제공 |
| ❌ **WHO ICTRP** | `trialsearch.who.int` | 없음(웹포털) | - | HTTP 200이나 **robots.txt `Disallow: /`** | 주 1회 | **크롤링 금지** |
| ⚠️ **EU CTIS** | `euclinicaltrials.eu/ctis-public-api/search` | REST | **필요** | **HTTP 403** `Missing Authentication Token` | - | 별도 확인 필요 |
| ❌ **CRIS (질병관리청)** | `cris.nih.go.kr` | 웹 only | - | HTTP 200이나 **robots.txt `Disallow: /`** | - | **크롤링 금지** |
| ⚠️ **MFDS 의약품 임상시험 정보** | data.go.kr `15056835` | REST/XML·JSON | **키 필요(무료)** | 미발급 상태 | 미상 | nedrug는 `Disallow: /` → **API만 사용** |

> **WHO ICTRP 대안**: 웹 크롤링이 금지되어 있으므로, ICTRP가 제공하는 **주간 벌크 다운로드 파일**을 이용해야 합니다. 다만 별도 신청/이용약관 확인이 필요합니다 → `UNVERIFIED`, 착수 시 확인 항목.

### Tier 1 — 규제기관

| Source | 엔드포인트 | API | 인증 | 검증 결과 |
|---|---|---|---|---|
| ✅ **openFDA — 이상사례** | `api.fda.gov/drug/event.json` | REST/JSON | 불필요(키 있으면 한도↑) | **HTTP 200, 15KB 응답** |
| ✅ **openFDA — 회수/조치** | `api.fda.gov/drug/enforcement.json` | REST/JSON | 불필요 | **HTTP 200** |
| ✅ **openFDA — NDC** | `api.fda.gov/drug/ndc.json` | REST/JSON | 불필요 | **HTTP 200** |
| ⚠️ **openFDA — 승인/라벨** | `drugsfda.json`, `label.json` | REST/JSON | 불필요 | **HTTP 200이나 niclosamide 검색 결과 0건** |
| ❌ **FDA RSS** | `fda.gov/.../rss.xml` | RSS | 불필요 | **HTTP 404** (브라우저 UA·Accept 헤더 추가해도 동일) |
| ❌ **EMA RSS** | `ema.europa.eu/en/rss/*` | RSS | 불필요 | **HTTP 404 + 봇 차단 페이지(antibot)** |
| ✅ **WHO 뉴스 RSS** | `who.int/rss-feeds/news-english.xml` | RSS | 불필요 | **HTTP 200, 141KB 정상** |

> **의미 있는 음성 결과**: `drugsfda`·`label`에서 니클로사마이드가 0건이라는 것은
> **미국 내 해당 경구제의 승인·라벨 레코드가 openFDA에 없다**는 뜻입니다.
> 즉 향후 FDA 승인/IND 관련 최초 신호는 openFDA가 아니라 **FDA 웹 공지·기업 공시**에서 먼저 나올 가능성이 높습니다.

### Tier 2 — 학술

| Source | 엔드포인트 | 인증 | 검증 결과 |
|---|---|---|---|
| ✅ **Europe PMC** | `ebi.ac.uk/europepmc/webservices/rest/search` | 불필요 | **HTTP 200, `CP-COV03` 검색 hitCount = 11건** |
| ⚠️ **PubMed E-utilities** | `eutils.ncbi.nlm.nih.gov/.../esearch.fcgi` | 불필요(키 권장) | HTTP 200이나 **백엔드 500 일시 장애** (2회 재시도 동일) |
| ⚠️ **medRxiv/bioRxiv API** | `api.biorxiv.org/details/...` | 불필요 | HTTP 200이나 **응답 본문 0바이트** — 파라미터 형식 재확인 필요 |

> **권장**: 1차 학술 소스를 **Europe PMC로 채택**합니다. PubMed을 포함하면서 API가 더 안정적이고, 현재 유일하게 CP-COV03 검색이 실제로 작동한 학술 엔드포인트입니다. PubMed은 보조·폴백으로 둡니다.

---

## 9. FDA 관련 데이터 수집 방법

FDA RSS가 이 환경에서 차단되므로 **3중 경로**로 설계합니다.

```
1) openFDA API (✅ 검증됨)
   drug/event · drug/enforcement · drug/ndc · drugsfda · label
   → 정기 폴링, 키 없이 동작. 키 발급 시 호출 한도 상향.

2) FDA 웹 공지 크롤링 (RSS 차단 대응)
   https://www.fda.gov/news-events/fda-newsroom/press-announcements
   → requests + BeautifulSoup. 목록 HTML 파싱 → 제목·날짜·URL 추출 → 해시 diff.
   → 차단 시 Playwright로 승격.

3) 키워드 감시
   openFDA 전 인덱스 + 웹 공지에 대해
   {niclosamide, CP-COV03, Xafty, Hyundai Bioscience, dengue} 매칭.
```

`drugsfda`/`label`에 레코드가 **없다가 생기는 순간**이 곧 FDA 승인 신호이므로,
**"결과 0건"이라는 상태 자체를 스냅샷으로 저장**해야 합니다. (0건 → 1건 전환 = CRITICAL 알림)
이것이 이 프로젝트에서 놓치기 쉬운 핵심 포인트입니다.

---

## 10. 페니트리움 — 정확한 영문명/개발명 확인 결과 `FACT` + `NEWS`

| 항목 | 값 | 신뢰도 |
|---|---|---|
| 한글명 | 페니트리움 | `NEWS` |
| **영문명** | **Penetrium** (™) — 언론의 "Penitrium" 표기는 오기 | `FACT` (DART 공시 원문) |
| **개발코드** | **CP-PCA07** | `FACT` (CT.gov 등록) |
| 관련 법인 | **페니트리움바이오 (코스닥 187660, 별도 상장사)** / 현대바이오 (048410) | `FACT` (DART 고유번호 파일) |
| 기반 물질 | **니클로사마이드** (CT.gov keywords에 `Niclosamide` 명시) | `FACT` |
| 적응증 | 거세저항성 전립선암(CRPC) → 이후 췌장암 확대 계획 | `FACT` / 확대는 `COMPANY CLAIM` |
| 기전 | 비세포독성. 종양 주변 세포외기질(ECM) 연화 → 기존 항암제 침투 개선 | `COMPANY CLAIM` |
| CT.gov 등록 | **NCT07683013** | `FACT` |

> **`페니트리움` ↔ `CP-PCA07` 동일성 판정**: 적응증(거세저항성 전립선암), 병용약물(엔잘루타마이드),
> 상(1상), 기관(서울대병원), 스폰서(현대바이오사이언스)가 모두 일치하여 **동일 물질로 판단**합니다.
> 다만 "페니트리움 = CP-PCA07"을 명시한 단일 공식 문서는 확인하지 못했습니다 → 이 매핑 자체는 `ANALYSIS` 등급으로 저장합니다.

### 10-1. ★ 이 프로젝트의 가치를 증명하는 실제 사례 — 등록정보 vs 현실의 괴리

페니트리움 건에서 **공식 등록정보가 현실보다 뒤처진 증거 2가지**를 발견했습니다.

**괴리 ① Status**

| 소스 | 내용 | 시점 |
|---|---|---|
| ClinicalTrials.gov (NCT07683013) | **NOT_YET_RECRUITING** (모집 전) | Last Update **2026-07-06** |
| 국내 뉴스·기업 발표 | **전립선암 환자 첫 투약 개시** | **2026-08-12** |

> CT.gov는 2026-09-27 현재까지도 "모집 전"입니다. 실제로는 **약 6주 전에 첫 환자 투약이 이루어졌습니다.**

**괴리 ② 실시기관 수**

| 소스 | 실시기관 |
|---|---|
| ClinicalTrials.gov | 서울대학교병원 **1개소** |
| 식약처 1상 변경승인 (2026-04-17 공시) | **서울삼성병원 · 한림대학교성심병원 · 서울대학교병원** 등 다기관 |

> **결론**: `ClinicalTrials.gov만 감시하면 국내 임상 변화를 놓칩니다.`
> **DART 공시 + MFDS 승인정보 + 기업 보도자료**를 동등한 Tier 1 소스로 반드시 포함해야 합니다.
> 이 발견은 아키텍처의 소스 우선순위를 바꾸는 근거이며, 1-2절 제약 C의 실증입니다.

### 10-2. ★★ DART 실증 (2026-09-27 인증키 발급 후 추가 조사)

DART OpenAPI 인증키로 실제 공시를 조회한 결과, **ClinicalTrials.gov 에 전혀 존재하지 않는 임상시험 프로그램**이 확인되었다.

**DART 고유번호** `FACT`

| 기업 | 종목코드 | corp_code |
|---|---|---|
| 현대바이오 | 048410 | `00313649` |
| **페니트리움바이오** | **187660** | `01409022` |
| 현대바이오랜드 (별개 회사) | 052260 | `00347062` |

> 페니트리움바이오가 **별도 상장사**라는 점이 중요하다. NCT07683013 의 과제번호가 `ADM-PC-001` 인 것과 연결된다.
> 투자 대상이 2개 종목으로 나뉘므로 Watchlist 도 분리해야 한다.

#### 🔴 CT.gov 에 없는 임상시험 — 미국 FDA IND 승인 `FACT`

2026-09-03 공시 (접수번호 `20260903900243`) 전문에서 확인:

| 항목 | 내용 |
|---|---|
| 제목 | 재발성 또는 불응성 진행성 고형암 환자 대상, 표준치료 병용 **Penetrium** 유효성·안전성 평가 **제2a상 IND 미국 FDA 승인** |
| 승인기관 | **미국 식품의약국 (FDA)** |
| 실시국가 | **미국** (3개 기관) |
| **등록번호** | **IND 183600** |
| 신청일 → 승인일 | **2026-08-04 → 2026-09-03** |
| 목표 대상자 | 18명 |
| 1차 지표 | RECIST v1.1 기준 객관적반응률(ORR) |
| 예상 종료일 | 2028-09-03 |

**ClinicalTrials.gov 검색 결과: 0건**

```
query.term=Penetrium              → 0건
query.term=Penitrium              → 0건
query.spons=Penetrium Bio         → 0건
query.term=pembrolizumab niclosamide → 0건
```

> **이 프로젝트의 존재 이유가 실측으로 증명되었다.**
> 한국 상장사의 **미국 FDA IND 승인**이 DART 에는 2026-09-03 에 공시되었는데,
> 24일이 지난 2026-09-27 현재까지 ClinicalTrials.gov 에서는 **검색조차 되지 않는다.**
> CT.gov 만 감시하는 시스템은 이 사건을 영원히 놓친다.

#### CT.gov 에 없는 다른 임상 `FACT`

| 공시일 | 기업 | 내용 |
|---|---|---|
| 2026-06-17 | 페니트리움바이오 | 불응성/재발성 고형암 대상 **펨브롤리주맙(키트루다) + Penetrium™ 병용요법 1상** 변경승인 |
| 2026-05-13 | 페니트리움바이오 | 위 1상 변경승인 **신청** |
| 2026-08-04 | 페니트리움바이오 | 고형암 2a상 **IND 신청** |
| 2026-09-03 | 페니트리움바이오 | 고형암 2a상 **FDA 승인** |
| 2026-09-04 | 현대바이오 | CPPCA07 전립선암 1상 **변경승인 신청** |
| 2026-04-17 | 현대바이오 | CPPCA07 전립선암 1상 **변경승인** |
| 2026-03-06 | 현대바이오 | CPPCA07 전립선암 1상 **변경승인 신청** |

> 반면 NCT07683013 의 CT.gov Last Update 는 여전히 **2026-07-06**, 상태는 **NOT_YET_RECRUITING** 이다.

#### 설계에 반영할 점

1. **공시는 `신청 → 승인` 2단 상태기계다.** 같은 임상에 대해 신청 공시와 승인 공시가 별도로 나온다.
   `regulatory_event` 에 `event_type`(IND_APPLY / IND_APPROVE / PROTOCOL_AMEND_APPLY / PROTOCOL_AMEND_APPROVE)을 두고 쌍으로 묶어야 중복이 아닌 진행으로 읽힌다.
2. **공시 제목만으로 충분하지 않다.** `document.xml` API 로 본문을 받아야 IND 번호·기관 수·목표 인원·예상 종료일이 나온다.
3. **`투자판단관련주요경영사항` 보고서명이 임상 이벤트의 신호다.** 이 접두어로 1차 필터링한 뒤 본문을 파싱한다.
4. 본문은 **XML(zip) + euc-kr/utf-8 혼재** 이므로 인코딩 폴백이 필요하다.


---

## 11. 국내 데이터 소스 — 검증 결과

| Source | 방식 | URL | 검증 | 비고 |
|---|---|---|---|---|
| ⭐ **DART 전자공시 OpenAPI** | REST/JSON | `list.json` / `corpCode.xml` / `document.xml` | ✅ **키 발급 완료, status=000 정상 동작 확인** (2026-09-27) | 무료. **국내 최속·법적 강제 소스. 10-2 참조** |
| ⚠️ MFDS 의약품 임상시험 정보 | REST | data.go.kr `15056835` | 키 발급 필요 | nedrug 직접 크롤링은 robots 금지 |
| ⚠️ 식의약 데이터포털 | REST | `data.mfds.go.kr` | 키 발급 필요 | 시험책임자·의뢰자·승인일자 제공 |
| ✅ **현대바이오사이언스 공식** | **크롤링 허용** | `hyundaibioscience.com/notice`, `/media` | **HTTP 200**, robots.txt **`Allow: /`** (금지 목록에 없음), sitemap.xml 제공 | 목록 HTML에 날짜 직접 노출(최신 2026-09-16) → **BeautifulSoup만으로 파싱 가능, JS 렌더링 불필요** |
| ✅ 연합뉴스 (건강) | RSS | `yna.co.kr/rss/health.xml` | **HTTP 200, 96KB** | |
| ✅ 히트뉴스 | RSS | `hitnews.co.kr/rss/allArticle.xml` | **HTTP 200, 52KB** | |
| ✅ 메디파나뉴스 | RSS | `medipana.com/rss/allArticle.xml` | **HTTP 200, 52KB** | |
| ✅ 데일리팜 | RSS | `dailypharm.com/rss/rss.php` | **HTTP 200, 31KB** | |
| ✅ 약사공론 | RSS | `kpanews.co.kr/rss/allArticle.xml` | **HTTP 200, 53KB** | |
| ❌ 바이오스펙테이터 | RSS | 2개 경로 시도 | **HTTP 404** | RSS 경로 재탐색 또는 크롤링 필요 |

> **국내 소스 결론**: 언론 RSS는 5개가 즉시 사용 가능하고, 기업 공식 사이트는 크롤링이 허용됩니다.
> 가장 중요한 **DART는 무료 키 발급만 하면 즉시 사용 가능**합니다.

---

## 12. 해외 데이터 소스 — 검증 결과

| Source | 방식 | 검증 | 대응 |
|---|---|---|---|
| ✅ **ClinicalTrials.gov** | REST API | **HTTP 200** | 주 소스 |
| ✅ **openFDA** | REST API | **HTTP 200** (event/enforcement/ndc) | 주 소스 |
| ✅ **Europe PMC** | REST API | **HTTP 200**, CP-COV03 11건 | 학술 주 소스 |
| ✅ **WHO 뉴스** | RSS | **HTTP 200, 141KB** | 즉시 사용 |
| ✅ **STAT News** | RSS `statnews.com/feed/` | **HTTP 200, 57KB** | 즉시 사용 |
| ❌ **Fierce Biotech** | RSS | **HTTP 403 — Cloudflare 봇 차단** (`Just a moment...`) | **Playwright 필요** |
| ❌ **Endpoints News** | RSS | **HTTP 403 — CloudFront 차단** | **Playwright 필요** |
| ❌ **EMA** | RSS | **HTTP 404 + antibot** | 웹 크롤링/Playwright |
| ❌ **FDA** | RSS | **HTTP 404** | 9항의 3중 경로 |

### 12-1. 크롤링 계층 설계 (사용자 지적사항 반영)

말씀하신 대로 **API만으로는 해외 주요 매체·규제기관을 커버할 수 없습니다.**
실측 결과 **해외 소스의 상당수가 403/404로 차단**되므로, 크롤링은 선택이 아니라 필수입니다.
다만 요구사항 29-1의 우선순위는 유지하고, **4단계 자동 승격(escalation) 구조**로 설계합니다.

```
Level 1  공식 API            (requests/httpx)          예: CT.gov, openFDA, Europe PMC, DART
   ↓ 실패 / 미제공
Level 2  RSS / sitemap.xml   (feedparser)              예: STAT, WHO, 국내 5개 매체
   ↓ 404 / 없음
Level 3  정적 HTML 크롤링     (httpx + BeautifulSoup)   예: 현대바이오 /notice·/media, FDA 공지
   ↓ 403 / 봇차단 / JS 렌더링
Level 4  브라우저 렌더링       (Playwright, headless)    예: Fierce Biotech, Endpoints, EMA
```

**각 소스는 `collection_level` 컬럼으로 현재 단계를 기록**하고, 실패가 N회 연속되면 자동으로 다음 레벨로 승격시킵니다.
이렇게 하면 무거운 Playwright는 **정말 필요한 소스에만** 쓰이고, 나머지는 가볍게 유지됩니다.

**크롤링 공통 규칙 (반드시 준수)**
- `robots.txt`를 매 수집 전 확인 — `Disallow: /` 사이트(CRIS, WHO ICTRP, nedrug)는 **크롤링하지 않고 API/벌크 경로만 사용**
- 소스별 `crawl-delay` 준수, 도메인당 동시요청 1, 지수 백오프
- 식별 가능한 User-Agent + 연락처 명시
- 본문 전문 저장이 아닌 **제목·날짜·URL·요약** 중심 저장 (저작권 고려)
- 원문 링크 필수 보존 (요구사항 29-2)

---

## 13. 추천 Architecture

### 13-1. 전체 구조

```
┌──────────────────────────────────────────────────────────────┐
│  COLLECTORS  (APScheduler, 소스별 독립 주기)                    │
│  ┌────────────┬────────────┬────────────┬────────────┐        │
│  │ L1 API     │ L2 RSS     │ L3 BS4     │ L4 Playwright│      │
│  │ CT.gov     │ STAT/WHO   │ 현대바이오   │ Fierce/EMA  │       │
│  │ openFDA    │ 국내5개매체  │ FDA공지     │ Endpoints   │       │
│  │ EuropePMC  │            │            │            │        │
│  │ DART       │            │            │            │        │
│  └────────────┴────────────┴────────────┴────────────┘        │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
                 ┌─────────────────────┐
                 │  raw_document       │  ← 원본 그대로 보존 (절대 삭제 X)
                 │  (JSON/HTML + hash) │     요구사항 29-3, 29-4
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │  NORMALIZE          │  소스별 → 공통 스키마
                 └──────────┬──────────┘
                            ▼
        ┌───────────────────┴────────────────────┐
        ▼                                        ▼
┌────────────────────┐                 ┌────────────────────┐
│ clinical_trial     │                 │ news / publication │
│ + _snapshot        │                 │ + regulatory_event │
└─────────┬──────────┘                 └─────────┬──────────┘
          ▼                                      ▼
┌────────────────────┐                 ┌────────────────────┐
│ DIFF ENGINE        │                 │ EVENT CLUSTERING   │
│ 필드 단위 비교       │                 │ 중복 기사 → 1 Event │
│ → _change 생성      │                 │ (요구사항 12)       │
└─────────┬──────────┘                 └─────────┬──────────┘
          └──────────────┬───────────────────────┘
                         ▼
              ┌─────────────────────┐
              │ SEVERITY CLASSIFIER │  규칙 기반 (LLM 아님)
              │ CRITICAL/HIGH/...   │  요구사항 13
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │ KO MESSAGE BUILDER  │  템플릿 기반 한국어 문장 생성
              │ "모집 전 → 환자 모집 중"│  ★ LLM 미사용 = 환각 0
              └──────────┬──────────┘
                         ▼
        ┌────────────────┴────────────────┐
        ▼                                 ▼
┌────────────────┐              ┌──────────────────┐
│ FastAPI (REST) │              │ ALERT DISPATCHER │
└───────┬────────┘              │ Telegram → Push  │
        ▼                       └──────────────────┘
┌────────────────┐
│ Next.js PWA    │  모바일 우선 / 대형 글꼴 / 한국어
└────────────────┘

        (별도) LLM SUMMARIZER — 뉴스 본문 요약 전용.
               출처 document_id 필수 연결. 임상 상태 문장 생성에는 사용 금지.
```

### 13-2. 기술 스택

| 레이어 | 선택 | 이유 |
|---|---|---|
| Backend | **Python 3.12 + FastAPI** | 요구사항 28항, 크롤링 생태계 |
| DB | **PostgreSQL 16** | JSONB(원본 보존) + 시계열 스냅샷 |
| ORM | SQLAlchemy 2.0 + Alembic | |
| 스케줄러 | **APScheduler** (Celery 아님) | 개인용·단일 서버. Celery는 초기에 과설계 |
| HTTP | httpx (async) | |
| 파싱 | BeautifulSoup4 + lxml + feedparser | |
| 브라우저 | Playwright (Level 4 전용) | |
| Frontend | **Next.js 15 + TypeScript + Tailwind** | PWA, 요구사항 19 |
| 알림 | **Telegram Bot → 이후 Web Push** | 요구사항 20항 권고대로 쉬운 것부터 |
| 배포 | Docker Compose | 요구사항 28항 |

> **APScheduler 선택 근거**: 개인 1인 사용, 소스 20개 미만, 단일 서버 전제입니다.
> Celery + broker는 운영 복잡도만 늘립니다. 소스가 100개를 넘어가면 그때 교체합니다.

---

## 14. 추천 Database Schema

핵심 3테이블(`clinical_trial` / `_snapshot` / `_change`)이 이 시스템의 심장입니다.

```sql
-- ───────────── 마스터 ─────────────
CREATE TABLE source (
  id            SERIAL PRIMARY KEY,
  code          TEXT UNIQUE NOT NULL,        -- 'ctgov','opendart','openfda','hyundaibio'
  name_ko       TEXT NOT NULL,               -- '미국 임상시험 등록소'
  source_type   TEXT NOT NULL,               -- REGISTRY|REGULATOR|COMPANY|NEWS|JOURNAL
  region        TEXT NOT NULL,               -- KR | GLOBAL
  is_official   BOOLEAN NOT NULL,            -- 요구사항 33-10 공식/뉴스 구분
  collection_level SMALLINT NOT NULL,        -- 1=API 2=RSS 3=BS4 4=Playwright
  base_url      TEXT,
  poll_interval_sec INT NOT NULL,
  robots_allowed BOOLEAN,
  last_ok_at    TIMESTAMPTZ,
  fail_streak   INT DEFAULT 0                -- N회 실패 시 level 자동 승격
);

CREATE TABLE drug (
  id SERIAL PRIMARY KEY,
  name_ko TEXT, name_en TEXT, dev_code TEXT,
  aliases TEXT[],                            -- 검색어 사전: {Xafty,제프티,CP-COV03,niclosamide}
  company_id INT REFERENCES company(id)
);
CREATE TABLE company  (id SERIAL PRIMARY KEY, name_ko TEXT, name_en TEXT,
                       dart_corp_code TEXT, aliases TEXT[]);
CREATE TABLE disease  (id SERIAL PRIMARY KEY, name_ko TEXT, name_en TEXT, aliases TEXT[]);

-- ───────────── 원본 보존 (요구사항 29-3, 29-4) ─────────────
CREATE TABLE raw_document (
  id            BIGSERIAL PRIMARY KEY,
  source_id     INT REFERENCES source(id),
  external_id   TEXT,                        -- NCT ID / 공시번호 / URL
  url           TEXT,
  payload       JSONB,                       -- 원본 그대로. 절대 UPDATE 하지 않음
  content_hash  TEXT NOT NULL,               -- 변화 감지 1차 필터
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_id, external_id, content_hash)   -- 요구사항 22 중복 방지
);

-- ───────────── ★ 핵심: 임상시험 3부작 ─────────────
CREATE TABLE clinical_trial (
  id              SERIAL PRIMARY KEY,
  registry        TEXT NOT NULL,             -- 'CTGOV','MFDS','CRIS'
  registry_id     TEXT NOT NULL,             -- 'NCT07576868'
  org_study_id    TEXT,                      -- 'DEN-201'
  drug_id         INT REFERENCES drug(id),
  company_id      INT REFERENCES company(id),
  disease_id      INT REFERENCES disease(id),
  title_en        TEXT,
  title_ko        TEXT,                      -- 33-4: 한국어 표시용
  is_watchlisted  BOOLEAN DEFAULT FALSE,
  UNIQUE (registry, registry_id)
);

CREATE TABLE clinical_trial_snapshot (       -- 시점별 전체 상태. 삭제 금지(29-4)
  id                    BIGSERIAL PRIMARY KEY,
  trial_id              INT REFERENCES clinical_trial(id),
  raw_document_id       BIGINT REFERENCES raw_document(id),
  overall_status        TEXT,                -- RECRUITING 등
  phase                 TEXT[],
  enrollment_count      INT,
  enrollment_type       TEXT,                -- ESTIMATED | ACTUAL
  start_date            DATE,
  primary_completion_date DATE,
  completion_date       DATE,
  has_results           BOOLEAN,
  locations             JSONB,               -- [{facility,city,country,status}]
  location_count        INT,
  source_last_update    DATE,                -- CT.gov lastUpdatePostDate
  snapshot_hash         TEXT NOT NULL,
  captured_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON clinical_trial_snapshot (trial_id, captured_at DESC);

CREATE TABLE clinical_trial_change (         -- diff 결과 = 앱의 주인공
  id            BIGSERIAL PRIMARY KEY,
  trial_id      INT REFERENCES clinical_trial(id),
  prev_snapshot_id BIGINT REFERENCES clinical_trial_snapshot(id),
  curr_snapshot_id BIGINT REFERENCES clinical_trial_snapshot(id),
  field_name    TEXT NOT NULL,               -- 'overall_status'
  old_value     TEXT,                        -- 'NOT_YET_RECRUITING'
  new_value     TEXT,                        -- 'RECRUITING'
  old_value_ko  TEXT,                        -- '모집 전'
  new_value_ko  TEXT,                        -- '환자 모집 중'
  severity      TEXT NOT NULL,               -- CRITICAL|HIGH|MEDIUM|LOW
  headline_ko   TEXT NOT NULL,               -- '베트남 댕기열 임상시험이 환자 모집을 시작했습니다'
  detected_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (curr_snapshot_id, field_name)
);

-- ───────────── 뉴스·학술·규제 ─────────────
CREATE TABLE news (
  id BIGSERIAL PRIMARY KEY,
  source_id INT REFERENCES source(id),
  raw_document_id BIGINT REFERENCES raw_document(id),
  title TEXT NOT NULL, url TEXT UNIQUE NOT NULL,
  published_at TIMESTAMPTZ, collected_at TIMESTAMPTZ DEFAULT now(),
  region TEXT,                               -- KR | GLOBAL (요구사항 7)
  claim_type TEXT NOT NULL,                  -- FACT|COMPANY_CLAIM|NEWS|ANALYSIS|UNKNOWN (15)
  ai_summary_ko TEXT,                        -- LLM. raw_document_id로 추적 가능(29-5)
  severity TEXT, event_id BIGINT REFERENCES event(id),
  title_fingerprint TEXT                     -- 중복 제거(22)
);
CREATE TABLE publication (id BIGSERIAL PRIMARY KEY, doi TEXT UNIQUE, pmid TEXT,
  title TEXT, journal TEXT, published_at DATE, url TEXT, is_preprint BOOLEAN);
CREATE TABLE regulatory_event (id BIGSERIAL PRIMARY KEY, agency TEXT, event_type TEXT,
  title TEXT, url TEXT, occurred_at TIMESTAMPTZ, severity TEXT);

CREATE TABLE event (                         -- 같은 사건 묶기 (요구사항 12)
  id BIGSERIAL PRIMARY KEY,
  subject_ko TEXT NOT NULL,
  primary_source_id INT REFERENCES source(id),
  first_seen_at TIMESTAMPTZ,                 -- ★ 최초 발생 출처·시각 (요구사항 7,24)
  severity TEXT, fingerprint TEXT UNIQUE
);

CREATE TABLE watchlist (id SERIAL PRIMARY KEY, kind TEXT, ref_id INT,
  label_ko TEXT, sort_order INT);            -- DRUG|DISEASE|COMPANY|TRIAL
CREATE TABLE alert (id BIGSERIAL PRIMARY KEY, change_id BIGINT, event_id BIGINT,
  channel TEXT, severity TEXT, sent_at TIMESTAMPTZ, is_read BOOLEAN DEFAULT FALSE);
```

**설계 포인트 3가지**
1. `raw_document`는 **append-only**. UPDATE/DELETE 하지 않습니다 (요구사항 29-4).
2. `clinical_trial_change`에 **`headline_ko`를 미리 생성해 저장**합니다. 프론트는 렌더링만 하면 되고, 50~60대용 문장이 DB에서 보장됩니다.
3. `content_hash` → `snapshot_hash` **2단계 필터**로 불필요한 diff 연산을 제거합니다.

---

## 15. MVP 구현 범위 (요구사항 26항 PoC)

### Phase 0 — PoC (권장: 여기부터)

**대상**: `NCT07576868` (제프티 / 댕기열 / 베트남) + `NCT07683013` (페니트리움)

| # | 구현 항목 | 산출물 |
|---|---|---|
| 1 | Docker Compose (Postgres + API) | `docker-compose.yml` |
| 2 | 스키마 + Alembic 마이그레이션 | 14항 DDL |
| 3 | CT.gov 수집기 (`dataTimestamp` 가드 포함) | 두 임상 스냅샷 저장 |
| 4 | **Diff 엔진 + 한국어 문장 생성기** | `clinical_trial_change` 레코드 |
| 5 | **변화 감지 검증** — 과거 스냅샷을 인위적으로 주입해 `NOT_YET_RECRUITING → RECRUITING` 재현 | 테스트 통과 |
| 6 | 모바일 대시보드 1화면 | 33-2 레이아웃 |
| 7 | Telegram 알림 | 실제 수신 |

> **5번이 PoC의 진짜 목표입니다.** 데이터를 모으는 건 쉽고, **변화를 정확히 잡아내는 것**이 어렵습니다.
> NCT07683013이 현재 `NOT_YET_RECRUITING`이므로, **실제로 곧 `RECRUITING`으로 바뀔 가능성이 높은 살아있는 테스트 대상**입니다.

### Phase 1 — 국내 축 추가 (PoC 검증 후)
DART OpenAPI + 현대바이오 `/notice`·`/media` 크롤러 + 국내 RSS 5종 → 10-1절의 괴리를 실제로 메움

### Phase 2 — 해외 뉴스·규제
openFDA 폴링 + STAT/WHO RSS + Playwright(Fierce/Endpoints) + Event 클러스터링

### Phase 3 이후
Europe PMC 학술 → 질환 확장(에볼라·COVID·인플루엔자·RSV) → Watchlist 일반화 → Web Push

### MVP에서 **제외**할 것
- LLM 요약 (Phase 2 이후. 임상 변화 문장은 템플릿으로 충분하고 더 정확)
- WHO ICTRP / EU CTIS (크롤링 금지·인증 필요 — 별도 조사 후)
- 사용자 계정·인증 (개인용 단일 사용자)

---

## 16. 예상 개발 난이도

| 영역 | 난이도 | 근거 |
|---|---|---|
| CT.gov 수집 | ★☆☆☆☆ | 인증 불필요, JSON 깔끔, **이미 검증 완료** |
| DB 스키마 + 스냅샷 | ★★☆☆☆ | 설계는 위에 완료. 구현은 정형 작업 |
| **Diff 엔진** | ★★★☆☆ | 필드별 비교 로직 + `locations` 배열 diff(기관 추가 감지)가 까다로움 |
| **한국어 문장 생성** | ★★☆☆☆ | 상태 매핑 테이블 + 템플릿. **LLM보다 쉽고 정확** |
| DART / MFDS API | ★★☆☆☆ | 키 발급 후 단순. 공시 본문 파싱은 ★★★ |
| 정적 크롤링(BS4) | ★★★☆☆ | 사이트 구조 변경 시 깨짐 → 파서 단위 테스트 필수 |
| **Playwright 크롤링** | ★★★★☆ | Cloudflare 차단 대응. **가장 불안정한 영역** |
| 뉴스 중복 제거 | ★★★★☆ | 한국어 제목 유사도 + 시간 윈도우. 튜닝 반복 필요 |
| 모바일 PWA UI | ★★☆☆☆ | 요구사항 33항이 상세해 판단 여지가 적음 |
| **LLM 요약(환각 방지)** | ★★★★☆ | 출처 추적 강제 + FACT/CLAIM 분리 검증 |
| 알림(Telegram→Push) | ★☆☆☆☆ → ★★★☆☆ | Telegram은 쉬움. Web Push는 iOS 제약 있음 |

**종합 난이도: ★★★☆☆ (중상)**

- **쉬운 이유**: 핵심 소스(CT.gov)가 인증 없는 정제된 JSON API이고, 단일 사용자라 인증·확장성 문제가 없습니다.
- **어려운 이유**: 진짜 난이도는 수집이 아니라 **(a) 차단된 해외 소스 크롤링 유지보수**, **(b) 뉴스 중복 제거 정확도**, **(c) 사실/주장 분리** 세 곳에 집중되어 있습니다.
- **PoC(Phase 0)만 보면 난이도 ★★☆☆☆** 이며, 이것이 Phase 0부터 시작해야 하는 이유입니다.

---

## 부록 A. 착수 전 사용자 확인/준비 필요 항목

| # | 항목 | 필요 조치 |
|---|---|---|
| 1 | **DART OpenAPI 인증키** | opendart.fss.or.kr 무료 발급 (국내 최속 소스, 사실상 필수) |
| 2 | **공공데이터포털 인증키** | data.go.kr 무료 발급 (MFDS 임상시험 정보) |
| 3 | openFDA API 키 | 선택. 없어도 동작, 있으면 호출 한도 상향 |
| 4 | Telegram Bot 토큰 | @BotFather에서 발급 (알림용) |
| 5 | LLM API 키 | Phase 2 이후 필요 |

## 부록 B. 미해결 / 추가 조사 항목 (`UNVERIFIED`)

| # | 항목 | 현재 상태 |
|---|---|---|
| 1 | 베트남 댕기열 **제2 임상시험** 존재 여부 | CT.gov 미확인. ICTRP·베트남 자국 등록시스템 확인 필요 |
| 2 | 제프티 **국내 COVID-19 임상**의 등록번호 | CT.gov 미등록. MFDS/CRIS API로 확인 필요 |
| 3 | WHO ICTRP 벌크 데이터 이용 조건 | robots 크롤링 금지. 벌크 다운로드 약관 확인 필요 |
| 4 | EU CTIS public API 인증 방식 | HTTP 403. 공개 여부·발급 절차 확인 필요 |
| 5 | 바이오스펙테이터 RSS 경로 | 2개 경로 404 |
| 6 | "페니트리움 = CP-PCA07" 명시 공식 문서 | 2026-09-27 DART 공시로 보강. 현대바이오는 `CPPCA07 전립선암`, 페니트리움바이오는 `Penetrium 고형암`으로 각각 공시 → 같은 물질의 적응증별 프로그램으로 판단 (`ANALYSIS` 유지) |
| 7 | CT.gov API 공식 rate limit 수치 | 응답 헤더에 rate-limit 정보 없음 → 보수적 자체 제한 권장 |
