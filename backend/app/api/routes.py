"""
REST API.

설계 원칙: 한국어 표시 문자열은 전부 서버에서 완성해서 내려보낸다.
프론트엔드는 렌더링만 하므로 화면마다 표기가 달라질 여지가 없다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.korean import (
    country_ko, date_ko, datetime_ko, enrollment_ko, phase_help, phase_ko,
    relative_ko, status_help, status_icon, status_ko,
)
from app.core.severity import SEVERITY_ORDER, severity_icon, severity_ko
from app.db import get_db
from app.models import (
    ClinicalTrial, ClinicalTrialChange, ClinicalTrialSnapshot,
    CollectionRun, Disclosure, Drug, Source, Watchlist,
)
from app.pipeline import collect_ctgov, collect_dart

router = APIRouter(prefix="/api")

KST = ZoneInfo("Asia/Seoul")


def _period(days: int) -> tuple[datetime, str]:
    """기간 필터. days=0 은 '오늘'(한국시간 자정부터)을 뜻한다.

    '최근 24시간'이 아니라 '오늘'이어야 한다.
    아침에 열었을 때 어제 저녁 소식이 섞여 나오면 '오늘 무슨 일이 있었나'를 알 수 없다.
    """
    if days <= 0:
        midnight = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.astimezone(timezone.utc), "오늘"
    if days == 1:
        return _now() - timedelta(days=1), "최근 24시간"
    return _now() - timedelta(days=days), f"최근 {days}일"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 직렬화 - 한국어 완성형
# ---------------------------------------------------------------------------
def _change_out(change: ClinicalTrialChange) -> Dict[str, Any]:
    """임상시험 변화 1건 -> 통합 업데이트 카드."""
    trial = change.trial
    meta: List[str] = []
    if trial:
        bits = [trial.drug.name_ko if trial.drug else None,
                trial.disease.name_ko if trial.disease else None,
                country_ko(trial.country) or None]
        line = " · ".join([b for b in bits if b])
        if line:
            meta.append(line)
        meta.append(f"등록번호 {trial.registry_id}")
    if change.detected_at:
        meta.append(f"{datetime_ko(change.detected_at)} 확인")

    return {
        "id": f"change-{change.id}",
        "kind": "TRIAL_CHANGE",
        "headline_ko": change.headline_ko,          # 화면에서 가장 크게 (요구사항 33-8)
        "detail_ko": change.detail_ko,
        "old_value_ko": change.old_value_ko,
        "new_value_ko": change.new_value_ko,
        "severity": change.severity,
        "severity_ko": severity_ko(change.severity),
        "severity_icon": severity_icon(change.severity),
        "detected_at": change.detected_at.isoformat() if change.detected_at else None,
        "detected_at_ko": datetime_ko(change.detected_at) if change.detected_at else "",
        "detected_relative_ko": relative_ko(change.detected_at) if change.detected_at else "",
        "is_read": change.is_read,
        # 요구사항 33-10: 공식 정보와 뉴스를 명확히 구분
        "source_kind_ko": "🏛 공식 임상정보",
        "source_name_ko": "미국 임상시험 등록소 (ClinicalTrials.gov)",
        "region_ko": ("🇰🇷 국내" if trial and trial.region == "KR" else "🌎 해외"),
        "meta_lines": meta,
        "internal_href": f"/trial/?id={trial.registry_id}" if trial else None,
        "external_url": trial.url if trial else None,
    }


def _disclosure_out(d: Disclosure) -> Dict[str, Any]:
    """전자공시 1건 -> 통합 업데이트 카드 (임상 변화와 같은 모양)."""
    meta: List[str] = []
    bits = [d.company.name_ko if d.company else None,
            d.drug.name_ko if d.drug else None]
    line = " · ".join([b for b in bits if b])
    if line:
        meta.append(line)
    meta.append(f"공시일 {date_ko(d.rcept_dt)}")

    return {
        "id": f"disclosure-{d.id}",
        "kind": "DISCLOSURE",
        "headline_ko": d.headline_ko,
        "detail_ko": d.detail_ko,
        "old_value_ko": None,
        "new_value_ko": None,
        "severity": d.severity,
        "severity_ko": severity_ko(d.severity),
        "severity_icon": severity_icon(d.severity),
        "detected_at": d.rcept_dt.isoformat() if d.rcept_dt else None,
        "detected_at_ko": date_ko(d.rcept_dt),
        "detected_relative_ko": relative_ko(
            datetime.combine(d.rcept_dt, datetime.min.time(), tzinfo=timezone.utc)
        ) if d.rcept_dt else "",
        "is_read": d.is_read,
        "source_kind_ko": "🏢 기업 공시 (DART)",
        "source_name_ko": "금융감독원 전자공시 — 법적 공시 의무 자료",
        "region_ko": "🇰🇷 국내",
        "event_type_ko": d.event_type_ko,
        "meta_lines": meta,
        "internal_href": None,
        "external_url": d.url,
    }


def _sorted_updates(items: List[Dict[str, Any]], limit: int = 60) -> List[Dict[str, Any]]:
    """중요한 것 먼저, 같은 등급이면 최신 먼저 (요구사항 33-1)."""
    return sorted(
        items,
        key=lambda c: (SEVERITY_ORDER.get(c["severity"], 9),
                       -(datetime.fromisoformat(c["detected_at"]).timestamp()
                         if c.get("detected_at") else 0)),
    )[:limit]


def _snapshot_out(snap: Optional[ClinicalTrialSnapshot]) -> Optional[Dict[str, Any]]:
    if snap is None:
        return None
    return {
        "id": snap.id,
        "captured_at": snap.captured_at.isoformat() if snap.captured_at else None,
        "captured_at_ko": datetime_ko(snap.captured_at) if snap.captured_at else "",
        "captured_relative_ko": relative_ko(snap.captured_at) if snap.captured_at else "",
        "status": snap.overall_status,
        "status_ko": status_ko(snap.overall_status),
        "status_icon": status_icon(snap.overall_status),
        "status_help_ko": status_help(snap.overall_status),
        "phase": list(snap.phase or []),
        "phase_ko": phase_ko(snap.phase),
        "phase_help_ko": phase_help(snap.phase),
        "enrollment_ko": enrollment_ko(snap.enrollment_count, snap.enrollment_type),
        "enrollment_count": snap.enrollment_count,
        "start_date_ko": date_ko(snap.start_date),
        "primary_completion_date_ko": date_ko(snap.primary_completion_date),
        "completion_date_ko": date_ko(snap.completion_date),
        "has_results": snap.has_results,
        "has_results_ko": "결과 등록됨" if snap.has_results else "아직 결과 없음",
        "source_last_update_ko": date_ko(snap.source_last_update),
        "location_count": snap.location_count,
        "locations": [
            {
                "facility": loc.get("facility"),
                "city": loc.get("city"),
                "country_ko": country_ko(loc.get("country")),
                # 등록소가 기관별 상태를 제공하지 않는 경우가 있다.
                # 없는 값을 시험 전체 상태로 대신 채우면 사실을 지어내는 것이므로 그대로 둔다.
                "status_ko": status_ko(loc.get("status")) if loc.get("status")
                             else "기관별 상태 미제공",
                "status_icon": status_icon(loc.get("status")) if loc.get("status") else "▫️",
            }
            for loc in (snap.locations or [])
        ],
    }


def _trial_out(db: Session, trial: ClinicalTrial) -> Dict[str, Any]:
    snap = db.scalars(
        select(ClinicalTrialSnapshot)
        .where(ClinicalTrialSnapshot.trial_id == trial.id)
        .order_by(desc(ClinicalTrialSnapshot.captured_at), desc(ClinicalTrialSnapshot.id))
        .limit(1)
    ).first()
    latest_change = db.scalars(
        select(ClinicalTrialChange)
        .where(ClinicalTrialChange.trial_id == trial.id)
        .order_by(desc(ClinicalTrialChange.detected_at), desc(ClinicalTrialChange.id))
        .limit(1)
    ).first()
    return {
        "id": trial.id,
        "registry": trial.registry,
        "registry_id": trial.registry_id,
        "org_study_id": trial.org_study_id,
        "url": trial.url,
        "title_en": trial.title_en,
        "title_ko": trial.title_ko,
        "drug_ko": trial.drug.name_ko if trial.drug else None,
        "drug_code": trial.drug.dev_code if trial.drug else None,
        "disease_ko": trial.disease.name_ko if trial.disease else None,
        "company_ko": trial.company.name_ko if trial.company else None,
        "country_ko": country_ko(trial.country),
        "region": trial.region,
        "region_ko": "🇰🇷 국내" if trial.region == "KR" else "🌎 해외",
        "is_watchlisted": trial.is_watchlisted,
        "current": _snapshot_out(snap),
        "latest_change": _change_out(latest_change) if latest_change else None,
    }


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 화면이 읽는 데이터 — GitHub Pages 의 정적 파일과 **같은 주소**로 맞춘다.
# 화면 코드가 배포 방식을 신경 쓰지 않아도 되게 하기 위함이다.
# ---------------------------------------------------------------------------
data_router = APIRouter(prefix="/data", tags=["data"])


@data_router.get("/dashboard-{days}.json")
def dashboard_file(days: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return dashboard(days=max(0, min(days, 365)), db=db)


@data_router.get("/trials/{registry_id}.json")
def trial_file(registry_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return trial_detail(registry_id, db=db)


@data_router.get("/disclosures.json")
def disclosures_file(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    return list_disclosures(days=365, limit=200, db=db)


@data_router.get("/meta.json")
def meta_file() -> Dict[str, Any]:
    return {"generated_at": _now().isoformat(), "periods": [0, 3, 7, 30], "live": True}


@router.get("/health")
def health(db: Session = Depends(get_db)) -> Dict[str, Any]:
    db.execute(select(func.count()).select_from(ClinicalTrial))
    return {"ok": True, "time": _now().isoformat()}


@router.get("/dashboard")
def dashboard(days: int = Query(0, ge=0, le=365),
              db: Session = Depends(get_db)) -> Dict[str, Any]:
    """첫 화면 한 방에 필요한 모든 것 (요구사항 16, 33-2).

    30초 안에 6개 질문에 답할 수 있도록 서버에서 미리 조립한다.
    """
    since, period_ko = _period(days)

    counts: Dict[str, int] = {}
    for sev_code, n in db.execute(
        select(ClinicalTrialChange.severity, func.count())
        .where(ClinicalTrialChange.detected_at >= since)
        .group_by(ClinicalTrialChange.severity)
    ).all():
        counts[sev_code] = counts.get(sev_code, 0) + n
    for sev_code, n in db.execute(
        select(Disclosure.severity, func.count())
        .where(Disclosure.rcept_dt >= since.date())
        .group_by(Disclosure.severity)
    ).all():
        counts[sev_code] = counts.get(sev_code, 0) + n
    summary = [
        {"severity": s, "severity_ko": severity_ko(s), "icon": severity_icon(s),
         "count": counts.get(s, 0)}
        for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    ]

    changes = db.scalars(
        select(ClinicalTrialChange)
        .where(ClinicalTrialChange.detected_at >= since)
        .order_by(desc(ClinicalTrialChange.detected_at), desc(ClinicalTrialChange.id))
        .limit(50)
    ).all()
    disclosures = db.scalars(
        select(Disclosure)
        .where(Disclosure.rcept_dt >= since.date())
        .order_by(desc(Disclosure.rcept_dt), desc(Disclosure.id))
        .limit(50)
    ).all()
    changes_out = _sorted_updates(
        [_change_out(c) for c in changes] + [_disclosure_out(d) for d in disclosures]
    )

    watched = db.scalars(
        select(ClinicalTrial).where(ClinicalTrial.is_watchlisted.is_(True))
    ).all()
    all_trials = db.scalars(select(ClinicalTrial)).all()

    # 규제기관·공시 섹션 (요구사항 16의 FDA / REGULATORY). 선택한 기간을 따른다.
    regulatory = db.scalars(
        select(Disclosure)
        .where(Disclosure.severity.in_(["CRITICAL", "HIGH"]),
               Disclosure.rcept_dt >= since.date())
        .order_by(desc(Disclosure.rcept_dt), desc(Disclosure.id))
        .limit(12)
    ).all()

    # 선택한 기간이 비어 있을 때 "그럼 언제 마지막으로 뭔가 있었나"를 알려주기 위한 값
    latest_any = db.scalars(
        select(Disclosure).order_by(desc(Disclosure.rcept_dt), desc(Disclosure.id)).limit(1)
    ).first()
    latest_change_any = db.scalars(
        select(ClinicalTrialChange)
        .order_by(desc(ClinicalTrialChange.detected_at), desc(ClinicalTrialChange.id)).limit(1)
    ).first()

    last_run = db.scalars(
        select(CollectionRun).order_by(desc(CollectionRun.started_at)).limit(1)
    ).first()

    today = _now()
    return {
        "generated_at": today.isoformat(),
        "today_ko": f"{today.year}년 {today.month}월 {today.day}일",
        "window_days": days,
        "period_ko": period_ko,
        "total_updates": sum(counts.values()),
        "summary": summary,
        "changes": changes_out,
        "watchlist": [_trial_out(db, t) for t in watched],
        "regulatory": _sorted_updates([_disclosure_out(d) for d in regulatory], limit=12),
        "latest_outside_window": (
            _disclosure_out(latest_any) if latest_any and
            (not latest_change_any or
             (latest_change_any.detected_at and
              latest_any.rcept_dt >= latest_change_any.detected_at.date()))
            else (_change_out(latest_change_any) if latest_change_any else None)
        ),
        "trials_domestic": [_trial_out(db, t) for t in all_trials if t.region == "KR"],
        "trials_global": [_trial_out(db, t) for t in all_trials if t.region != "KR"],
        "last_collection": {
            "at_ko": datetime_ko(last_run.started_at) if last_run else "아직 없음",
            "relative_ko": relative_ko(last_run.started_at) if last_run else "",
            "ok": last_run.ok if last_run else None,
            "skipped": last_run.skipped if last_run else None,
            "skip_reason": last_run.skip_reason if last_run else None,
        } if last_run else None,
    }


@router.get("/trials")
def list_trials(region: Optional[str] = None,
                db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    stmt = select(ClinicalTrial)
    if region:
        stmt = stmt.where(ClinicalTrial.region == region.upper())
    return [_trial_out(db, t) for t in db.scalars(stmt).all()]


@router.get("/trials/{registry_id}")
def trial_detail(registry_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    trial = db.scalars(
        select(ClinicalTrial).where(ClinicalTrial.registry_id == registry_id)
    ).first()
    if trial is None:
        raise HTTPException(404, f"임상시험 {registry_id} 을(를) 찾을 수 없습니다")

    snaps = db.scalars(
        select(ClinicalTrialSnapshot)
        .where(ClinicalTrialSnapshot.trial_id == trial.id)
        .order_by(desc(ClinicalTrialSnapshot.captured_at))
        .limit(50)
    ).all()
    changes = db.scalars(
        select(ClinicalTrialChange)
        .where(ClinicalTrialChange.trial_id == trial.id)
        .order_by(desc(ClinicalTrialChange.detected_at), desc(ClinicalTrialChange.id))
        .limit(100)
    ).all()

    out = _trial_out(db, trial)
    out["snapshot_count"] = len(snaps)
    out["history"] = [_snapshot_out(s) for s in snaps]
    out["changes"] = [_change_out(c) for c in changes]
    return out


@router.get("/changes")
def list_changes(severity: Optional[str] = None,
                 region: Optional[str] = None,
                 days: int = Query(30, ge=1, le=365),
                 limit: int = Query(100, ge=1, le=500),
                 db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    stmt = (select(ClinicalTrialChange)
            .where(ClinicalTrialChange.detected_at >= _now() - timedelta(days=days)))
    if severity:
        stmt = stmt.where(ClinicalTrialChange.severity == severity.upper())
    if region:
        stmt = stmt.join(ClinicalTrial).where(ClinicalTrial.region == region.upper())
    stmt = stmt.order_by(desc(ClinicalTrialChange.detected_at),
                         desc(ClinicalTrialChange.id)).limit(limit)
    return [_change_out(c) for c in db.scalars(stmt).all()]


@router.post("/changes/{change_id}/read")
def mark_read(change_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    change = db.get(ClinicalTrialChange, change_id)
    if change is None:
        raise HTTPException(404, "해당 변경 내역을 찾을 수 없습니다")
    change.is_read = True
    db.commit()
    return {"ok": True}


@router.get("/search")
def search(q: str = Query(..., min_length=1),
           db: Session = Depends(get_db)) -> Dict[str, Any]:
    """요구사항 18: 한글/영문/개발코드 어느 것으로 검색해도 찾아야 한다."""
    needle = q.strip().lower()
    trials = db.scalars(select(ClinicalTrial)).all()
    matched = []
    for t in trials:
        haystack = [t.registry_id or "", t.title_en or "", t.title_ko or "",
                    t.org_study_id or ""]
        for rel in (t.drug, t.disease, t.company):
            if rel is None:
                continue
            haystack += [getattr(rel, "name_ko", "") or "",
                         getattr(rel, "name_en", "") or "",
                         getattr(rel, "dev_code", "") or ""]
            haystack += list(getattr(rel, "aliases", None) or [])
        if any(needle in (h or "").lower() for h in haystack):
            matched.append(_trial_out(db, t))
    return {"query": q, "trial_count": len(matched), "trials": matched}


@router.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    items = db.scalars(select(Watchlist).order_by(Watchlist.sort_order)).all()
    return [{"id": w.id, "kind": w.kind, "ref_id": w.ref_id,
             "label_ko": w.label_ko} for w in items]


@router.post("/collect")
def trigger_collect(force: bool = Query(False, description="dataTimestamp 게이트를 무시하고 강제 수집"),
                    db: Session = Depends(get_db)) -> Dict[str, Any]:
    """앱의 '지금 새 정보 확인하기' 버튼. 두 소스를 모두 확인한다."""
    ct = collect_ctgov(db, force=force)
    db.commit()
    dt = collect_dart(db)
    db.commit()
    return {
        "ok": ct.ok and dt.ok,
        "skipped": ct.skipped and dt.skipped,
        "skip_reason": ct.skip_reason if ct.skipped else None,
        "trials_checked": ct.trials_checked,
        "snapshots_created": ct.snapshots_created,
        "changes_detected": ct.changes_detected + dt.changes_detected,
        "ctgov": {"skipped": ct.skipped, "changes": ct.changes_detected, "error": ct.error},
        "dart": {"skipped": dt.skipped, "skip_reason": dt.skip_reason,
                 "new_disclosures": dt.changes_detected, "error": dt.error},
        "error": ct.error or dt.error,
    }


@router.get("/disclosures")
def list_disclosures(severity: Optional[str] = None,
                     days: int = Query(365, ge=1, le=1825),
                     limit: int = Query(100, ge=1, le=500),
                     db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    stmt = select(Disclosure).where(Disclosure.rcept_dt >= (_now() - timedelta(days=days)).date())
    if severity:
        stmt = stmt.where(Disclosure.severity == severity.upper())
    stmt = stmt.order_by(desc(Disclosure.rcept_dt), desc(Disclosure.id)).limit(limit)
    return [_disclosure_out(d) for d in db.scalars(stmt).all()]


@router.post("/collect/dart")
def trigger_collect_dart(db: Session = Depends(get_db)) -> Dict[str, Any]:
    run = collect_dart(db)
    db.commit()
    return {
        "ok": run.ok, "skipped": run.skipped, "skip_reason": run.skip_reason,
        "companies_checked": run.trials_checked,
        "new_disclosures": run.changes_detected, "error": run.error,
    }


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    LEVEL_KO = {1: "공식 API", 2: "RSS", 3: "정적 HTML 크롤링", 4: "브라우저 렌더링"}
    return [{
        "code": s.code,
        "name_ko": s.name_ko,
        "kind_ko": {"REGISTRY": "🧪 임상시험 등록소", "REGULATOR": "🏛 규제기관",
                    "COMPANY": "🏢 기업 발표", "NEWS": "📰 뉴스",
                    "JOURNAL": "📄 논문"}.get(s.source_type, s.source_type),
        "region_ko": "🇰🇷 국내" if s.region == "KR" else "🌎 해외",
        "is_official": s.is_official,
        "collection_level": s.collection_level,
        "collection_level_ko": LEVEL_KO.get(s.collection_level, "-"),
        "last_ok_ko": relative_ko(s.last_ok_at) if s.last_ok_at else "없음",
        "fail_streak": s.fail_streak,
        "upstream_data_timestamp": s.upstream_data_timestamp,
    } for s in db.scalars(select(Source)).all()]
