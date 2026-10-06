"""
변화 감지 엔진 검증 (요구사항 9, 11 / PoC 항목 5).

여기서 검증하는 것은 '데이터를 가져왔는가'가 아니라
'달라진 것을 정확히 집어냈는가, 그리고 50~60대가 읽을 수 있는 문장이 나왔는가' 이다.
"""
from __future__ import annotations

import pytest

from app.core.diff import (
    FieldChange,
    diff_snapshots,
    overall_severity,
    snapshot_hash,
)
from app.core import severity as sev


# --- 실제 데이터 기반 픽스처 -------------------------------------------------
# NCT07576868 (제프티/댕기열/베트남) 2026-09-27 조회 실측값
XAFTY_CONTEXT = {"drug_ko": "제프티", "disease_ko": "댕기열"}

XAFTY_SNAPSHOT = {
    "overall_status": "RECRUITING",
    "phase": ["PHASE2", "PHASE3"],
    "enrollment_count": 210,
    "enrollment_type": "ESTIMATED",
    "start_date": "2026-04-09",
    "primary_completion_date": "2027-01",
    "completion_date": "2027-05",
    "has_results": False,
    "source_last_update": "2026-07-10",
    "locations": [
        {"facility": "The National Hospital of Tropical Diseases (NHTD)",
         "city": "Hanoi", "country": "Vietnam", "status": "RECRUITING"},
        {"facility": "Tien Giang Provincial General Hospital",
         "city": "Mỹ Tho", "country": "Vietnam", "status": "RECRUITING"},
    ],
}


def _by_field(changes, field):
    for c in changes:
        if c.field_name == field:
            return c
    return None


# --- 기본 동작 ---------------------------------------------------------------
def test_최초수집은_변화를_만들지_않는다():
    assert diff_snapshots(None, XAFTY_SNAPSHOT, XAFTY_CONTEXT) == []


def test_동일한_스냅샷은_변화가_없다():
    assert diff_snapshots(XAFTY_SNAPSHOT, dict(XAFTY_SNAPSHOT), XAFTY_CONTEXT) == []


def test_동일한_스냅샷은_해시가_같다():
    assert snapshot_hash(XAFTY_SNAPSHOT) == snapshot_hash(dict(XAFTY_SNAPSHOT))


def test_source_last_update만_바뀌면_해시는_그대로다():
    """내용이 같은데 갱신일만 바뀐 경우를 '변화 없음'으로 처리해야 diff 비용이 줄어든다."""
    later = dict(XAFTY_SNAPSHOT, source_last_update="2026-09-20")
    assert snapshot_hash(XAFTY_SNAPSHOT) == snapshot_hash(later)


# --- ★ 핵심 시나리오: 모집 전 -> 환자 모집 중 --------------------------------
def test_모집전에서_모집중으로_바뀌면_HIGH로_감지한다():
    """NCT07683013(페니트리움)이 실제로 곧 겪을 변화.

    CT.gov는 현재 NOT_YET_RECRUITING 이지만 뉴스상 이미 첫 투약이 이루어졌다.
    """
    prev = dict(XAFTY_SNAPSHOT, overall_status="NOT_YET_RECRUITING")
    changes = diff_snapshots(prev, XAFTY_SNAPSHOT, XAFTY_CONTEXT)

    status = _by_field(changes, "overall_status")
    assert status is not None
    assert status.old_value == "NOT_YET_RECRUITING"
    assert status.new_value == "RECRUITING"
    assert status.old_value_ko == "모집 전"
    assert status.new_value_ko == "환자 모집 중"
    assert status.severity == sev.HIGH
    # 요구사항 33-8: 영어 원문 제목이 아니라 '무슨 일이 있었는지'가 보여야 한다
    assert status.headline_ko == "제프티 댕기열 임상시험이 환자 모집을 시작했습니다"


def test_요구사항11_예시_시나리오를_그대로_재현한다():
    """요구사항 11항의 예시:
       Status     Recruiting -> Active, not recruiting
       Enrollment 100        -> 120
       Completion 2026-12    -> 2027-02
    """
    prev = dict(XAFTY_SNAPSHOT, overall_status="RECRUITING",
                enrollment_count=100, completion_date="2026-12")
    curr = dict(XAFTY_SNAPSHOT, overall_status="ACTIVE_NOT_RECRUITING",
                enrollment_count=120, completion_date="2027-02")

    changes = diff_snapshots(prev, curr, XAFTY_CONTEXT)
    fields = {c.field_name for c in changes}
    assert fields == {"overall_status", "enrollment_count", "completion_date"}

    status = _by_field(changes, "overall_status")
    assert status.new_value_ko == "임상 진행 중 · 모집은 끝남"
    assert status.headline_ko == "제프티 댕기열 임상시험의 환자 모집이 끝나고 임상이 진행 중입니다"

    enroll = _by_field(changes, "enrollment_count")
    assert enroll.old_value_ko == "100명(예상)"
    assert enroll.new_value_ko == "120명(예상)"
    assert enroll.severity == sev.HIGH

    comp = _by_field(changes, "completion_date")
    assert comp.old_value_ko == "2026년 12월"
    assert comp.new_value_ko == "2027년 2월"
    assert "2026년 12월에서 2027년 2월로 바뀌었습니다" in comp.headline_ko

    assert overall_severity(changes) == sev.HIGH


# --- CRITICAL 시나리오 --------------------------------------------------------
@pytest.mark.parametrize("status,expected_word", [
    ("TERMINATED", "조기 종료"),
    ("SUSPENDED", "일시 중단"),
    ("WITHDRAWN", "취소"),
])
def test_중단_취소는_CRITICAL이다(status, expected_word):
    curr = dict(XAFTY_SNAPSHOT, overall_status=status)
    changes = diff_snapshots(XAFTY_SNAPSHOT, curr, XAFTY_CONTEXT)
    change = _by_field(changes, "overall_status")
    assert change.severity == sev.CRITICAL
    assert expected_word in change.headline_ko


def test_결과등록은_CRITICAL이다():
    """Results Posted FALSE -> TRUE. 투자 관점에서 가장 영향이 큰 레지스트리 이벤트."""
    curr = dict(XAFTY_SNAPSHOT, has_results=True)
    changes = diff_snapshots(XAFTY_SNAPSHOT, curr, XAFTY_CONTEXT)
    change = _by_field(changes, "has_results")
    assert change.severity == sev.CRITICAL
    assert change.headline_ko == "제프티 댕기열 임상시험의 결과가 공식 등록되었습니다"
    assert change.new_value_ko == "결과 등록됨"


def test_임상종료는_HIGH다():
    curr = dict(XAFTY_SNAPSHOT, overall_status="COMPLETED")
    change = _by_field(diff_snapshots(XAFTY_SNAPSHOT, curr, XAFTY_CONTEXT), "overall_status")
    assert change.severity == sev.HIGH
    assert change.headline_ko == "제프티 댕기열 임상시험이 종료되었습니다"


# --- 실시기관 변화 (요구사항 9) ----------------------------------------------
def test_실시기관_추가를_감지한다():
    curr = dict(XAFTY_SNAPSHOT)
    curr["locations"] = XAFTY_SNAPSHOT["locations"] + [
        {"facility": "Cho Ray Hospital", "city": "Ho Chi Minh City",
         "country": "Vietnam", "status": "NOT_YET_RECRUITING"},
    ]
    change = _by_field(diff_snapshots(XAFTY_SNAPSHOT, curr, XAFTY_CONTEXT), "locations_added")
    assert change is not None
    assert change.severity == sev.HIGH
    assert change.old_value_ko == "2곳"
    assert change.new_value_ko == "3곳"
    assert change.headline_ko == "제프티 댕기열 임상시험의 실시기관 1곳이 새로 추가되었습니다"
    # 긴 영문 기관명은 제목이 아니라 상세에 들어간다 (요구사항 33-8)
    assert "Cho Ray Hospital" not in change.headline_ko
    assert "Cho Ray Hospital" in change.detail_ko


def test_실시기관_제외를_감지한다():
    curr = dict(XAFTY_SNAPSHOT)
    curr["locations"] = XAFTY_SNAPSHOT["locations"][:1]
    change = _by_field(diff_snapshots(XAFTY_SNAPSHOT, curr, XAFTY_CONTEXT), "locations_removed")
    assert change is not None
    assert "Tien Giang" in change.detail_ko


def test_기관별_모집상태_변화를_감지한다():
    curr = dict(XAFTY_SNAPSHOT)
    curr["locations"] = [
        dict(XAFTY_SNAPSHOT["locations"][0], status="ACTIVE_NOT_RECRUITING"),
        XAFTY_SNAPSHOT["locations"][1],
    ]
    change = _by_field(diff_snapshots(XAFTY_SNAPSHOT, curr, XAFTY_CONTEXT), "location_status")
    assert change is not None
    assert change.severity == sev.MEDIUM
    assert "National Hospital of Tropical Diseases" in change.headline_ko


def test_기관수만_같으면_교체도_추가제외로_잡힌다():
    """기관 수는 2곳으로 같지만 한 곳이 다른 곳으로 바뀐 경우."""
    curr = dict(XAFTY_SNAPSHOT)
    curr["locations"] = [
        XAFTY_SNAPSHOT["locations"][0],
        {"facility": "Cho Ray Hospital", "city": "Ho Chi Minh City",
         "country": "Vietnam", "status": "RECRUITING"},
    ]
    changes = diff_snapshots(XAFTY_SNAPSHOT, curr, XAFTY_CONTEXT)
    assert _by_field(changes, "locations_added") is not None
    assert _by_field(changes, "locations_removed") is not None


# --- 단계/날짜 ---------------------------------------------------------------
def test_임상단계_변경을_감지한다():
    prev = dict(XAFTY_SNAPSHOT, phase=["PHASE2"])
    change = _by_field(diff_snapshots(prev, XAFTY_SNAPSHOT, XAFTY_CONTEXT), "phase")
    assert change.old_value_ko == "임상 2상"
    assert change.new_value_ko == "임상 2상 · 3상"
    assert change.severity == sev.HIGH


def test_주요완료예정일_변경을_감지한다():
    curr = dict(XAFTY_SNAPSHOT, primary_completion_date="2027-03")
    change = _by_field(diff_snapshots(XAFTY_SNAPSHOT, curr, XAFTY_CONTEXT), "primary_completion_date")
    assert change.severity == sev.HIGH
    assert change.headline_ko == (
        "제프티 댕기열 임상시험의 주요 완료 예정일이 2027년 1월에서 2027년 3월로 바뀌었습니다"
    )


def test_등록인원이_실제로_확정되면_HIGH다():
    curr = dict(XAFTY_SNAPSHOT, enrollment_type="ACTUAL", enrollment_count=215)
    changes = diff_snapshots(XAFTY_SNAPSHOT, curr, XAFTY_CONTEXT)
    assert _by_field(changes, "enrollment_type").severity == sev.HIGH
    assert _by_field(changes, "enrollment_type").headline_ko == (
        "제프티 댕기열 임상시험의 등록 인원이 실제 인원으로 확정되었습니다"
    )


def test_등록정보_갱신일만_바뀌면_LOW다():
    curr = dict(XAFTY_SNAPSHOT, source_last_update="2026-09-25")
    changes = diff_snapshots(XAFTY_SNAPSHOT, curr, XAFTY_CONTEXT)
    assert len(changes) == 1
    assert changes[0].severity == sev.LOW
    assert overall_severity(changes) == sev.LOW


# --- 문장 품질 (요구사항 33-4: 영어 용어를 그대로 쓰지 않는다) ---------------
def test_모든_헤드라인에_영어_상태코드가_남아있지_않다():
    prev = dict(XAFTY_SNAPSHOT, overall_status="NOT_YET_RECRUITING",
                enrollment_count=100, phase=["PHASE2"], has_results=False,
                primary_completion_date="2026-12")
    curr = dict(XAFTY_SNAPSHOT, has_results=True)
    changes = diff_snapshots(prev, curr, XAFTY_CONTEXT)
    assert len(changes) >= 4
    banned = ["RECRUITING", "NOT_YET", "ACTIVE_NOT", "TERMINATED",
              "PHASE", "ESTIMATED", "ACTUAL", "Status", "Enrollment"]
    for c in changes:
        for word in banned:
            assert word not in c.headline_ko, f"{c.field_name}: {c.headline_ko}"


def test_헤드라인은_모두_다로_끝나는_완전한_문장이다():
    prev = dict(XAFTY_SNAPSHOT, overall_status="NOT_YET_RECRUITING", enrollment_count=100)
    changes = diff_snapshots(prev, XAFTY_SNAPSHOT, XAFTY_CONTEXT)
    assert changes
    for c in changes:
        assert c.headline_ko.endswith("다"), c.headline_ko
        assert len(c.headline_ko) >= 10


def test_약물정보가_없어도_문장이_만들어진다():
    prev = dict(XAFTY_SNAPSHOT, overall_status="NOT_YET_RECRUITING")
    changes = diff_snapshots(prev, XAFTY_SNAPSHOT, None)
    assert changes[0].headline_ko == "임상시험이 환자 모집을 시작했습니다"
