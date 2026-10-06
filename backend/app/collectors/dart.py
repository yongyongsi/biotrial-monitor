"""
DART 전자공시 수집기 (수집 Level 1: 공식 API).

국내에서 가장 빠른 소스다. 법적으로 공시 의무가 있어 기업이 늦출 수 없고,
ClinicalTrials.gov 보다 몇 주~몇 달 앞선다 (docs/00_RESEARCH.md 10-2 참조).

실제로 2026-09-03 공시된 페니트리움의 미국 FDA IND 183600 승인은
2026-09-27 현재까지 ClinicalTrials.gov 에서 검색조차 되지 않는다.

세 개의 API 를 쓴다.
    list.json      공시 목록 (제목까지만)
    document.xml   공시 본문 (zip 안의 XML) - IND 번호/기관수/목표인원이 여기에만 있다
    corpCode.xml   기업 고유번호 (최초 1회, 약 3.6MB)
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings
from app.core import severity as sev
from app.core.korean import josa

log = logging.getLogger(__name__)

API_BASE = "https://opendart.fss.or.kr/api"
VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
SOURCE_CODE = "opendart"

STATUS_KO = {
    "000": "정상",
    "010": "등록되지 않은 인증키",
    "011": "사용할 수 없는 인증키",
    "013": "조회된 데이터가 없음",
    "020": "요청 제한 초과",
    "100": "필드 부적절",
    "800": "시스템 점검 중",
    "900": "정의되지 않은 오류",
}


class DartError(RuntimeError):
    def __init__(self, status: str, message: str = ""):
        self.status = status
        super().__init__(f"DART 오류 {status}: {STATUS_KO.get(status, '알 수 없음')} {message}".strip())


def _client() -> httpx.Client:
    return httpx.Client(timeout=30.0, follow_redirects=True,
                        headers={"User-Agent": settings.user_agent})


# ---------------------------------------------------------------------------
# API 호출
# ---------------------------------------------------------------------------
def fetch_list(corp_code: str, bgn_de: str, end_de: str,
               page_count: int = 100) -> List[Dict[str, Any]]:
    """기간 내 공시 목록. 013(데이터 없음)은 오류가 아니라 빈 목록으로 돌려준다."""
    if not settings.opendart_api_key:
        raise DartError("010", "OPENDART_API_KEY 가 설정되지 않았습니다")
    with _client() as c:
        r = c.get(f"{API_BASE}/list.json", params={
            "crtfc_key": settings.opendart_api_key,
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_count": page_count,
        })
        r.raise_for_status()
        data = r.json()
    status = data.get("status")
    if status == "013":
        return []
    if status != "000":
        raise DartError(status or "900", data.get("message", ""))
    return data.get("list") or []


def fetch_document_text(rcept_no: str) -> Optional[str]:
    """공시 본문. zip 안의 XML 이며 인코딩이 utf-8/euc-kr 로 섞여 있다."""
    if not settings.opendart_api_key:
        return None
    try:
        with _client() as c:
            r = c.get(f"{API_BASE}/document.xml", params={
                "crtfc_key": settings.opendart_api_key,
                "rcept_no": rcept_no,
            })
            r.raise_for_status()
            raw = r.content
        if not raw.startswith(b"PK"):          # zip 이 아니면 오류 응답
            return None
        z = zipfile.ZipFile(io.BytesIO(raw))
        blob = z.read(z.namelist()[0])
    except Exception as exc:                    # noqa: BLE001
        log.warning("공시 본문 조회 실패 %s: %s", rcept_no, exc)
        return None

    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return blob.decode(enc)
        except UnicodeDecodeError:
            continue
    return blob.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 본문 파싱
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_NUM_KEY_RE = re.compile(r"^\d+\)\s*(.+?)\s*$")
_SEC_KEY_RE = re.compile(r"^\d+\.\s*(.+?)\s*$")

# 공시 본문의 항목명 -> 우리 필드명
FIELD_MAP = {
    "임상시험명칭": "trial_name",
    "임상시험단계": "phase",
    "임상시험승인기관": "agency",
    "임상시험실시국가": "country",
    "임상시험실시기관": "sites",
    "대상질환": "disease",
    "신청일": "apply_date",
    "승인일(결정일)": "approve_date",
    "승인일": "approve_date",
    "결정일": "approve_date",
    "등록번호": "registration_no",
    "임상시험기간": "duration",
    "목표시험대상자수": "enrollment",
    "예상종료일": "expected_end",
}


def _clean_lines(xml_text: str) -> List[str]:
    import html as html_mod
    body = _TAG_RE.sub("\n", xml_text)
    body = html_mod.unescape(body)
    out: List[str] = []
    for line in body.split("\n"):
        line = line.strip()
        if not line or line.startswith((".", "/*", "*/", "}", "{")) or ":" in line[:20] and "{" in line:
            continue
        if out and out[-1] == line:
            continue
        out.append(line)
    return out


def parse_clinical_document(xml_text: str) -> Dict[str, Any]:
    """`투자판단관련주요경영사항` 본문에서 임상 상세를 뽑아낸다.

    본문은 `1) 임상시험명칭` / 다음 줄에 값 형태의 표다.
    """
    lines = _clean_lines(xml_text)
    details: Dict[str, Any] = {}
    current: Optional[str] = None
    buf: List[str] = []

    def flush() -> None:
        if current and buf:
            details.setdefault(current, " ".join(buf).strip())

    for line in lines:
        m = _NUM_KEY_RE.match(line) or _SEC_KEY_RE.match(line)
        if m:
            flush()
            key = m.group(1).replace(" ", "")
            current = FIELD_MAP.get(key)
            buf = []
            continue
        if current:
            if len(buf) < 6:                   # 목적/통계분석 같은 긴 항목은 앞부분만
                buf.append(line)
    flush()

    # 날짜 정리
    for k in ("apply_date", "approve_date", "expected_end"):
        if k in details:
            m = re.search(r"(\d{4})[-.\s]*(\d{1,2})[-.\s]*(\d{1,2})", str(details[k]))
            details[k] = (f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                          if m else str(details[k]).strip())

    # 목표 인원은 '최소 3명 ~ 최대 18명' 같은 범위로 적히는 경우가 많다.
    # 첫 숫자만 떼어내면 사실이 왜곡되므로 원문 문자열을 그대로 둔다.
    if "enrollment" in details:
        details["enrollment"] = " ".join(str(details["enrollment"]).split())

    # '-', '해당사항 없음' 같은 빈 값 제거
    EMPTY = {"", "-", "–", "해당없음", "해당사항없음", "해당 사항 없음", "미정", "N/A"}
    return {k: v for k, v in details.items()
            if v not in (None, [], ) and str(v).strip() not in EMPTY}


# ---------------------------------------------------------------------------
# 분류
# ---------------------------------------------------------------------------
EVENT_KO = {
    "TRIAL_IND_APPROVE": "임상시험 승인",
    "TRIAL_IND_APPLY": "임상시험 승인 신청",
    "TRIAL_AMEND_APPROVE": "임상시험 변경승인",
    "TRIAL_AMEND_APPLY": "임상시험 변경승인 신청",
    "TRIAL_RESULT": "임상시험 결과",
    "TRIAL_HALT": "임상시험 중단",
    "PRODUCT_APPROVAL": "품목허가",
    "LICENSE_DEAL": "기술이전·계약",
    "CAPITAL": "자금·지분 변동",
    "PERIODIC": "정기보고서",
    "OTHER": "기타 공시",
}

# 해외 규제기관은 국내 식약처보다 파급력이 크다 (요구사항 13: FDA 승인/거절 = CRITICAL)
FOREIGN_AGENCY_PAT = re.compile(
    r"FDA|식품의약국|EMA|유럽의약품|PMDA|NMPA|MHRA|TGA|Health\s*Canada", re.I)

AGENCY_KO = [
    (re.compile(r"미국\s*식품의약국|FDA", re.I), "미국 FDA"),
    (re.compile(r"EMA|유럽의약품청", re.I), "유럽 EMA"),
    (re.compile(r"식품의약품안전처|식약처|MFDS", re.I), "식약처"),
    (re.compile(r"PMDA|일본", re.I), "일본 PMDA"),
    (re.compile(r"NMPA|중국", re.I), "중국 NMPA"),
]


_PHASE_RE = re.compile(r"제?\s*(\d+\s*[a-zA-Z]?)\s*상")


def phase_short(raw: Optional[str]) -> Optional[str]:
    """'한국 식약처 임상시험 제1상' -> '임상 1상'. 못 찾으면 None."""
    if not raw:
        return None
    m = _PHASE_RE.search(str(raw))
    if not m:
        return None
    return "임상 " + m.group(1).replace(" ", "") + "상"


def agency_ko(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    for pat, label in AGENCY_KO:
        if pat.search(raw):
            return label
    return raw.strip()


def split_report_name(report_nm: str) -> Tuple[str, Optional[str]]:
    """'투자판단관련주요경영사항(임상시험계획승인신청등결정)      (부제)' 를 나눈다."""
    text = report_nm.strip()
    parts = re.split(r"\s{2,}", text, maxsplit=1)
    main = parts[0].strip()
    subtitle = parts[1].strip() if len(parts) > 1 else None
    if subtitle:
        subtitle = subtitle.strip()
        while subtitle.startswith("(") and subtitle.endswith(")"):
            subtitle = subtitle[1:-1].strip()
    return main, subtitle


def _form_name(main: str) -> str:
    """'투자판단관련주요경영사항(임상시험계획변경승인신청)' -> '임상시험계획변경승인신청'"""
    m = re.search(r"\(([^()]*)\)\s*$", main.strip())
    return (m.group(1) if m else main).replace(" ", "")


def classify(report_nm: str, details: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """(event_type, severity) 판정.

    승인인지 신청인지는 **공시 양식명**(괄호 안)으로 판단한다.
    부제는 회사가 자유롭게 적는 칸이라 '변경승인 신청' 건에도 '변경승인'이라고만 쓰는 등
    표기가 일정하지 않아 신뢰할 수 없다.
    """
    main, subtitle = split_report_name(report_nm)
    form = _form_name(main)
    text = f"{main} {subtitle or ''}"
    details = details or {}

    if any(k in text for k in ("임상시험", "임상")):
        amend = "변경" in form or "변경" in text
        if "등결정" in form:
            # 승인/신청을 한 양식으로 함께 쓰는 형태 -> 본문의 승인일로 가른다
            approved = bool(details.get("approve_date"))
        elif form.endswith("신청"):
            approved = False
        elif "승인" in form:
            approved = True
        else:
            approved = bool(details.get("approve_date"))
        if any(k in text for k in ("중단", "중지", "자진취하", "철회", "실패")):
            return "TRIAL_HALT", sev.CRITICAL
        if any(k in text for k in ("결과", "탑라인", "톱라인")):
            return "TRIAL_RESULT", sev.CRITICAL

        agency = details.get("agency") or ""
        foreign = bool(FOREIGN_AGENCY_PAT.search(agency or text))
        if approved:
            etype = "TRIAL_AMEND_APPROVE" if amend else "TRIAL_IND_APPROVE"
            # 해외 규제기관 승인은 CRITICAL, 국내는 HIGH
            return etype, (sev.CRITICAL if foreign else sev.HIGH)
        etype = "TRIAL_AMEND_APPLY" if amend else "TRIAL_IND_APPLY"
        return etype, sev.HIGH

    if any(k in text for k in ("품목허가", "제조판매품목", "시판허가")):
        return "PRODUCT_APPROVAL", sev.CRITICAL
    if any(k in text for k in ("기술이전", "라이선스", "공급계약", "판매계약", "단일판매")):
        return "LICENSE_DEAL", sev.HIGH
    if any(k in text for k in ("유상증자", "전환사채", "신주인수권", "무상증자", "주식매수")):
        return "CAPITAL", sev.MEDIUM
    if any(k in text for k in ("대량보유", "특정증권등소유", "임원ㆍ주요주주", "임원·주요주주")):
        return "CAPITAL", sev.LOW
    if any(k in text for k in ("사업보고서", "반기보고서", "분기보고서", "감사보고서")):
        return "PERIODIC", sev.LOW
    return "OTHER", sev.LOW


# ---------------------------------------------------------------------------
# 한국어 헤드라인 (템플릿 기반 - LLM 미사용)
# ---------------------------------------------------------------------------
def build_headline(company_ko: str, event_type: str, subtitle: Optional[str],
                   details: Optional[Dict[str, Any]] = None,
                   drug_ko: Optional[str] = None) -> str:
    details = details or {}
    ag = agency_ko(details.get("agency"))
    phase = phase_short(details.get("phase"))
    disease = (details.get("disease") or "").strip()
    if len(disease) > 30:                      # 대상질환이 문장처럼 긴 경우가 있다
        disease = disease[:30].rstrip(" ,·") + "…"

    subject_bits = [b for b in (drug_ko, disease, phase) if b]
    subject = " ".join(subject_bits) if subject_bits else (subtitle or "임상시험")
    company_j = josa(company_ko, "이가")

    if event_type in ("TRIAL_IND_APPROVE", "TRIAL_AMEND_APPROVE"):
        what = "변경승인" if event_type.endswith("AMEND_APPROVE") else "승인"
        if ag:
            return f"{subject} 임상시험계획이 {ag} {josa(what, '을를')} 받았습니다"
        return f"{subject} 임상시험계획이 {josa(what, '을를')} 받았습니다"

    if event_type in ("TRIAL_IND_APPLY", "TRIAL_AMEND_APPLY"):
        what = "변경승인" if event_type.endswith("AMEND_APPLY") else "승인"
        where = f"{ag}에 " if ag else ""
        return f"{company_j} {subject} 임상시험계획 {what}을 {where}신청했습니다"

    if event_type == "TRIAL_HALT":
        return f"{subject} 임상시험이 중단되었습니다"
    if event_type == "TRIAL_RESULT":
        return f"{subject} 임상시험 결과가 발표되었습니다"
    if event_type == "PRODUCT_APPROVAL":
        return f"{company_ko}의 {subject} 품목허가가 나왔습니다"
    if event_type == "LICENSE_DEAL":
        return f"{company_j} 기술이전·공급계약을 공시했습니다"
    if event_type == "CAPITAL":
        return f"{company_ko}의 자금·지분 관련 공시가 올라왔습니다"
    if event_type == "PERIODIC":
        return f"{company_ko}의 정기보고서가 제출되었습니다"
    return f"{company_j} 새 공시를 등록했습니다" + (f" — {subtitle}" if subtitle else "")


def build_detail(subtitle: Optional[str], details: Optional[Dict[str, Any]],
                 fallback: Optional[str] = None) -> str:
    """카드 안쪽에 보여줄 '레이블: 값' 목록 (요구사항 33-3)."""
    details = details or {}
    rows: List[str] = []
    label_of = [  # noqa: E126
        ("agency", "승인기관"), ("country", "실시국가"), ("sites", "실시기관"),
        ("phase", "임상시험 단계"), ("disease", "대상질환"),
        ("registration_no", "등록번호"), ("apply_date", "신청일"),
        ("approve_date", "승인일"), ("enrollment", "목표 인원"),
        ("expected_end", "예상 종료일"),
    ]
    if not details and not subtitle:
        return fallback or ""
    for key, label in label_of:
        val = details.get(key)
        if val in (None, "", []):
            continue
        if key == "agency":
            val = agency_ko(str(val))
        if key == "phase":
            val = phase_short(val) or val
        rows.append(f"{label}: {val}")
    if subtitle:
        rows.insert(0, subtitle)
    return "\n".join(rows)


def to_date(yyyymmdd: str) -> date:
    return datetime.strptime(yyyymmdd, "%Y%m%d").date()


def default_range(days: int = 365) -> Tuple[str, str]:
    today = date.today()
    return (today - timedelta(days=days)).strftime("%Y%m%d"), today.strftime("%Y%m%d")
