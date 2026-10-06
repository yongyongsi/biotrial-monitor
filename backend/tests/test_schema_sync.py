"""
스키마 자동 동기화 검증.

과거 데이터를 지우지 않는 것이 이 프로젝트의 전제(요구사항 29-4)라
DB 를 다시 만들 수 없다. 컬럼이 추가돼도 기존 DB 가 그대로 동작해야 한다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db import Base
from app.schema_sync import sync


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/sync.db", future=True)
    yield eng
    eng.dispose()


def test_빈_DB에_전체_스키마를_만든다(engine):
    sync(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"clinical_trial", "disclosure", "alert", "drug"} <= tables


def test_이미_만들어진_DB를_다시_돌려도_변화가_없다(engine):
    sync(engine)
    assert sync(engine) == []          # 두 번째는 할 일이 없어야 한다


def _make_old_alert_table(engine):
    """disclosure_id 가 없던 예전 alert 테이블을 재현한다.

    (SQLite 는 외래키가 걸린 컬럼을 DROP 하지 못하므로 테이블을 다시 만든다)
    """
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alert"))
        conn.execute(text("""
            CREATE TABLE alert (
                id INTEGER NOT NULL PRIMARY KEY,
                change_id BIGINT,
                channel VARCHAR(32) NOT NULL,
                severity VARCHAR(16) NOT NULL,
                body_ko TEXT,
                sent_at DATETIME,
                ok BOOLEAN,
                error TEXT
            )"""))


def test_빠진_컬럼을_채워넣는다(engine):
    """실제로 겪은 상황: alert 테이블에 disclosure_id 를 나중에 추가했다."""
    sync(engine)
    _make_old_alert_table(engine)
    assert "disclosure_id" not in {c["name"] for c in inspect(engine).get_columns("alert")}

    changes = sync(engine)
    assert any("alert.disclosure_id" in c for c in changes), changes
    assert "disclosure_id" in {c["name"] for c in inspect(engine).get_columns("alert")}


def test_기존_데이터를_지우지_않는다(engine):
    sync(engine)
    _make_old_alert_table(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO drug (id, name_ko, name_en) VALUES (1, '제프티', 'Xafty')"))
        conn.execute(text(
            "INSERT INTO alert (id, channel, severity, body_ko, ok) "
            "VALUES (1, 'android', 'CRITICAL', '기존 알림', 1)"))

    sync(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name_ko FROM drug WHERE id=1")).one()[0] == "제프티"
        assert conn.execute(text("SELECT body_ko FROM alert WHERE id=1")).one()[0] == "기존 알림"
