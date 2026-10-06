"""이메일 알림 — 설정 없으면 조용히 넘어가고, 서버 주소를 알아서 고른다."""
from __future__ import annotations

import pytest

from app.notify import email


def test_설정이_없으면_보내지_않는다(monkeypatch):
    for key in ("email_user", "email_password", "email_to"):
        monkeypatch.setattr(email.settings, key, "")
    assert email.available() is False
    assert email.send("제목", "내용") is False


def test_세_가지가_모두_있어야_보낸다(monkeypatch):
    monkeypatch.setattr(email.settings, "email_user", "me@gmail.com")
    monkeypatch.setattr(email.settings, "email_password", "")
    monkeypatch.setattr(email.settings, "email_to", "me@gmail.com")
    assert email.available() is False

    monkeypatch.setattr(email.settings, "email_password", "앱비밀번호")
    assert email.available() is True


@pytest.mark.parametrize("addr,host,port", [
    ("me@gmail.com", "smtp.gmail.com", 587),
    ("me@naver.com", "smtp.naver.com", 587),
    ("me@daum.net", "smtp.daum.net", 465),
    ("me@kakao.com", "smtp.kakao.com", 465),
    ("me@알수없는곳.com", "smtp.gmail.com", 587),      # 모르면 지메일로 가정
])
def test_주소만_보고_서버를_고른다(monkeypatch, addr, host, port):
    monkeypatch.setattr(email.settings, "smtp_host", "")
    monkeypatch.setattr(email.settings, "email_from", "")
    monkeypatch.setattr(email.settings, "email_user", addr)
    assert email._server() == (host, port)


def test_직접_지정한_서버가_우선이다(monkeypatch):
    monkeypatch.setattr(email.settings, "smtp_host", "smtp.mycompany.co.kr")
    monkeypatch.setattr(email.settings, "smtp_port", 2525)
    monkeypatch.setattr(email.settings, "email_user", "me@gmail.com")
    assert email._server() == ("smtp.mycompany.co.kr", 2525)


def test_보내기_실패해도_예외가_새지_않는다(monkeypatch):
    """메일 서버가 죽어도 수집은 계속되어야 한다."""
    monkeypatch.setattr(email.settings, "email_user", "me@gmail.com")
    monkeypatch.setattr(email.settings, "email_password", "x")
    monkeypatch.setattr(email.settings, "email_to", "me@gmail.com")
    monkeypatch.setattr(email.settings, "smtp_host", "smtp.invalid.example")

    def boom(*a, **k):
        raise OSError("연결 실패")
    monkeypatch.setattr(email.smtplib, "SMTP", boom)

    assert email.send("제목", "내용") is False
