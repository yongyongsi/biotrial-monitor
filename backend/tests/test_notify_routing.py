"""알림 경로 선택 검증 — 폰에서 돌면 폰 알림, 서버면 텔레그램, 없으면 로그."""
from __future__ import annotations

from app.notify import android, telegram


def test_Termux가_없으면_안드로이드_알림을_쓰지_않는다(monkeypatch):
    monkeypatch.setattr(android.shutil, "which", lambda _: None)
    assert android.available() is False
    assert android.notify("제목", "내용") is False


def test_Termux가_있으면_사용가능으로_본다(monkeypatch):
    monkeypatch.setattr(android.shutil, "which", lambda _: "/usr/bin/termux-notification")
    assert android.available() is True


def test_중요도가_안드로이드_우선순위로_변환된다():
    assert android._PRIORITY["CRITICAL"] == "max"
    assert android._PRIORITY["LOW"] == "low"


def test_등급_미달이면_보내지_않는다(monkeypatch):
    monkeypatch.setattr(telegram.settings, "alert_min_severity", "HIGH")
    assert telegram._should_send("CRITICAL") is True
    assert telegram._should_send("HIGH") is True
    assert telegram._should_send("MEDIUM") is False
    assert telegram._should_send("LOW") is False
