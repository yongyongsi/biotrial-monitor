"""CT.gov 정규화 검증. 실제 API 응답 구조를 그대로 넣어 확인한다."""
from __future__ import annotations

from app.collectors.ctgov import normalize

# 2026-09-27 실제 조회한 NCT07576868 응답에서 필요한 부분만 발췌
REAL_RAW = {
    "protocolSection": {
        "identificationModule": {
            "nctId": "NCT07576868",
            "orgStudyIdInfo": {"id": "DEN-201"},
            "briefTitle": ("A Study of CP-COV03 Compared With Placebo in Participants "
                           "With Dengue (Part 1) and Dengue-like Illness (Part 2)"),
            "officialTitle": "A Randomized, Double-blinded, Placebo-controlled Clinical Trial ...",
        },
        "statusModule": {
            "overallStatus": "RECRUITING",
            "startDateStruct": {"date": "2026-04-09", "type": "ACTUAL"},
            "primaryCompletionDateStruct": {"date": "2027-01", "type": "ESTIMATED"},
            "completionDateStruct": {"date": "2027-05", "type": "ESTIMATED"},
            "lastUpdatePostDateStruct": {"date": "2026-07-10", "type": "ACTUAL"},
        },
        "sponsorCollaboratorsModule": {
            "leadSponsor": {"name": "Hyundai Bioscience Co., Ltd.", "class": "INDUSTRY"}
        },
        "designModule": {
            "phases": ["PHASE2", "PHASE3"],
            "studyType": "INTERVENTIONAL",
            "enrollmentInfo": {"count": 210, "type": "ESTIMATED"},
        },
        "conditionsModule": {"conditions": ["Dengue"]},
        "contactsLocationsModule": {
            "locations": [
                {"facility": "The National Hospital of Tropical Diseases (NHTD)",
                 "city": "Hanoi", "country": "Vietnam", "status": "RECRUITING"},
                {"facility": "Tien Giang Provincial General Hospital",
                 "city": "Mỹ Tho", "country": "Vietnam", "status": "RECRUITING"},
            ]
        },
    },
    "hasResults": False,
}


def test_임상시험_고정정보를_추출한다():
    trial, _ = normalize(REAL_RAW)
    assert trial["registry"] == "CTGOV"
    assert trial["registry_id"] == "NCT07576868"
    assert trial["org_study_id"] == "DEN-201"
    assert trial["url"] == "https://clinicaltrials.gov/study/NCT07576868"
    assert trial["sponsor_name"] == "Hyundai Bioscience Co., Ltd."
    assert trial["conditions"] == ["Dengue"]
    assert trial["country"] == "Vietnam"
    assert trial["region"] == "GLOBAL"


def test_스냅샷_필드를_정확히_추출한다():
    _, snap = normalize(REAL_RAW)
    assert snap["overall_status"] == "RECRUITING"
    assert snap["phase"] == ["PHASE2", "PHASE3"]
    assert snap["enrollment_count"] == 210
    assert snap["enrollment_type"] == "ESTIMATED"
    assert snap["start_date"] == "2026-04-09"
    assert snap["primary_completion_date"] == "2027-01"
    assert snap["completion_date"] == "2027-05"
    assert snap["has_results"] is False
    assert snap["source_last_update"] == "2026-07-10"
    assert snap["location_count"] == 2


def test_베트남_2개_기관을_모두_추출한다():
    _, snap = normalize(REAL_RAW)
    facilities = [l["facility"] for l in snap["locations"]]
    assert "The National Hospital of Tropical Diseases (NHTD)" in facilities
    assert "Tien Giang Provincial General Hospital" in facilities
    assert all(l["country"] == "Vietnam" for l in snap["locations"])
    assert all(l["status"] == "RECRUITING" for l in snap["locations"])


def test_국내임상은_region이_KR이다():
    raw = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT07683013"},
            "statusModule": {"overallStatus": "NOT_YET_RECRUITING"},
            "designModule": {},
            "contactsLocationsModule": {
                "locations": [{"facility": "Seoul National University Hospital",
                               "city": "Seoul", "country": "South Korea"}]
            },
        },
        "hasResults": False,
    }
    trial, _ = normalize(raw)
    assert trial["region"] == "KR"


def test_빈_응답에도_죽지_않는다():
    trial, snap = normalize({})
    assert trial["registry_id"] is None
    assert snap["locations"] == []
    assert snap["location_count"] == 0


def test_정규화_결과는_diff엔진에_바로_들어간다():
    from app.core.diff import diff_snapshots
    _, snap = normalize(REAL_RAW)
    prev = dict(snap, overall_status="NOT_YET_RECRUITING")
    changes = diff_snapshots(prev, snap, {"drug_ko": "제프티", "disease_ko": "댕기열"})
    assert len(changes) == 1
    assert changes[0].headline_ko == "제프티 댕기열 임상시험이 환자 모집을 시작했습니다"
