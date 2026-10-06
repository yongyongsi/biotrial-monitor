"""
원본(raw_document) 중복 저장 방지.

raw_document 에는 (source, external_id, content_hash) 유니크 제약이 있다.
확인 없이 INSERT 하면 중복 시 예외가 나고, 그 순간 세션이 롤백되어
**그 뒤에 수집하려던 것이 전부 날아간다.** 실제로 겪은 문제라 테스트로 고정한다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import RawDocument, Source
from app.pipeline import get_or_create_raw_document


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/raw.db", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False, future=True)()
    session.add(Source(id=1, code="opendart", name_ko="DART", source_type="COMPANY",
                       region="KR", is_official=True, collection_level=1,
                       poll_interval_sec=1800))
    session.flush()
    yield session
    session.close()
    engine.dispose()


PAYLOAD = {"report_nm": "투자판단관련주요경영사항", "rcept_no": "20260903900243"}


def test_같은_원본을_두_번_넣어도_한_건만_남는다(db):
    first = get_or_create_raw_document(db, 1, "20260903900243", "https://x", PAYLOAD)
    second = get_or_create_raw_document(db, 1, "20260903900243", "https://x", PAYLOAD)
    assert first.id == second.id
    assert db.scalar(select(func.count()).select_from(RawDocument)) == 1


def test_내용이_바뀌면_새로_쌓인다(db):
    """과거 원본은 지우지 않는다 (요구사항 29-4)."""
    get_or_create_raw_document(db, 1, "20260903900243", "https://x", PAYLOAD)
    changed = dict(PAYLOAD, report_nm="투자판단관련주요경영사항(정정)")
    get_or_create_raw_document(db, 1, "20260903900243", "https://x", changed)
    assert db.scalar(select(func.count()).select_from(RawDocument)) == 2


def test_재수집해도_세션이_죽지_않는다(db):
    """공시 테이블만 비우고 다시 수집하는 상황 - 원본은 남아 있다."""
    from sqlalchemy import delete
    from app.models import Disclosure

    for i in range(3):
        get_or_create_raw_document(db, 1, f"2026090390024{i}", "https://x",
                                   dict(PAYLOAD, rcept_no=f"2026090390024{i}"))
    db.commit()

    db.execute(delete(Disclosure))
    db.commit()

    # 같은 원본을 다시 만나도 예외 없이 진행되어야 한다
    for i in range(3):
        get_or_create_raw_document(db, 1, f"2026090390024{i}", "https://x",
                                   dict(PAYLOAD, rcept_no=f"2026090390024{i}"))
    db.commit()
    assert db.scalar(select(func.count()).select_from(RawDocument)) == 3

    # 세션이 살아 있어야 이후 작업이 이어진다
    get_or_create_raw_document(db, 1, "새것", "https://y", {"a": 1})
    db.commit()
    assert db.scalar(select(func.count()).select_from(RawDocument)) == 4
