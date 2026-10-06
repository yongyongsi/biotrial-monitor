"""
이메일 알림.

텔레그램·카카오톡과 달리 앱 등록도 토큰 만료도 없다.
지메일이면 '앱 비밀번호' 하나만 있으면 되고, 다른 메일도 SMTP 주소만 맞추면 된다.

보내는 사람과 받는 사람이 같아도 된다 (자기 자신에게 보내기).
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate
from typing import Optional, Sequence

from app.config import settings

log = logging.getLogger(__name__)

# 자주 쓰는 메일 서비스의 SMTP 주소 (주소만 넣으면 알아서 잡힌다)
KNOWN_HOSTS = {
    "gmail.com": ("smtp.gmail.com", 587),
    "googlemail.com": ("smtp.gmail.com", 587),
    "naver.com": ("smtp.naver.com", 587),
    "daum.net": ("smtp.daum.net", 465),
    "hanmail.net": ("smtp.daum.net", 465),
    "kakao.com": ("smtp.kakao.com", 465),
    "outlook.com": ("smtp-mail.outlook.com", 587),
    "hotmail.com": ("smtp-mail.outlook.com", 587),
    "nate.com": ("smtp.mail.nate.com", 465),
}


def _server() -> tuple[str, int]:
    """설정에 적힌 SMTP 주소. 없으면 보내는 주소의 도메인으로 추측한다."""
    if settings.smtp_host:
        return settings.smtp_host, settings.smtp_port
    domain = (settings.email_from or settings.email_user or "").split("@")[-1].lower()
    return KNOWN_HOSTS.get(domain, ("smtp.gmail.com", 587))


def available() -> bool:
    return bool(settings.email_user and settings.email_password and settings.email_to)


def send(subject: str, body: str, link: Optional[str] = None) -> bool:
    """메일 한 통을 보낸다. 설정이 없으면 조용히 False."""
    if not available():
        return False

    host, port = _server()
    sender = settings.email_from or settings.email_user
    recipients: Sequence[str] = [a.strip() for a in settings.email_to.split(",") if a.strip()]

    msg = EmailMessage()
    msg["Subject"] = subject[:150]
    msg["From"] = formataddr(("바이오 임상 모니터", sender))
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)

    text = body if not link else f"{body}\n\n원문 보기\n{link}"
    msg.set_content(text)

    try:
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as s:
                s.login(settings.email_user, settings.email_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.ehlo()
                s.starttls(context=context)
                s.login(settings.email_user, settings.email_password)
                s.send_message(msg)
        return True
    except Exception as exc:                       # noqa: BLE001
        log.warning("이메일 전송 실패 (%s:%s): %s", host, port, exc)
        return False
