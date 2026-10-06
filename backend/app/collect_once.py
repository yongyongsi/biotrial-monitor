"""
수집 1회만 하고 끝나는 진입점.

휴대폰에서는 서버를 24시간 띄워두는 대신, 안드로이드 스케줄러
(termux-job-scheduler)가 이 스크립트를 주기적으로 불러준다.

배터리 관점에서 이 방식이 훨씬 낫다.
    상시 실행 + wake-lock : CPU 를 계속 깨워둬야 한다
    필요할 때만 깨우기     : 수집에 실제로 쓰는 시간은 하루 몇 초뿐이다

실행:
    python -m app.collect_once            # 평소
    python -m app.collect_once --force    # 등록소 갱신 여부와 무관하게 강제 수집
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Tuple

from sqlalchemy import desc, func, select

from app.core.severity import SEVERITY_ORDER, worst
from app.db import engine, session_scope
from app.models import Alert
from app.notify import android
from app.pipeline import collect_ctgov, collect_dart, collect_news
from app.schema_sync import sync as sync_schema

log = logging.getLogger("collect")

# httpx 는 요청 URL 을 INFO 로 남기는데, 거기에 DART 인증키가 그대로 들어간다.
# 로그 파일에 키가 남지 않도록 경고 이상만 남긴다.
for _noisy in ("httpx", "httpcore", "apscheduler.executors.default"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# 한 번에 이 건수 이상이 들어오면 배너를 도배하지 않고 묶음 알림을 하나 더 띄운다
SUMMARY_THRESHOLD = 3


def _max_alert_id() -> int:
    with session_scope() as db:
        return db.scalar(select(func.max(Alert.id))) or 0


def _alerts_since(alert_id: int) -> List[Tuple[str, str]]:
    """이번 실행에서 실제로 발송된 알림의 (중요도, 첫 줄)."""
    with session_scope() as db:
        rows = db.scalars(
            select(Alert)
            .where(Alert.id > alert_id, Alert.ok.is_(True))
            .order_by(desc(Alert.id))
        ).all()
        return [(a.severity, (a.body_ko or "").split("\n")[0]) for a in rows]


def run(force: bool = False) -> int:
    """수집을 한 번 돌리고 발송된 알림 수를 돌려준다."""
    sync_schema(engine)
    before = _max_alert_id()

    with session_scope() as db:
        ct = collect_ctgov(db, force=force)
        log.info("임상시험: %s", ct.skip_reason if ct.skipped
                 else f"확인 {ct.trials_checked}건 / 변화 {ct.changes_detected}건")

    with session_scope() as db:
        dt = collect_dart(db)
        log.info("공시: %s", dt.skip_reason if dt.skipped
                 else f"기업 {dt.trials_checked}개 / 새 공시 {dt.changes_detected}건")

    with session_scope() as db:
        nw = collect_news(db)
        log.info("뉴스: %s", nw.error or f"새 기사 {nw.changes_detected}건")

    sent = _alerts_since(before)
    if len(sent) >= SUMMARY_THRESHOLD:
        top = worst([s for s, _ in sent])
        headline = next((h for s, h in sent if s == top), sent[0][1])
        android.summary(len(sent), headline, top)

    log.info("알림 %d건 발송", len(sent))
    return len(sent)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="임상시험·공시를 한 번 수집한다")
    parser.add_argument("--force", action="store_true",
                        help="등록소 갱신 여부와 무관하게 강제로 수집")
    parser.add_argument("--quiet", action="store_true", help="로그를 줄인다")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
    )
    try:
        run(force=args.force)
        return 0
    except Exception:                              # noqa: BLE001
        log.exception("수집 실패")
        return 1


if __name__ == "__main__":
    sys.exit(main())
