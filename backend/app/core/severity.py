"""
변화의 중요도 분류 (요구사항 13).

전부 규칙 기반이다. LLM을 쓰지 않으므로 같은 입력에 항상 같은 결과가 나오고,
왜 그렇게 분류됐는지 코드로 설명할 수 있다. 투자 판단에 쓰이는 앱이므로 중요한 성질이다.
"""
from __future__ import annotations

CRITICAL = "CRITICAL"
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

# (한국어 라벨, 아이콘) - 색상만으로 전달하지 않는다 (요구사항 33-5)
SEVERITY_KO = {
    CRITICAL: ("매우 중요", "🔴"),
    HIGH: ("중요", "🟠"),
    MEDIUM: ("참고", "🟡"),
    LOW: ("일반", "⚪"),
}

SEVERITY_ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3}

# 임상시험이 멈추거나 취소된 상태 -> 투자 관점에서 가장 위험한 신호
HALT_STATUSES = {"TERMINATED", "SUSPENDED", "WITHDRAWN"}


def severity_ko(code: str) -> str:
    return SEVERITY_KO.get(code, (code, "⚪"))[0]


def severity_icon(code: str) -> str:
    return SEVERITY_KO.get(code, (code, "⚪"))[1]


def worst(severities) -> str:
    """여러 변화 중 가장 심각한 등급을 고른다."""
    items = [s for s in severities if s in SEVERITY_ORDER]
    if not items:
        return LOW
    return min(items, key=lambda s: SEVERITY_ORDER[s])


def classify(field_name: str, old, new) -> str:
    """필드 변화 1건의 중요도를 판정한다."""
    if field_name == "overall_status":
        if new in HALT_STATUSES:
            return CRITICAL          # 중단/취소 = 요구사항 13 CRITICAL
        return HIGH                  # 그 외 모든 상태 변경 = HIGH

    if field_name == "has_results":
        # 결과가 공식 등록되는 순간. 투자 관점에서 레지스트리 이벤트 중 영향이 가장 크다.
        # 요구사항 13은 '결과 등록'을 HIGH, '임상 결과 발표'를 CRITICAL로 두는데
        # CT.gov의 results posting은 후자에 해당하므로 CRITICAL로 올린다.
        return CRITICAL if (new and not old) else HIGH

    if field_name == "enrollment_type":
        # ESTIMATED -> ACTUAL 은 목표치가 실측치로 확정됐다는 뜻 = 사실상 모집 완료 신호
        return HIGH if (old == "ESTIMATED" and new == "ACTUAL") else MEDIUM

    if field_name in {
        "phase",
        "enrollment_count",
        "primary_completion_date",
        "completion_date",
        "locations_added",
        "locations_removed",
    }:
        return HIGH

    if field_name in {"start_date", "location_status"}:
        return MEDIUM

    if field_name in {"source_last_update", "location_count"}:
        return LOW

    return MEDIUM
