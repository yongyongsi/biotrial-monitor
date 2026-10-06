"""
PoC 검증용 엔드포인트 (요구사항 26: 테스트 데이터로 상태 변경 감지를 검증한다).

실제 CT.gov 데이터가 바뀌기를 기다리지 않고, 과거 스냅샷을 인위적으로 만들어
변화 감지가 end-to-end 로 동작하는지 확인한다.
운영 데이터를 건드리므로 경로를 /api/demo 로 분리해 두었다.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.core.diff import snapshot_hash
from app.db import get_db
from app.models import (
    Alert, ClinicalTrial, ClinicalTrialChange, ClinicalTrialSnapshot,
)
from app.pipeline import ingest_snapshot, _now
from app.models import Source
from app.collectors import ctgov

router = APIRouter(prefix="/api/demo", tags=["demo"])


class SimulateRequest(BaseModel):
    registry_id: str
    overall_status: Optional[str] = None
    enrollment_count: Optional[int] = None
    primary_completion_date: Optional[str] = None
    completion_date: Optional[str] = None
    has_results: Optional[bool] = None
    drop_last_location: bool = False


@router.post("/simulate-previous")
def simulate_previous(req: SimulateRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """현재 스냅샷을 기준으로 '과거에는 이랬다'는 스냅샷을 주입한다.

    그 다음 CT.gov 에서 실제 데이터를 다시 받아오면 diff 가 발생해야 한다.
    """
    trial = db.scalars(
        select(ClinicalTrial).where(ClinicalTrial.registry_id == req.registry_id)
    ).first()
    if trial is None:
        raise HTTPException(404, f"{req.registry_id} 을(를) 찾을 수 없습니다")

    latest = db.scalars(
        select(ClinicalTrialSnapshot)
        .where(ClinicalTrialSnapshot.trial_id == trial.id)
        .order_by(desc(ClinicalTrialSnapshot.captured_at), desc(ClinicalTrialSnapshot.id))
        .limit(1)
    ).first()
    if latest is None:
        raise HTTPException(400, "먼저 /api/collect 로 최소 1회 수집해야 합니다")

    data = latest.as_dict()
    if req.overall_status is not None:
        data["overall_status"] = req.overall_status
    if req.enrollment_count is not None:
        data["enrollment_count"] = req.enrollment_count
    if req.primary_completion_date is not None:
        data["primary_completion_date"] = req.primary_completion_date
    if req.completion_date is not None:
        data["completion_date"] = req.completion_date
    if req.has_results is not None:
        data["has_results"] = req.has_results
    if req.drop_last_location and data.get("locations"):
        data["locations"] = data["locations"][:-1]

    # 현재 스냅샷을 지우고, 조작된 '과거' 스냅샷만 남긴다
    db.execute(delete(ClinicalTrialChange).where(ClinicalTrialChange.trial_id == trial.id))
    db.execute(delete(ClinicalTrialSnapshot).where(ClinicalTrialSnapshot.trial_id == trial.id))

    past = ClinicalTrialSnapshot(
        trial_id=trial.id,
        overall_status=data.get("overall_status"),
        phase=data.get("phase") or [],
        enrollment_count=data.get("enrollment_count"),
        enrollment_type=data.get("enrollment_type"),
        start_date=data.get("start_date"),
        primary_completion_date=data.get("primary_completion_date"),
        completion_date=data.get("completion_date"),
        has_results=data.get("has_results"),
        locations=data.get("locations") or [],
        location_count=len(data.get("locations") or []),
        source_last_update=data.get("source_last_update"),
        snapshot_hash=snapshot_hash(data),
        captured_at=_now() - timedelta(days=1),
    )
    db.add(past)
    db.commit()
    return {
        "ok": True,
        "message": f"{req.registry_id} 의 '어제 스냅샷'을 주입했습니다. "
                   f"이제 POST /api/collect?force=true 를 호출하면 변화가 감지됩니다.",
        "injected_snapshot_id": past.id,
        "injected": {k: data.get(k) for k in
                     ("overall_status", "enrollment_count", "primary_completion_date",
                      "completion_date", "has_results")},
    }


@router.post("/reset")
def reset(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """스냅샷/변화/알림을 모두 지운다. 임상시험/약물 마스터는 남긴다."""
    db.execute(delete(Alert))
    db.execute(delete(ClinicalTrialChange))
    db.execute(delete(ClinicalTrialSnapshot))
    for s in db.scalars(select(Source)).all():
        s.upstream_data_timestamp = None
    db.commit()
    return {"ok": True, "message": "스냅샷과 변경 이력을 초기화했습니다."}
