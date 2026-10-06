from __future__ import annotations

import os


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://bio:bio@localhost:5432/biotrial"
    )
    # ClinicalTrials.gov 는 1일 1회 배치 갱신이므로 시간 단위 폴링은 의미가 없다.
    # dataTimestamp 가 바뀌었을 때만 실제 수집한다 (docs/00_RESEARCH.md 제약 A).
    ctgov_poll_minutes: int = int(os.getenv("CTGOV_POLL_MINUTES", "60"))
    ctgov_force_fetch: bool = _bool("CTGOV_FORCE_FETCH", False)

    # DART 전자공시 (국내 최속 소스). https://opendart.fss.or.kr 무료 발급
    opendart_api_key: str = os.getenv("OPENDART_API_KEY", "")
    dart_poll_minutes: int = int(os.getenv("DART_POLL_MINUTES", "30"))
    dart_lookback_days: int = int(os.getenv("DART_LOOKBACK_DAYS", "365"))

    # 이메일 알림 — 앱 등록도 토큰 만료도 없다. 지메일은 '앱 비밀번호' 를 쓴다.
    email_user: str = os.getenv("EMAIL_USER", "")          # 보내는 계정
    email_password: str = os.getenv("EMAIL_PASSWORD", "")  # 앱 비밀번호
    email_to: str = os.getenv("EMAIL_TO", "")              # 받는 주소 (쉼표로 여러 개)
    email_from: str = os.getenv("EMAIL_FROM", "")          # 비우면 email_user 를 쓴다
    smtp_host: str = os.getenv("SMTP_HOST", "")            # 비우면 주소 보고 자동
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    # 이 등급 이상만 알림을 보낸다
    alert_min_severity: str = os.getenv("ALERT_MIN_SEVERITY", "HIGH")

    scheduler_enabled: bool = _bool("SCHEDULER_ENABLED", True)
    user_agent: str = os.getenv(
        "HTTP_USER_AGENT",
        "BioTrialMonitor/0.1 (personal research; contact: local)",
    )
    cors_origins: list = os.getenv("CORS_ORIGINS", "*").split(",")


settings = Settings()
