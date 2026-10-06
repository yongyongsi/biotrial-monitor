"""
SQLite 에서도 같은 스키마가 동작하는지 검증.

휴대폰(Termux)에는 PostgreSQL 서버를 띄울 수 없으므로 SQLite 를 쓴다.
스키마 정의는 하나만 유지하고 방언만 바꾸는 구조라, 실제로 그렇게 되는지 확인한다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    ClinicalTrial, ClinicalTrialChange, ClinicalTrialSnapshot,
    Company, Disclosure, Drug, RawDocument, Source,
)


@pytest.fixture
def sqlite_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    db = Session()
    yield db
    db.close()
    engine.dispose()


def test_전체_스키마가_SQLite에_생성된다(sqlite_db):
    names = set(Base.metadata.tables)
    for expected in ("clinical_trial", "clinical_trial_snapshot",
                     "clinical_trial_change", "disclosure", "raw_document",
                     "drug", "company", "disease", "watchlist", "alert"):
        assert expected in names


def test_문자열_배열이_왕복한다(sqlite_db):
    """PostgreSQL 에서는 ARRAY(Text), SQLite 에서는 JSON 으로 저장된다."""
    db = sqlite_db
    aliases = ["제프티", "Xafty", "CP-COV03", "니클로사마이드"]
    db.add(Drug(name_ko="제프티", name_en="Xafty", dev_code="CP-COV03", aliases=aliases))
    db.commit()

    got = db.scalars(select(Drug)).one()
    assert got.aliases == aliases
    assert isinstance(got.aliases, list)


def test_JSON_필드가_왕복한다(sqlite_db):
    db = sqlite_db
    src = Source(code="ctgov", name_ko="테스트", source_type="REGISTRY",
                 region="GLOBAL", is_official=True, collection_level=1,
                 poll_interval_sec=3600)
    db.add(src)
    db.flush()

    locations = [
        {"facility": "NHTD", "city": "Hanoi", "country": "Vietnam", "status": "RECRUITING"},
        {"facility": "Tien Giang", "city": "Mỹ Tho", "country": "Vietnam", "status": "RECRUITING"},
    ]
    trial = ClinicalTrial(registry="CTGOV", registry_id="NCT07576868", region="GLOBAL")
    db.add(trial)
    db.flush()
    db.add(ClinicalTrialSnapshot(
        trial_id=trial.id, overall_status="RECRUITING", phase=["PHASE2", "PHASE3"],
        locations=locations, location_count=2, snapshot_hash="abc",
    ))
    db.commit()

    snap = db.scalars(select(ClinicalTrialSnapshot)).one()
    assert snap.locations == locations
    assert snap.phase == ["PHASE2", "PHASE3"]
    assert snap.locations[1]["city"] == "Mỹ Tho"     # 유니코드도 보존


def test_수집_파이프라인이_SQLite에서_끝까지_돈다(sqlite_db):
    """원본 저장 -> 스냅샷 -> diff -> 변화 기록까지."""
    from app.collectors.ctgov import normalize
    from app.pipeline import ingest_snapshot
    from tests.test_ctgov_normalize import REAL_RAW

    db = sqlite_db
    src = Source(code="ctgov", name_ko="CT.gov", source_type="REGISTRY",
                 region="GLOBAL", is_official=True, collection_level=1,
                 poll_interval_sec=3600)
    drug = Drug(name_ko="제프티", name_en="Xafty", dev_code="CP-COV03")
    db.add_all([src, drug])
    db.flush()

    trial = ClinicalTrial(registry="CTGOV", registry_id="NCT07576868",
                          drug_id=drug.id, region="GLOBAL")
    db.add(trial)
    db.flush()

    _, snap = normalize(REAL_RAW)

    first = ingest_snapshot(db, trial, REAL_RAW, snap, src)
    assert first.snapshot_created is True
    assert first.changes_detected == 0          # 최초 수집은 변화가 아니다

    again = ingest_snapshot(db, trial, REAL_RAW, snap, src)
    assert again.snapshot_created is False      # 같은 내용이면 스냅샷을 만들지 않는다
    assert again.changes_detected == 0

    changed = dict(snap, overall_status="ACTIVE_NOT_RECRUITING", enrollment_count=250)
    third = ingest_snapshot(db, trial, REAL_RAW, changed, src)
    assert third.snapshot_created is True
    assert third.changes_detected == 2
    db.commit()

    rows = db.scalars(select(ClinicalTrialChange)).all()
    headlines = [r.headline_ko for r in rows]
    assert any("환자 모집이 끝나고" in h for h in headlines)
    assert any("210명에서 250명으로" in h for h in headlines)

    # 원본은 지우지 않고 쌓인다 (요구사항 29-4)
    assert len(db.scalars(select(RawDocument)).all()) >= 1
    assert len(db.scalars(select(ClinicalTrialSnapshot)).all()) == 2


def test_공시_중복이_SQLite에서도_막힌다(sqlite_db):
    from sqlalchemy.exc import IntegrityError
    from datetime import date

    db = sqlite_db
    src = Source(code="opendart", name_ko="DART", source_type="COMPANY",
                 region="KR", is_official=True, collection_level=1,
                 poll_interval_sec=1800)
    company = Company(name_ko="현대바이오사이언스", dart_corp_code="00313649")
    db.add_all([src, company])
    db.flush()

    def make():
        return Disclosure(
            source_id=src.id, company_id=company.id, rcept_no="20260903900243",
            rcept_dt=date(2026, 9, 3), report_nm="투자판단관련주요경영사항",
            url="https://dart.fss.or.kr/x", event_type="TRIAL_IND_APPROVE",
            event_type_ko="임상시험 승인", severity="CRITICAL",
            headline_ko="미국 FDA 승인을 받았습니다",
        )

    db.add(make())
    db.commit()
    db.add(make())
    with pytest.raises(IntegrityError):
        db.commit()
