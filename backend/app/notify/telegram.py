"""
Telegram 알림 (요구사항 20).

모바일 Push 는 iOS 제약이 있으므로 요구사항 권고대로 Telegram 부터 구현한다.
토큰이 없으면 조용히 로그만 남기고 넘어간다 - 알림 미설정이 수집을 막으면 안 된다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Sequence

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.core.severity import SEVERITY_ORDER, severity_icon, severity_ko
from app.models import Alert
from app.notify import android, email

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/sendMessage"


def _should_send(severity: str) -> bool:
    threshold = SEVERITY_ORDER.get(settings.alert_min_severity, 1)
    return SEVERITY_ORDER.get(severity, 3) <= threshold


def build_message(change) -> str:
    """요구사항 20항 형식의 알림 본문."""
    trial = change.trial
    icon = severity_icon(change.severity)
    label = severity_ko(change.severity)
    lines = [
        f"{icon} [{label}] 임상시험 업데이트",
        "",
        change.headline_ko,
        "",
    ]
    if change.old_value_ko and change.new_value_ko:
        lines += [f"기존: {change.old_value_ko}", f"현재: {change.new_value_ko}", ""]
    if trial is not None:
        if trial.drug:
            lines.append(f"약물: {trial.drug.name_ko}")
        if trial.disease:
            lines.append(f"질환: {trial.disease.name_ko}")
        lines.append(f"등록번호: {trial.registry_id}")
        if trial.url:
            lines.append(trial.url)
    lines += ["", "출처: ClinicalTrials.gov (공식 임상시험 등록정보)"]
    return "\n".join(lines)


def build_disclosure_message(d) -> str:
    """전자공시 알림 본문."""
    icon = severity_icon(d.severity)
    label = severity_ko(d.severity)
    lines = [
        f"{icon} [{label}] {d.event_type_ko}",
        "",
        d.headline_ko,
        "",
    ]
    if d.detail_ko:
        lines += [d.detail_ko, ""]
    if d.company:
        lines.append(f"기업: {d.company.name_ko}")
    if d.drug:
        lines.append(f"약물: {d.drug.name_ko}")
    lines.append(f"공시일: {d.rcept_dt}")
    lines.append(d.url)
    lines += ["", "출처: 금융감독원 전자공시(DART) — 법적 공시 의무 자료"]
    return "\n".join(lines)


def banner_for_change(change) -> tuple:
    """임상시험 변화 -> 배너 제목/본문.

    배너는 화면 위에 잠깐 떠오르고 사라지므로 제목만 읽어도 뜻이 통해야 한다.
    """
    trial = change.trial
    who = " ".join(filter(None, [
        trial.drug.name_ko if trial and trial.drug else None,
        trial.disease.name_ko if trial and trial.disease else None,
    ])) or "임상시험"
    title = f"{severity_icon(change.severity)} {who} 변경"
    return title[:80], change.headline_ko


def banner_for_disclosure(d) -> tuple:
    """전자공시 -> 배너 제목/본문."""
    who = (d.drug.name_ko if d.drug else None) or (d.company.name_ko if d.company else "")
    title = f"{severity_icon(d.severity)} {who} {d.event_type_ko}".strip()
    return title[:80], d.headline_ko


def _send(db: Session, body: str, severity: str,
          change_id=None, disclosure_id=None, url: str = None,
          banner_title: str = None, banner_body: str = None) -> Alert:
    """알림을 보낸다. 설정된 경로를 모두 쓴다.

        1) 갤럭시에서 직접 돌 때  -> 폰 알림창 (Termux:API)
        2) 이메일이 설정돼 있으면 -> 메일
        3) 텔레그램이 설정돼 있으면 -> 텔레그램
        4) 아무것도 없으면        -> 로그

    여러 개를 켜두면 모두 보낸다. 하나가 실패해도 나머지는 간다.
    """
    alert = Alert(change_id=change_id, disclosure_id=disclosure_id,
                  severity=severity, body_ko=body, channel="log")
    sent_via: List[str] = []
    errors: List[str] = []

    # 1) 폰에서 직접 돌고 있으면 외부 서비스 없이 바로 알린다
    if android.available():
        if android.notify(banner_title or body.split("\n")[0],
                          banner_body or body, severity, url):
            sent_via.append("android")
        else:
            errors.append("폰 알림 실패")

    # 2) 이메일 — 제목만 봐도 무슨 일인지 알 수 있어야 한다
    if email.available():
        subject = banner_title or body.split("\n")[0]
        if email.send(subject, body, url):
            sent_via.append("email")
        else:
            errors.append("이메일 실패")

    if sent_via:
        alert.channel = "+".join(sent_via)
        alert.ok = True
        alert.sent_at = datetime.now(timezone.utc)
        if errors:
            alert.error = " / ".join(errors)
        db.add(alert)
        return alert

    # 3) 텔레그램
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        alert.channel = "log"
        alert.ok = True
        alert.sent_at = datetime.now(timezone.utc)
        if errors:
            alert.error = " / ".join(errors)
        log.info("[알림 미설정 - 로그로 대체]\n%s", body)
    else:
        alert.channel = "telegram"
        try:
            r = httpx.post(
                API.format(token=settings.telegram_bot_token),
                json={"chat_id": settings.telegram_chat_id, "text": body,
                      "disable_web_page_preview": False},
                timeout=15.0,
            )
            r.raise_for_status()
            alert.ok = True
            alert.sent_at = datetime.now(timezone.utc)
        except Exception as exc:                  # noqa: BLE001
            alert.ok = False
            alert.error = str(exc)
            log.warning("텔레그램 전송 실패: %s", exc)
    db.add(alert)
    return alert


def notify_disclosures(db: Session, disclosures: Sequence) -> List[Alert]:
    sent: List[Alert] = []
    for d in disclosures:
        if not _should_send(d.severity):
            continue
        bt, bb = banner_for_disclosure(d)
        alert = _send(db, build_disclosure_message(d), d.severity,
                      disclosure_id=d.id, url=d.url,
                      banner_title=bt, banner_body=bb)
        d.is_notified = alert.ok
        sent.append(alert)
    db.flush()
    return sent


def notify_changes(db: Session, changes: Sequence) -> List[Alert]:
    sent: List[Alert] = []
    for change in changes:
        if not _should_send(change.severity):
            continue
        bt, bb = banner_for_change(change)
        alert = _send(db, build_message(change), change.severity,
                      change_id=change.id,
                      url=change.trial.url if change.trial else None,
                      banner_title=bt, banner_body=bb)
        change.is_notified = alert.ok
        sent.append(alert)
    db.flush()
    return sent
