"""
DART 공시 분류·파싱 검증.

여기 쓰인 공시 제목과 본문은 2026-09-27 실제 DART API 응답에서 가져온 것이다.
"""
from __future__ import annotations

import pytest

from app.collectors import dart
from app.core import severity as sev


# --- 제목 분리 ---------------------------------------------------------------
def test_공시제목에서_양식명과_부제를_분리한다():
    nm = ("투자판단관련주요경영사항(임상시험계획변경승인신청)              "
          "(전립선암 치료제 CPPCA07의 1상 임상시험계획 변경승인 신청)")
    main, subtitle = dart.split_report_name(nm)
    assert main == "투자판단관련주요경영사항(임상시험계획변경승인신청)"
    assert subtitle == "전립선암 치료제 CPPCA07의 1상 임상시험계획 변경승인 신청"


def test_부제가_없어도_된다():
    main, subtitle = dart.split_report_name("반기보고서 (2026.06)")
    assert main.startswith("반기보고서")
    assert subtitle is None


# --- 승인 / 신청 구분 (실제로 틀렸던 부분) -----------------------------------
def test_양식명이_승인이면_부제에_상관없이_승인이다():
    """부제는 회사가 자유롭게 적는 칸이라 '신청' 건에도 '변경승인'이라고만 쓰는 경우가 있다.
    반대로 양식명은 금감원이 정한 것이라 신뢰할 수 있다."""
    nm = ("투자판단관련주요경영사항(임상시험계획변경승인)              "
          "(전립선암 치료제 CPPCA07의 1상 임상시험계획 변경승인)")
    etype, severity = dart.classify(nm)
    assert etype == "TRIAL_AMEND_APPROVE"
    assert severity == sev.HIGH          # 국내 식약처 승인


def test_양식명이_신청이면_신청이다():
    nm = ("투자판단관련주요경영사항(임상시험계획변경승인신청)              "
          "(전립선암 치료제 CPPCA07의 1상 임상시험계획 변경승인 신청)")
    etype, severity = dart.classify(nm)
    assert etype == "TRIAL_AMEND_APPLY"
    assert severity == sev.HIGH


def test_승인신청등결정_양식은_본문의_승인일로_가른다():
    """'임상시험계획승인신청등결정' 은 승인과 신청을 한 양식으로 쓰므로 본문을 봐야 한다."""
    nm = ("투자판단관련주요경영사항(임상시험계획승인신청등결정)              "
          "(재발성 또는 불응성 진행성 고형암 임상 2a상 임상시험계획 숭인)")

    approved = dart.classify(nm, {"agency": "미국 식품의약국 (FDA)",
                                  "approve_date": "2026-09-03"})
    assert approved == ("TRIAL_IND_APPROVE", sev.CRITICAL)

    applied = dart.classify(nm, {"agency": "미국 식품의약국 (FDA)",
                                 "apply_date": "2026-08-04"})
    assert applied == ("TRIAL_IND_APPLY", sev.HIGH)


def test_해외규제기관_승인은_국내보다_등급이_높다():
    nm = "투자판단관련주요경영사항(임상시험계획승인신청등결정)"
    fda = dart.classify(nm, {"agency": "미국 식품의약국 (FDA)", "approve_date": "2026-09-03"})
    mfds = dart.classify(nm, {"agency": "식품의약품안전처", "approve_date": "2026-09-03"})
    assert fda[1] == sev.CRITICAL        # 요구사항 13: FDA 승인 = CRITICAL
    assert mfds[1] == sev.HIGH


@pytest.mark.parametrize("nm,etype,severity", [
    ("투자판단관련주요경영사항(임상시험중단)", "TRIAL_HALT", sev.CRITICAL),
    ("투자판단관련주요경영사항(임상시험결과)", "TRIAL_RESULT", sev.CRITICAL),
    ("주식등의대량보유상황보고서(일반)", "CAPITAL", sev.LOW),
    ("주요사항보고서(전환사채권발행결정)", "CAPITAL", sev.MEDIUM),
    ("반기보고서 (2026.06)", "PERIODIC", sev.LOW),
])
def test_기타_공시_분류(nm, etype, severity):
    assert dart.classify(nm) == (etype, severity)


# --- 본문 파싱 ---------------------------------------------------------------
REAL_DOC = """
<p>1. 제목</p>
<p>재발성 또는 불응성 진행성 고형암 환자를 대상으로 한 제2a상 임상시험계획(IND) 미국 FDA 승인</p>
<p>2. 주요내용</p>
<p>1) 임상시험명칭</p><p>재발성 또는 불응성 진행성 고형암 2a상 임상시험</p>
<p>2) 임상시험단계</p><p>임상 2a상</p>
<p>3) 임상시험승인기관</p><p>미국 식품의약국 (FDA)</p>
<p>4) 임상시험실시국가</p><p>미국</p>
<p>5) 임상시험실시기관</p><p>미국 3개 기관</p>
<p>6) 대상질환</p><p>재발성 또는 불응성 진행성 고형암</p>
<p>7) 신청일</p><p>2026-08-04</p>
<p>8) 승인일(결정일)</p><p>2026-09-03</p>
<p>9) 등록번호</p><p>IND 183600</p>
<p>15) 목표 시험대상자 수</p><p>최소 3명 ~ 최대 18명</p>
<p>16) 예상종료일</p><p>2028-09-03</p>
"""


def test_본문에서_임상_상세를_뽑아낸다():
    d = dart.parse_clinical_document(REAL_DOC)
    assert d["agency"] == "미국 식품의약국 (FDA)"
    assert d["country"] == "미국"
    assert d["sites"] == "미국 3개 기관"
    assert d["registration_no"] == "IND 183600"
    assert d["apply_date"] == "2026-08-04"
    assert d["approve_date"] == "2026-09-03"
    assert d["expected_end"] == "2028-09-03"


def test_목표인원_범위를_첫숫자로_뭉개지_않는다():
    """'최소 3명 ~ 최대 18명' 을 3 으로 저장하면 사실이 왜곡된다."""
    d = dart.parse_clinical_document(REAL_DOC)
    assert d["enrollment"] == "최소 3명 ~ 최대 18명"
    assert d["enrollment"] != 3


def test_빈값은_저장하지_않는다():
    d = dart.parse_clinical_document(
        "<p>1) 예상종료일</p><p>-</p><p>2) 대상질환</p><p>고형암</p>")
    assert "expected_end" not in d
    assert d["disease"] == "고형암"


# --- 표시 문자열 -------------------------------------------------------------
def test_임상단계_표기를_짧게_만든다():
    assert dart.phase_short("한국 식약처 임상시험 제1상") == "임상 1상"
    assert dart.phase_short("임상 2a상") == "임상 2a상"
    assert dart.phase_short("해당 없음") is None


def test_승인기관을_한국어로_정리한다():
    assert dart.agency_ko("미국 식품의약국 (FDA)") == "미국 FDA"
    assert dart.agency_ko("식품의약품안전처") == "식약처"
    assert dart.agency_ko("베트남 보건부") == "베트남 보건부"


def test_FDA승인_헤드라인():
    details = dart.parse_clinical_document(REAL_DOC)
    h = dart.build_headline("페니트리움바이오", "TRIAL_IND_APPROVE", None, details, "페니트리움")
    assert h == ("페니트리움 재발성 또는 불응성 진행성 고형암 임상 2a상 "
                 "임상시험계획이 미국 FDA 승인을 받았습니다")


def test_신청_헤드라인의_조사가_올바르다():
    """'현대바이오사이언스이(가)' 같은 표기가 나오면 안 된다."""
    for company in ("현대바이오사이언스", "페니트리움바이오", "한미약품"):
        h = dart.build_headline(company, "TRIAL_AMEND_APPLY", "부제", {}, "제프티")
        assert "이(가)" not in h, h
        assert h.endswith("신청했습니다")
    assert dart.build_headline("현대바이오사이언스", "TRIAL_AMEND_APPLY", None, {}, "제프티") \
        .startswith("현대바이오사이언스가")


def test_모든_헤드라인이_완전한_문장이다():
    for etype in dart.EVENT_KO:
        h = dart.build_headline("현대바이오사이언스", etype, "부제", {}, "제프티")
        assert h.endswith("다") or h.endswith("니다") or "—" in h, (etype, h)
        assert "이(가)" not in h, (etype, h)
