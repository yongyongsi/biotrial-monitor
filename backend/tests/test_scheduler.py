"""스케줄러 등록 검증.

next_run_time=None 을 넘기면 APScheduler 가 작업을 '일시정지' 상태로 등록해
영영 실행되지 않는다. 실수하기 쉬운 부분이라 회귀 테스트로 고정해 둔다.

next_run_time 은 스케줄러가 실제로 기동한 뒤에야 계산되므로 진짜로 start 한 다음 확인한다.
"""
from __future__ import annotations

import pytest

pytest.importorskip("apscheduler")


@pytest.fixture
def clean_scheduler():
    from app import scheduler as sched
    sched.scheduler.remove_all_jobs()
    yield sched
    sched.shutdown()
    sched.scheduler.remove_all_jobs()


def test_수집작업이_일시정지_상태로_등록되지_않는다(clean_scheduler, monkeypatch):
    sched = clean_scheduler
    monkeypatch.setattr(sched.settings, "scheduler_enabled", True)
    monkeypatch.setattr(sched.settings, "ctgov_poll_minutes", 60)

    sched.start()

    job = sched.scheduler.get_job("ctgov")
    assert job is not None, "ctgov 수집 작업이 등록되지 않았습니다"
    assert job.next_run_time is not None, (
        "작업이 일시정지 상태입니다. next_run_time=None 을 넘기지 않았는지 확인하세요."
    )


def test_첫_실행은_기동_직후가_아니라_한_주기_뒤다(clean_scheduler, monkeypatch):
    """기동하자마자 외부 API 를 때리지 않도록 한 주기 뒤부터 시작해야 한다."""
    from datetime import datetime, timedelta, timezone

    sched = clean_scheduler
    monkeypatch.setattr(sched.settings, "scheduler_enabled", True)
    monkeypatch.setattr(sched.settings, "ctgov_poll_minutes", 60)

    sched.start()
    job = sched.scheduler.get_job("ctgov")
    delta = job.next_run_time - datetime.now(timezone.utc)
    assert timedelta(minutes=50) < delta <= timedelta(minutes=61), delta


def test_비활성화되면_작업을_등록하지_않는다(clean_scheduler, monkeypatch):
    sched = clean_scheduler
    monkeypatch.setattr(sched.settings, "scheduler_enabled", False)
    sched.start()
    assert sched.scheduler.get_job("ctgov") is None
