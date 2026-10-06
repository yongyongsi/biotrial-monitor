"""
영어 임상시험 용어 -> 50~60대 사용자가 바로 이해하는 한국어로 변환.

요구사항 33-4(어려운 영어 용어를 그대로 쓰지 않는다), 33-5(색상만으로 전달하지 않는다),
33-6(용어 설명), 33-7(숫자/날짜 직관적 표시) 담당 모듈.

이 모듈은 의존성이 없는 순수 함수만 포함한다. LLM을 쓰지 않으므로 환각이 발생할 수 없다.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# 임상시험 상태 (ClinicalTrials.gov overallStatus)
#   (한국어 라벨, 아이콘, 한 줄 설명)
#   아이콘 + 텍스트를 함께 제공 -> 색맹/저시력 사용자도 구분 가능 (요구사항 33-5)
# ---------------------------------------------------------------------------
STATUS_KO: dict[str, Tuple[str, str, str]] = {
    "NOT_YET_RECRUITING": ("모집 전", "⚪", "아직 환자를 모집하기 전 단계입니다."),
    "RECRUITING": ("환자 모집 중", "🟢", "현재 시험에 참여할 환자를 모집하고 있습니다."),
    "ENROLLING_BY_INVITATION": ("초청 대상자만 모집 중", "🟢", "미리 선정된 대상자만 참여할 수 있습니다."),
    "ACTIVE_NOT_RECRUITING": ("임상 진행 중 · 모집은 끝남", "🟡", "환자 모집은 끝났고 투약과 관찰이 진행 중입니다."),
    "SUSPENDED": ("일시 중단", "🔴", "임상시험이 일시적으로 멈췄습니다."),
    "TERMINATED": ("조기 종료(중단)", "🔴", "계획보다 일찍 시험이 종료되었습니다."),
    "WITHDRAWN": ("시험 취소", "🔴", "시작 전에 시험이 철회되었습니다."),
    "COMPLETED": ("임상 종료", "🔵", "계획된 시험이 모두 끝났습니다."),
    "NO_LONGER_AVAILABLE": ("제공 종료", "⚪", "더 이상 참여할 수 없습니다."),
    "APPROVED_FOR_MARKETING": ("시판 승인됨", "🔵", "허가를 받아 판매가 가능합니다."),
    "UNKNOWN": ("상태 미확인", "⚪", "등록 사이트에서 최신 상태를 확인하지 못했습니다."),
}

# 임상 단계 (요구사항 33-6: 설명을 붙인다)
PHASE_KO: dict[str, Tuple[str, str]] = {
    "EARLY_PHASE1": ("초기 1상", "사람에게 아주 적은 양을 처음 투여해 보는 단계입니다."),
    "PHASE1": ("임상 1상", "소수의 사람에게 투여해 안전성과 용량을 확인하는 단계입니다."),
    "PHASE2": ("임상 2상", "약효가 있는지와 안전성을 확인하는 단계입니다."),
    "PHASE3": ("임상 3상", "많은 환자에게 투여해 효과를 최종 확인하는 단계입니다."),
    "PHASE4": ("임상 4상", "시판 후 장기 안전성을 확인하는 단계입니다."),
    "NA": ("해당 없음", "단계 구분이 적용되지 않는 연구입니다."),
}

# 추적 필드명 -> 화면에 쓸 한국어 레이블 (요구사항 33-3: 레이블과 값을 분리)
FIELD_KO: dict[str, str] = {
    "overall_status": "임상시험 상태",
    "phase": "임상시험 단계",
    "enrollment_count": "목표 등록 인원",
    "enrollment_type": "인원 기준",
    "start_date": "시험 시작일",
    "primary_completion_date": "주요 임상 완료 예정일",
    "completion_date": "시험 전체 종료 예정일",
    "has_results": "결과 등록 여부",
    "location_count": "실시기관 수",
    "locations_added": "실시기관 추가",
    "locations_removed": "실시기관 제외",
    "location_status": "기관별 모집 상태",
    "source_last_update": "등록정보 갱신일",
}

ENROLLMENT_TYPE_KO = {"ESTIMATED": "예상", "ACTUAL": "실제"}

COUNTRY_KO = {
    "Vietnam": ("베트남", "🇻🇳"),
    "South Korea": ("대한민국", "🇰🇷"),
    "Korea, Republic of": ("대한민국", "🇰🇷"),
    "United States": ("미국", "🇺🇸"),
    "Japan": ("일본", "🇯🇵"),
    "China": ("중국", "🇨🇳"),
    "Thailand": ("태국", "🇹🇭"),
    "Singapore": ("싱가포르", "🇸🇬"),
    "India": ("인도", "🇮🇳"),
    "Brazil": ("브라질", "🇧🇷"),
    "United Kingdom": ("영국", "🇬🇧"),
}


# ---------------------------------------------------------------------------
# 조사(josa) 처리 - 자연스러운 한국어 문장을 만들기 위해 필요
# ---------------------------------------------------------------------------
_DIGIT_BATCHIM = {"0": True, "1": True, "3": True, "6": True, "7": True, "8": True,
                  "2": False, "4": False, "5": False, "9": False}


def has_batchim(word: str) -> bool:
    """마지막 글자에 받침이 있는지 판정한다."""
    if not word:
        return False
    ch = word[-1]
    if "가" <= ch <= "힣":            # 한글 음절
        return (ord(ch) - 0xAC00) % 28 != 0
    if ch.isdigit():
        return _DIGIT_BATCHIM[ch]
    if ch in ")]}»’\"'":                       # 괄호/따옴표는 그 앞 글자로 판정
        return has_batchim(word[:-1])
    return False


def _ends_with_rieul(word: str) -> bool:
    if not word:
        return False
    ch = word[-1]
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 == 8    # 종성 ㄹ
    return ch.isdigit() and ch in "17"          # 일, 칠


def josa(word: str, pair: str) -> str:
    """단어 뒤에 붙는 조사를 골라 '단어+조사' 형태로 돌려준다.

    pair 예: '은는', '이가', '을를', '와과', '으로/로'
    """
    if pair in ("으로", "로", "으로/로"):
        suffix = "로" if (not has_batchim(word) or _ends_with_rieul(word)) else "으로"
        return word + suffix
    with_b, without_b = pair[0], pair[1]
    return word + (with_b if has_batchim(word) else without_b)


# ---------------------------------------------------------------------------
# 값 -> 한국어 표시
# ---------------------------------------------------------------------------
def status_ko(code: Optional[str]) -> str:
    if not code:
        return "알 수 없음"
    return STATUS_KO.get(code, (code, "⚪", ""))[0]


def status_icon(code: Optional[str]) -> str:
    if not code:
        return "⚪"
    return STATUS_KO.get(code, (code, "⚪", ""))[1]


def status_help(code: Optional[str]) -> str:
    if not code:
        return ""
    return STATUS_KO.get(code, (code, "⚪", ""))[2]


def phase_ko(phases) -> str:
    """['PHASE2','PHASE3'] -> '임상 2상 · 3상'"""
    if not phases:
        return "단계 정보 없음"
    if isinstance(phases, str):
        phases = [phases]
    labels = [PHASE_KO.get(p, (p, ""))[0] for p in phases]
    if len(labels) == 2 and labels[0].startswith("임상") and labels[1].startswith("임상"):
        return labels[0] + " · " + labels[1].replace("임상 ", "")
    return " · ".join(labels)


def phase_help(phases) -> str:
    if not phases:
        return ""
    if isinstance(phases, str):
        phases = [phases]
    return " ".join(PHASE_KO.get(p, (p, ""))[1] for p in phases if p in PHASE_KO).strip()


def country_ko(name: Optional[str]) -> str:
    if not name:
        return ""
    label, flag = COUNTRY_KO.get(name, (name, "🌎"))
    return f"{flag} {label}"


def enrollment_ko(count: Optional[int], etype: Optional[str] = None) -> str:
    """120, 'ESTIMATED' -> '120명(예상)'  (요구사항 33-7)"""
    if count is None:
        return "정보 없음"
    text = f"{count:,}명"
    if etype in ENROLLMENT_TYPE_KO:
        text += f"({ENROLLMENT_TYPE_KO[etype]})"
    return text


def date_ko(value) -> str:
    """date/'2027-01'/'2026-04-09' -> '2027년 1월' / '2026년 4월 9일'  (요구사항 33-7)"""
    if value is None or value == "":
        return "정보 없음"
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return f"{value.year}년 {value.month}월 {value.day}일"
    s = str(value).strip()
    parts = s.split("-")
    try:
        if len(parts) == 3:
            return f"{int(parts[0])}년 {int(parts[1])}월 {int(parts[2])}일"
        if len(parts) == 2:
            return f"{int(parts[0])}년 {int(parts[1])}월"
        if len(parts) == 1 and parts[0]:
            return f"{int(parts[0])}년"
    except ValueError:
        pass
    return s


def datetime_ko(dt: datetime) -> str:
    """2026-09-27T09:15:32Z -> '2026년 9월 27일 오전 9시 15분'"""
    if dt is None:
        return "정보 없음"
    ampm = "오전" if dt.hour < 12 else "오후"
    h = dt.hour % 12 or 12
    return f"{dt.year}년 {dt.month}월 {dt.day}일 {ampm} {h}시 {dt.minute:02d}분"


def relative_ko(dt: datetime, now: Optional[datetime] = None) -> str:
    """'약 3시간 전' 같은 상대시간. 요구사항 10항(얼마나 최신인가를 가장 중요하게)."""
    if dt is None:
        return ""
    now = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    secs = (now - dt).total_seconds()
    if secs < 0:
        return "곧"
    if secs < 60:
        return "방금 전"
    mins = int(secs // 60)
    if mins < 60:
        return f"{mins}분 전"
    hours = int(secs // 3600)
    if hours < 24:
        return f"약 {hours}시간 전"
    days = int(secs // 86400)
    if days < 7:
        return f"{days}일 전"
    if days < 31:
        return f"{days // 7}주 전"
    if days < 365:
        return f"{days // 30}개월 전"
    return f"{days // 365}년 전"


def bool_ko(value: Optional[bool], true_text: str = "있음", false_text: str = "없음") -> str:
    if value is None:
        return "정보 없음"
    return true_text if value else false_text
