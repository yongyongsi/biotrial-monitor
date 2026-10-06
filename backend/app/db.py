from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    pool_pre_ping=not _is_sqlite,
    future=True,
    # SQLite 는 기본적으로 한 스레드에서만 쓸 수 있는데,
    # FastAPI 요청과 스케줄러가 다른 스레드에서 돈다.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - 연결 시 1회
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.execute("PRAGMA synchronous=NORMAL")   # 휴대폰 저장소 수명을 아낀다
        # WAL 은 읽기와 쓰기가 서로를 막지 않게 해 주지만,
        # 네트워크/공유 파일시스템에서는 지원되지 않아 DB 가 깨질 수 있다.
        # 실제 적용됐는지 확인하고, 안 되면 기본 모드로 둔다.
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            mode = (cur.fetchone() or [""])[0]
            if str(mode).lower() != "wal":
                cur.execute("PRAGMA journal_mode=DELETE")
        except Exception:                          # noqa: BLE001
            cur.execute("PRAGMA journal_mode=DELETE")
        cur.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 의존성."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """스케줄러/스크립트용."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
