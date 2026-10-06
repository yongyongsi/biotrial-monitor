"""
Phase 0 스키마. docs/00_RESEARCH.md 14항 설계의 구현.

핵심 3테이블:
    clinical_trial            임상시험 1건 (고정 정보)
    clinical_trial_snapshot   시점별 전체 상태  -> append-only, 절대 삭제하지 않는다 (요구사항 29-4)
    clinical_trial_change     두 스냅샷의 diff  -> 앱 화면의 주인공
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    ARRAY, JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Integer,
    SmallInteger, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# 같은 스키마를 PostgreSQL 과 SQLite 양쪽에서 쓴다.
#   서버(클라우드/PC)  -> PostgreSQL
#   휴대폰(Termux)     -> SQLite (DB 서버를 따로 띄울 수 없다)
# 배열/JSON 은 파이썬 리스트로만 다루고 DB 쪽 연산자를 쓰지 않으므로 이렇게 바꿔도 동작이 같다.
JSONType = JSON().with_variant(JSONB(), "postgresql")
StrListType = JSON().with_variant(ARRAY(Text), "postgresql")

# SQLite 는 'INTEGER PRIMARY KEY' 만 자동 증가시킨다. BIGINT 로 두면 id 가 NULL 로 들어간다.
BigIntPk = BigInteger().with_variant(Integer, "sqlite")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Source(Base):
    """수집 대상 소스. collection_level 로 API/RSS/크롤링 단계를 관리한다."""
    __tablename__ = "source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name_ko: Mapped[str] = mapped_column(String(128))
    source_type: Mapped[str] = mapped_column(String(32))    # REGISTRY|REGULATOR|COMPANY|NEWS|JOURNAL
    region: Mapped[str] = mapped_column(String(16))         # KR | GLOBAL
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    # 1=공식API 2=RSS 3=정적HTML(BeautifulSoup) 4=Playwright
    collection_level: Mapped[int] = mapped_column(SmallInteger, default=1)
    base_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    poll_interval_sec: Mapped[int] = mapped_column(Integer, default=3600)
    robots_allowed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_ok_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fail_streak: Mapped[int] = mapped_column(Integer, default=0)
    # CT.gov dataTimestamp 등 소스가 알려주는 데이터 기준시각
    upstream_data_timestamp: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class Company(Base):
    __tablename__ = "company"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_ko: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    dart_corp_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    aliases: Mapped[Optional[list]] = mapped_column(StrListType, nullable=True)
    ir_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Drug(Base):
    """검색어 사전(aliases)이 핵심. 요구사항 2-2의 명칭 다양성 문제를 여기서 흡수한다."""
    __tablename__ = "drug"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_ko: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    dev_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    aliases: Mapped[Optional[list]] = mapped_column(StrListType, nullable=True)
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("company.id"), nullable=True)
    company: Mapped[Optional[Company]] = relationship()


class Disease(Base):
    __tablename__ = "disease"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_ko: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    aliases: Mapped[Optional[list]] = mapped_column(StrListType, nullable=True)


class RawDocument(Base):
    """원본 보존. append-only - UPDATE/DELETE 하지 않는다 (요구사항 29-3, 29-4)."""
    __tablename__ = "raw_document"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", "content_hash", name="uq_raw_doc"),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"))
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONType)
    content_hash: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ClinicalTrial(Base):
    __tablename__ = "clinical_trial"
    __table_args__ = (UniqueConstraint("registry", "registry_id", name="uq_trial_registry"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registry: Mapped[str] = mapped_column(String(32))        # CTGOV | MFDS | CRIS
    registry_id: Mapped[str] = mapped_column(String(64))     # NCT07576868
    org_study_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    drug_id: Mapped[Optional[int]] = mapped_column(ForeignKey("drug.id"), nullable=True)
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("company.id"), nullable=True)
    disease_id: Mapped[Optional[int]] = mapped_column(ForeignKey("disease.id"), nullable=True)

    title_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title_ko: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    region: Mapped[str] = mapped_column(String(16), default="GLOBAL")   # 요구사항 7
    is_watchlisted: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    drug: Mapped[Optional[Drug]] = relationship()
    company: Mapped[Optional[Company]] = relationship()
    disease: Mapped[Optional[Disease]] = relationship()


class ClinicalTrialSnapshot(Base):
    """시점별 전체 상태. 과거를 지우지 않는 것이 이 프로젝트의 전제다."""
    __tablename__ = "clinical_trial_snapshot"
    __table_args__ = (
        Index("ix_snapshot_trial_time", "trial_id", "captured_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("clinical_trial.id"))
    raw_document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("raw_document.id"), nullable=True)

    overall_status: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    phase: Mapped[Optional[list]] = mapped_column(StrListType, nullable=True)
    enrollment_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    enrollment_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    start_date: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    primary_completion_date: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    completion_date: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    has_results: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    locations: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)
    location_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_last_update: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    snapshot_hash: Mapped[str] = mapped_column(String(64))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    trial: Mapped[ClinicalTrial] = relationship()

    def as_dict(self) -> dict:
        """diff 엔진에 넘길 형태로 변환."""
        return {
            "overall_status": self.overall_status,
            "phase": list(self.phase or []),
            "enrollment_count": self.enrollment_count,
            "enrollment_type": self.enrollment_type,
            "start_date": self.start_date,
            "primary_completion_date": self.primary_completion_date,
            "completion_date": self.completion_date,
            "has_results": self.has_results,
            "locations": self.locations or [],
            "source_last_update": self.source_last_update,
        }


class ClinicalTrialChange(Base):
    """diff 결과 = 앱 첫 화면의 주인공."""
    __tablename__ = "clinical_trial_change"
    __table_args__ = (
        UniqueConstraint("curr_snapshot_id", "field_name", "old_value", "new_value",
                         name="uq_change"),
        Index("ix_change_detected", "detected_at"),
        Index("ix_change_severity", "severity"),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("clinical_trial.id"))
    prev_snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clinical_trial_snapshot.id"), nullable=True)
    curr_snapshot_id: Mapped[int] = mapped_column(ForeignKey("clinical_trial_snapshot.id"))

    field_name: Mapped[str] = mapped_column(String(48))
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    old_value_ko: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value_ko: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    severity: Mapped[str] = mapped_column(String(16))
    headline_ko: Mapped[str] = mapped_column(Text)
    detail_ko: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    is_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    trial: Mapped[ClinicalTrial] = relationship()


class Disclosure(Base):
    """DART 전자공시 1건.

    접수번호(rcept_no)가 금융감독원이 부여하는 자연 고유키라 중복 제거가 간단하다.
    임상 관련 공시는 본문(document.xml)까지 받아 details(JSONB)에 구조화해 넣는다.
    """
    __tablename__ = "disclosure"
    __table_args__ = (
        Index("ix_disclosure_dt", "rcept_dt"),
        Index("ix_disclosure_severity", "severity"),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"))
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("company.id"), nullable=True)
    drug_id: Mapped[Optional[int]] = mapped_column(ForeignKey("drug.id"), nullable=True)
    raw_document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("raw_document.id"), nullable=True)

    rcept_no: Mapped[str] = mapped_column(String(32), unique=True)   # 중복 방지 (요구사항 22)
    rcept_dt: Mapped[date] = mapped_column(Date)
    report_nm: Mapped[str] = mapped_column(Text)
    subtitle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text)

    event_type: Mapped[str] = mapped_column(String(32))     # IND_APPROVE 등
    event_type_ko: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    headline_ko: Mapped[str] = mapped_column(Text)
    detail_ko: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 본문에서 파싱한 구조화 필드 (IND번호, 승인기관, 실시국가, 목표인원 등)
    details: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    is_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    company: Mapped[Optional[Company]] = relationship()
    drug: Mapped[Optional[Drug]] = relationship()


class Watchlist(Base):
    __tablename__ = "watchlist"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))      # DRUG|DISEASE|COMPANY|TRIAL
    ref_id: Mapped[int] = mapped_column(Integer)
    label_ko: Mapped[str] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Alert(Base):
    __tablename__ = "alert"
    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True)
    change_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clinical_trial_change.id"), nullable=True)
    disclosure_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("disclosure.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(32))    # telegram | log
    severity: Mapped[str] = mapped_column(String(16))
    body_ko: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class CollectionRun(Base):
    """수집 이력. '언제 마지막으로 확인했는가'를 화면에 보여주기 위해 필요하다."""
    __tablename__ = "collection_run"
    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True)
    source_code: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    skip_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trials_checked: Mapped[int] = mapped_column(Integer, default=0)
    snapshots_created: Mapped[int] = mapped_column(Integer, default=0)
    changes_detected: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
