"""
ClinicalTrials.gov API v2 수집기 (수집 Level 1: 공식 API).

핵심 최적화 - docs/00_RESEARCH.md 제약 A:
    CT.gov 는 1일 1회 배치로 갱신된다. /api/v2/version 이 dataTimestamp 를 알려주므로
    그 값이 지난번과 같으면 전체 수집을 건너뛴다. 호출량이 1/10 이하로 줄고 정확도는 동일하다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings

log = logging.getLogger(__name__)

API_BASE = "https://clinicaltrials.gov/api/v2"
STUDY_URL = "https://clinicaltrials.gov/study/{nct_id}"
SOURCE_CODE = "ctgov"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _client() -> httpx.Client:
    return httpx.Client(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": settings.user_agent, "Accept": "application/json"},
    )


def fetch_data_timestamp() -> Optional[str]:
    """CT.gov 데이터 기준시각. 이 값이 그대로면 수집을 건너뛴다."""
    try:
        with _client() as c:
            r = c.get(f"{API_BASE}/version")
            r.raise_for_status()
            return r.json().get("dataTimestamp")
    except Exception as exc:                      # noqa: BLE001
        log.warning("CT.gov version 조회 실패: %s", exc)
        return None


def fetch_study(nct_id: str) -> Dict[str, Any]:
    with _client() as c:
        r = c.get(f"{API_BASE}/studies/{nct_id}", params={"format": "json"})
        r.raise_for_status()
        return r.json()


def search_studies(*, sponsor: Optional[str] = None, term: Optional[str] = None,
                   page_size: int = 50) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"format": "json", "pageSize": page_size}
    if sponsor:
        params["query.spons"] = sponsor
    if term:
        params["query.term"] = term
    with _client() as c:
        r = c.get(f"{API_BASE}/studies", params=params)
        r.raise_for_status()
        return r.json().get("studies", [])


# ---------------------------------------------------------------------------
# 정규화  (raw JSON -> 공통 스냅샷 형태)
#   순수 함수이므로 네트워크 없이 단위 테스트할 수 있다.
# ---------------------------------------------------------------------------
def _date_of(struct: Optional[Dict[str, Any]]) -> Optional[str]:
    return (struct or {}).get("date")


def normalize(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """CT.gov 원본 JSON -> (임상시험 고정정보, 스냅샷).

    반환되는 스냅샷 dict 의 키는 app.core.diff.TRACKED_SCALAR_FIELDS 와 일치한다.
    """
    p = raw.get("protocolSection", {}) or {}
    ident = p.get("identificationModule", {}) or {}
    status = p.get("statusModule", {}) or {}
    design = p.get("designModule", {}) or {}
    sponsor = p.get("sponsorCollaboratorsModule", {}) or {}
    conds = p.get("conditionsModule", {}) or {}
    contacts = p.get("contactsLocationsModule", {}) or {}

    nct_id = ident.get("nctId")
    locations = [
        {
            "facility": loc.get("facility"),
            "city": loc.get("city"),
            "state": loc.get("state"),
            "country": loc.get("country"),
            "status": loc.get("status"),
        }
        for loc in (contacts.get("locations") or [])
    ]
    countries = [l["country"] for l in locations if l.get("country")]
    primary_country = countries[0] if countries else None

    trial = {
        "registry": "CTGOV",
        "registry_id": nct_id,
        "org_study_id": (ident.get("orgStudyIdInfo") or {}).get("id"),
        "url": STUDY_URL.format(nct_id=nct_id) if nct_id else None,
        "title_en": ident.get("briefTitle"),
        "official_title": ident.get("officialTitle"),
        "sponsor_name": (sponsor.get("leadSponsor") or {}).get("name"),
        "conditions": conds.get("conditions") or [],
        "country": primary_country,
        "region": "KR" if primary_country in {"South Korea", "Korea, Republic of"} else "GLOBAL",
    }

    enrollment = design.get("enrollmentInfo") or {}
    snapshot = {
        "overall_status": status.get("overallStatus"),
        "phase": list(design.get("phases") or []),
        "enrollment_count": enrollment.get("count"),
        "enrollment_type": enrollment.get("type"),
        "start_date": _date_of(status.get("startDateStruct")),
        "primary_completion_date": _date_of(status.get("primaryCompletionDateStruct")),
        "completion_date": _date_of(status.get("completionDateStruct")),
        "has_results": bool(raw.get("hasResults")),
        "locations": locations,
        "location_count": len(locations),
        "source_last_update": _date_of(status.get("lastUpdatePostDateStruct")),
    }
    return trial, snapshot


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
