"""
수집 파이프라인 (요구사항 11).

    Source -> Fetch -> Normalize -> Compare with previous snapshot
           -> Detect Change -> Store Change History -> Generate Alert

2단계 해시 필터로 불필요한 연산을 없앤다.
    1차 content_hash   : 원본이 그대로면 raw_document 를 새로 만들지 않는다
    2차 snapshot_hash  : 추적 필드가 그대로면 diff 를 돌리지 않는다
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.collectors import ctgov, dart
from app.config import settings
from app.core.diff import content_hash, diff_snapshots, snapshot_hash
from app.core import severity as sev
from app.models import (
    ClinicalTrial, ClinicalTrialChange, ClinicalTrialSnapshot,
    CollectionRun, Company, Disclosure, Drug, RawDocument, Source,
)
from app.notify.telegram import notify_changes, notify_disclosures

log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """스냅샷 1건 처리 결과."""
    snapshot_created: bool = False
    changes: List[ClinicalTrialChange] = field(default_factory=list)

    @property
    def changes_detected(self) -> int:
        return len(self.changes)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _trial_context(trial: ClinicalTrial) -> Dict[str, Optional[str]]:
    """한국어 문장 생성에 쓰일 주어 재료."""
    return {
        "drug_ko": trial.drug.name_ko if trial.drug else None,
        "disease_ko": trial.disease.name_ko if trial.disease else None,
        "title_ko": trial.title_ko,
    }


def get_or_create_raw_document(db: Session, source_id: int, external_id: str,
                               url: Optional[str], payload: dict) -> RawDocument:
    """원본을 저장한다. 같은 내용이 이미 있으면 그것을 돌려준다.

    raw_document 에는 (source, external_id, content_hash) 유니크 제약이 걸려 있어서
    확인 없이 INSERT 하면 중복 시 예외가 나고, 그 순간 세션이 롤백되어
    **그 뒤의 수집이 전부 날아간다.** 반드시 이 함수를 거쳐야 한다.
    """
    c_hash = content_hash(payload)
    existing = db.scalars(
        select(RawDocument).where(
            RawDocument.source_id == source_id,
            RawDocument.external_id == external_id,
            RawDocument.content_hash == c_hash,
        ).limit(1)
    ).first()
    if existing is not None:
        return existing

    row = RawDocument(source_id=source_id, external_id=external_id,
                      url=url, payload=payload, content_hash=c_hash)
    db.add(row)
    db.flush()
    return row


def _latest_snapshot(db: Session, trial_id: int) -> Optional[ClinicalTrialSnapshot]:
    return db.scalars(
        select(ClinicalTrialSnapshot)
        .where(ClinicalTrialSnapshot.trial_id == trial_id)
        .order_by(desc(ClinicalTrialSnapshot.captured_at), desc(ClinicalTrialSnapshot.id))
        .limit(1)
    ).first()


def ingest_snapshot(db: Session, trial: ClinicalTrial, raw: dict,
                    snap_data: dict, source: Source) -> "IngestResult":
    """원본 1건을 받아 스냅샷을 만들고 이전 것과 비교한다.

    이 함수는 중복 수집에 안전하다 - 같은 내용이 다시 들어오면 아무 것도 만들지 않는다.
    """
    result = IngestResult()

    # --- 1차 필터: 원본이 완전히 같으면 raw_document 를 새로 만들지 않는다 (요구사항 22)
    existing_raw = get_or_create_raw_document(
        db, source.id, trial.registry_id, trial.url, raw)

    # --- 2차 필터: 추적 필드가 그대로면 diff 를 돌리지 않는다
    s_hash = snapshot_hash(snap_data)
    prev = _latest_snapshot(db, trial.id)
    if prev is not None and prev.snapshot_hash == s_hash:
        return result

    snapshot = ClinicalTrialSnapshot(
        trial_id=trial.id,
        raw_document_id=existing_raw.id,
        overall_status=snap_data.get("overall_status"),
        phase=snap_data.get("phase") or [],
        enrollment_count=snap_data.get("enrollment_count"),
        enrollment_type=snap_data.get("enrollment_type"),
        start_date=snap_data.get("start_date"),
        primary_completion_date=snap_data.get("primary_completion_date"),
        completion_date=snap_data.get("completion_date"),
        has_results=snap_data.get("has_results"),
        locations=snap_data.get("locations") or [],
        location_count=snap_data.get("location_count"),
        source_last_update=snap_data.get("source_last_update"),
        snapshot_hash=s_hash,
    )
    db.add(snapshot)
    db.flush()
    result.snapshot_created = True

    # --- diff
    changes = diff_snapshots(
        prev.as_dict() if prev else None,
        snap_data,
        _trial_context(trial),
    )
    for ch in changes:
        row = ClinicalTrialChange(
            trial_id=trial.id,
            prev_snapshot_id=prev.id if prev else None,
            curr_snapshot_id=snapshot.id,
            field_name=ch.field_name,
            old_value=ch.old_value,
            new_value=ch.new_value,
            old_value_ko=ch.old_value_ko,
            new_value_ko=ch.new_value_ko,
            severity=ch.severity,
            headline_ko=ch.headline_ko,
            detail_ko=ch.detail_ko,
        )
        db.add(row)
        result.changes.append(row)
    db.flush()
    return result


def collect_ctgov(db: Session, force: bool = False) -> CollectionRun:
    """관심 임상시험 전체를 CT.gov 에서 다시 확인한다."""
    run = CollectionRun(source_code=ctgov.SOURCE_CODE, started_at=_now())
    db.add(run)
    db.flush()

    source = db.scalars(select(Source).where(Source.code == ctgov.SOURCE_CODE)).first()
    if source is None:
        run.ok = False
        run.error = "source 'ctgov' 가 등록되어 있지 않습니다. seed 를 먼저 실행하세요."
        run.finished_at = _now()
        return run

    # ---- dataTimestamp 게이트 (docs/00_RESEARCH.md 제약 A)
    data_ts = ctgov.fetch_data_timestamp()
    force = force or settings.ctgov_force_fetch
    if (not force) and data_ts and source.upstream_data_timestamp == data_ts:
        run.ok = True
        run.skipped = True
        run.skip_reason = f"CT.gov 데이터 기준시각이 그대로입니다 ({data_ts}). 수집을 건너뜁니다."
        run.finished_at = _now()
        source.last_ok_at = _now()
        log.info(run.skip_reason)
        return run

    trials = list(db.scalars(
        select(ClinicalTrial).where(ClinicalTrial.registry == "CTGOV")
    ).all())

    new_changes: List[ClinicalTrialChange] = []
    errors: List[str] = []

    for trial in trials:
        try:
            raw = ctgov.fetch_study(trial.registry_id)
            trial_info, snap_data = ctgov.normalize(raw)

            # 고정 정보가 비어 있으면 채운다
            if not trial.title_en and trial_info.get("title_en"):
                trial.title_en = trial_info["title_en"]
            if not trial.org_study_id and trial_info.get("org_study_id"):
                trial.org_study_id = trial_info["org_study_id"]
            if trial_info.get("country"):
                trial.country = trial_info["country"]
                trial.region = trial_info["region"]

            stats = ingest_snapshot(db, trial, raw, snap_data, source)
            run.trials_checked += 1
            run.snapshots_created += int(stats.snapshot_created)
            run.changes_detected += stats.changes_detected
            new_changes.extend(stats.changes)
        except Exception as exc:                       # noqa: BLE001
            db.rollback()
            msg = f"{trial.registry_id}: {exc}"
            errors.append(msg)
            log.exception("수집 실패 %s", msg)

    if data_ts:
        source.upstream_data_timestamp = data_ts

    if errors:
        source.fail_streak += 1
        source.last_error = " | ".join(errors[:3])
        run.error = source.last_error
        run.ok = run.trials_checked > 0
    else:
        source.fail_streak = 0
        source.last_error = None
        source.last_ok_at = _now()
        run.ok = True

    run.finished_at = _now()
    db.flush()

    if new_changes:
        notify_changes(db, new_changes)
    return run


# ---------------------------------------------------------------------------
# DART 전자공시
# ---------------------------------------------------------------------------
# 본문(document.xml)까지 받아볼 공시 유형. 나머지는 제목만 저장한다.
_DETAIL_EVENT_TYPES = {
    "TRIAL_IND_APPROVE", "TRIAL_IND_APPLY",
    "TRIAL_AMEND_APPROVE", "TRIAL_AMEND_APPLY",
    "TRIAL_RESULT", "TRIAL_HALT", "PRODUCT_APPROVAL",
}


def _match_drug(db: Session, text: str) -> Optional[Drug]:
    """공시 제목/본문에 등장하는 약물을 검색어 사전으로 찾는다."""
    haystack = (text or "").lower()
    best = None
    for drug in db.scalars(select(Drug)).all():
        for alias in (drug.aliases or []) + [drug.name_ko, drug.name_en, drug.dev_code]:
            if not alias:
                continue
            a = alias.lower()
            if len(a) >= 3 and a in haystack:
                # 더 긴 별칭이 매칭되면 그쪽이 정확하다
                if best is None or len(a) > best[1]:
                    best = (drug, len(a))
    return best[0] if best else None


def collect_dart(db: Session, force: bool = False) -> CollectionRun:
    """관심 기업의 전자공시를 수집한다.

    접수번호(rcept_no)가 고유키라 중복 수집에 안전하다.
    어떤 기업의 공시를 처음 가져오는 경우에는 과거 공시가 전부 '새 소식'이 되어
    알림이 쏟아지므로, 그때는 저장만 하고 알림은 보내지 않는다(백필).
    """
    run = CollectionRun(source_code=dart.SOURCE_CODE, started_at=_now())
    db.add(run)
    db.flush()

    source = db.scalars(select(Source).where(Source.code == dart.SOURCE_CODE)).first()
    if source is None:
        run.ok, run.error = False, "source 'opendart' 가 없습니다. seed 를 먼저 실행하세요."
        run.finished_at = _now()
        return run

    if not settings.opendart_api_key:
        run.ok, run.skipped = True, True
        run.skip_reason = "DART 인증키가 설정되지 않았습니다 (.env 의 OPENDART_API_KEY)"
        run.finished_at = _now()
        return run

    companies = [c for c in db.scalars(select(Company)).all() if c.dart_corp_code]
    if not companies:
        run.ok, run.skipped = True, True
        run.skip_reason = "DART 고유번호(corp_code)가 등록된 기업이 없습니다"
        run.finished_at = _now()
        return run

    bgn_de, end_de = dart.default_range(settings.dart_lookback_days)
    fresh: List[Disclosure] = []
    errors: List[str] = []

    for company in companies:
        try:
            # 이 기업 공시를 처음 가져오는가?
            seen = db.scalar(
                select(func.count()).select_from(Disclosure)
                .where(Disclosure.company_id == company.id)
            ) or 0
            is_backfill = seen == 0

            items = dart.fetch_list(company.dart_corp_code, bgn_de, end_de)
            run.trials_checked += 1
            added_here = 0

            for item in items:
                rcept_no = item.get("rcept_no")
                if not rcept_no:
                    continue
                if db.scalars(select(Disclosure)
                              .where(Disclosure.rcept_no == rcept_no).limit(1)).first():
                    continue        # 이미 저장됨 (요구사항 22)

                report_nm = item.get("report_nm") or ""
                main, subtitle = dart.split_report_name(report_nm)
                event_type, severity = dart.classify(report_nm)

                details = None
                raw_doc_id = None
                if event_type in _DETAIL_EVENT_TYPES:
                    xml_text = dart.fetch_document_text(rcept_no)
                    if xml_text:
                        details = dart.parse_clinical_document(xml_text)
                        # 본문을 보고 분류를 다시 한다 (제목보다 정확하다)
                        event_type, severity = dart.classify(report_nm, details)
                        raw = get_or_create_raw_document(
                            db, source.id, rcept_no,
                            dart.VIEWER_URL.format(rcept_no=rcept_no),
                            {"report_nm": report_nm, "details": details,
                             "list_item": item},
                        )
                        raw_doc_id = raw.id

                search_text = " ".join(filter(None, [
                    report_nm, subtitle,
                    (details or {}).get("trial_name"), (details or {}).get("disease"),
                ]))
                drug = _match_drug(db, search_text)

                row = Disclosure(
                    source_id=source.id,
                    company_id=company.id,
                    drug_id=drug.id if drug else None,
                    raw_document_id=raw_doc_id,
                    rcept_no=rcept_no,
                    rcept_dt=dart.to_date(item["rcept_dt"]),
                    report_nm=" ".join(report_nm.split()),
                    subtitle=subtitle,
                    url=dart.VIEWER_URL.format(rcept_no=rcept_no),
                    event_type=event_type,
                    event_type_ko=dart.EVENT_KO.get(event_type, "기타 공시"),
                    severity=severity,
                    headline_ko=dart.build_headline(
                        company.name_ko, event_type, subtitle, details,
                        drug.name_ko if drug else None),
                    detail_ko=dart.build_detail(subtitle, details, fallback=main),
                    details=details,
                    is_notified=is_backfill,      # 백필분은 보낸 것으로 간주해 알림을 막는다
                )
                db.add(row)
                db.flush()
                run.changes_detected += 1
                added_here += 1
                if not is_backfill:
                    fresh.append(row)

            if added_here:
                log.info("%s: 새 공시 %d건%s", company.name_ko, added_here,
                         " (최초 수집이라 알림은 보내지 않습니다)" if is_backfill else "")
        except Exception as exc:                      # noqa: BLE001
            # 한 기업에서 실패해도 세션을 되살려 나머지 기업은 계속 처리한다
            db.rollback()
            errors.append(f"{company.name_ko}: {exc}")
            log.exception("DART 수집 실패 %s", company.name_ko)

    if errors:
        source.fail_streak += 1
        source.last_error = " | ".join(errors[:3])
        run.error = source.last_error
        run.ok = run.trials_checked > 0
    else:
        source.fail_streak = 0
        source.last_error = None
        source.last_ok_at = _now()
        run.ok = True

    run.finished_at = _now()
    db.flush()

    if fresh:
        notify_disclosures(db, fresh)
    return run
