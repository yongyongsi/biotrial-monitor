"""
수집 스케줄러.

개인용 단일 서버 + 소스 20개 미만이므로 Celery 대신 APScheduler 를 쓴다
(docs/00_RESEARCH.md 13-2 참조). 소스가 100개를 넘으면 그때 교체한다.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.db import session_scope
from app.pipeline import collect_ctgov, collect_dart

log = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="Asia/Seoul")


def _job_ctgov() -> None:
    try:
        with session_scope() as db:
            run = collect_ctgov(db)
            if run.skipped:
                log.info("CT.gov 수집 건너뜀: %s", run.skip_reason)
            else:
                log.info("CT.gov 수집 완료: 확인 %d건 / 스냅샷 %d건 / 변화 %d건",
                         run.trials_checked, run.snapshots_created, run.changes_detected)
    except Exception:                          # noqa: BLE001
        log.exception("CT.gov 수집 작업 실패")


def _job_dart() -> None:
    try:
        with session_scope() as db:
            run = collect_dart(db)
            if run.skipped:
                log.info("DART 수집 건너뜀: %s", run.skip_reason)
            else:
                log.info("DART 수집 완료: 기업 %d개 / 새 공시 %d건",
                         run.trials_checked, run.changes_detected)
    except Exception:                          # noqa: BLE001
        log.exception("DART 수집 작업 실패")


def start() -> None:
    if not settings.scheduler_enabled:
        log.info("스케줄러가 비활성화되어 있습니다 (SCHEDULER_ENABLED=false)")
        return
    # next_run_time 은 지정하지 않는다.
    # APScheduler 의 interval 트리거는 기본적으로 '지금 + 간격' 을 첫 실행으로 잡으므로
    # 기동 직후 바로 돌지 않으면서 이후 주기적으로 실행된다.
    # (next_run_time=None 을 넘기면 작업이 일시정지 상태로 등록되어 영영 실행되지 않는다.)
    scheduler.add_job(
        _job_ctgov,
        "interval",
        minutes=settings.ctgov_poll_minutes,
        id="ctgov",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # DART 는 공시가 올라오는 즉시가 중요하므로 CT.gov 보다 자주 본다.
    if settings.opendart_api_key:
        scheduler.add_job(
            _job_dart,
            "interval",
            minutes=settings.dart_poll_minutes,
            id="dart",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    scheduler.start()
    log.info("스케줄러 시작: CT.gov %d분 / DART %s",
             settings.ctgov_poll_minutes,
             f"{settings.dart_poll_minutes}분" if settings.opendart_api_key else "미설정")


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
