"""
기간 필터 검증.

'오늘'은 최근 24시간이 아니라 한국시간 자정부터여야 한다.
아침에 앱을 열었을 때 어제 저녁 소식이 섞여 나오면 '오늘 무슨 일이 있었나'를 알 수 없다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.api.routes import _period

KST = ZoneInfo("Asia/Seoul")


def test_오늘은_한국시간_자정부터다():
    since, label = _period(0)
    assert label == "오늘"
    since_kst = since.astimezone(KST)
    assert (since_kst.hour, since_kst.minute, since_kst.second) == (0, 0, 0)
    assert since_kst.date() == datetime.now(KST).date()


def test_오늘은_24시간_전이_아니다():
    """지금이 자정 직후라면 '오늘'과 '24시간 전'은 크게 달라야 한다."""
    since, _ = _period(0)
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    assert since > day_ago or since.astimezone(KST).hour == 0


def test_음수도_오늘로_처리한다():
    assert _period(-5)[1] == "오늘"


def test_1일은_최근_24시간이다():
    since, label = _period(1)
    assert label == "최근 24시간"
    delta = datetime.now(timezone.utc) - since
    assert timedelta(hours=23, minutes=55) < delta < timedelta(hours=24, minutes=5)


def test_여러날은_해당_일수만큼_거슬러간다():
    for days in (3, 7, 30):
        since, label = _period(days)
        assert label == f"최근 {days}일"
        delta = datetime.now(timezone.utc) - since
        assert timedelta(days=days) - timedelta(minutes=1) < delta < timedelta(days=days) + timedelta(minutes=1)


def test_기간이_길수록_시작점이_이르다():
    starts = [_period(d)[0] for d in (0, 3, 7, 30)]
    assert starts == sorted(starts, reverse=True)
