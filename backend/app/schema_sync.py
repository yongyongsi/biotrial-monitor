"""
스키마 자동 동기화.

`Base.metadata.create_all` 은 없는 테이블만 만들고 이미 있는 테이블은 건드리지 않는다.
그래서 컬럼을 새로 추가하면 기존 DB 에서 'column does not exist' 가 난다.

이 프로젝트는 과거 스냅샷을 지우지 않는 것이 전제(요구사항 29-4)이므로
DB 를 지웠다 다시 만들 수 없다. 그래서 **추가된 컬럼만** 안전하게 붙여준다.

다루는 것 / 다루지 않는 것
    ✅ 새 테이블
    ✅ 새 컬럼 (NULL 허용 또는 기본값이 있는 경우)
    ❌ 컬럼 삭제·이름 변경·타입 변경  -> 이런 변경이 필요해지면 그때 Alembic 을 도입한다

PostgreSQL 과 SQLite 양쪽에서 동작한다.
"""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateColumn

from app.db import Base

log = logging.getLogger(__name__)


def _column_sql(engine: Engine, column) -> str:
    """ALTER TABLE ... ADD COLUMN 에 쓸 조각을 만든다."""
    ddl = str(CreateColumn(column).compile(engine))
    # 기본키/유니크 같은 제약은 추가 컬럼에 붙일 수 없으므로 떼어낸다
    for token in (" PRIMARY KEY", " UNIQUE"):
        ddl = ddl.replace(token, "")
    return ddl.strip()


def sync(engine: Engine) -> List[str]:
    """없는 테이블과 컬럼을 채운다. 무엇을 했는지 목록으로 돌려준다."""
    changes: List[str] = []

    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            changes.append(f"테이블 추가: {table.name}")
            continue

        have = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in have:
                continue
            if not column.nullable and column.default is None and column.server_default is None:
                log.warning(
                    "컬럼 %s.%s 은(는) NULL 을 허용하지 않고 기본값도 없어 자동 추가하지 않습니다.",
                    table.name, column.name)
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {_column_sql(engine, column)}"
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
                changes.append(f"컬럼 추가: {table.name}.{column.name}")
            except Exception as exc:               # noqa: BLE001
                log.error("컬럼 추가 실패 %s.%s: %s", table.name, column.name, exc)

    if changes:
        log.info("스키마 동기화: %s", ", ".join(changes))
    return changes
