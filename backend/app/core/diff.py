"""
임상시험 스냅샷 비교 엔진 (요구사항 9, 11).

이 모듈이 이 프로젝트의 핵심이다.
'어제 스냅샷'과 '오늘 스냅샷'을 받아 무엇이 달라졌는지 필드 단위로 찾아내고,
각 변화를 50~60대 사용자가 읽을 수 있는 한국어 한 문장으로 만든다.

한국어 문장은 LLM이 아니라 템플릿으로 생성한다 (요구사항 29-5).
  - 없는 사실을 만들어낼 수 없다
  - 비용/지연이 없다
  - 같은 입력에 항상 같은 문장이 나온다

의존성 없는 순수 함수 모듈이라 DB 없이 단위 테스트할 수 있다.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence

from app.core import severity as sev
from app.core.korean import (
    FIELD_KO,
    date_ko,
    enrollment_ko,
    josa,
    phase_ko,
    status_ko,
)

# 스냅샷에서 변화를 추적할 스칼라 필드
TRACKED_SCALAR_FIELDS: Sequence[str] = (
    "overall_status",
    "phase",
    "enrollment_count",
    "enrollment_type",
    "start_date",
    "primary_completion_date",
    "completion_date",
    "has_results",
    "source_last_update",
)

# 스냅샷 해시 계산에 포함할 필드 (source_last_update 는 제외 -
# 내용이 그대로인데 갱신일만 바뀌는 경우를 '변화 없음'으로 보기 위함)
_HASH_FIELDS: Sequence[str] = (
    "overall_status", "phase", "enrollment_count", "enrollment_type",
    "start_date", "primary_completion_date", "completion_date",
    "has_results", "locations",
)


@dataclass(frozen=True)
class FieldChange:
    """변화 1건. 그대로 clinical_trial_change 테이블 한 행이 된다."""
    field_name: str
    old_value: Optional[str]
    new_value: Optional[str]
    old_value_ko: Optional[str]
    new_value_ko: Optional[str]
    severity: str
    headline_ko: str      # 화면에서 가장 크게 보이는 문장 (요구사항 33-8)
    detail_ko: str        # 카드 안쪽 '기존 -> 현재' 상세

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 해시
# ---------------------------------------------------------------------------
def _canonical(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, dict):
        return {k: _canonical(value[k]) for k in sorted(value)}
    return value


def snapshot_hash(snapshot: Dict[str, Any]) -> str:
    """내용 기반 해시. 값이 같으면 diff 연산을 아예 건너뛴다 (요구사항 11의 1차 필터)."""
    payload = {f: _canonical(snapshot.get(f)) for f in _HASH_FIELDS}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def content_hash(payload: Any) -> str:
    blob = json.dumps(_canonical(payload), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 값 표시 헬퍼
# ---------------------------------------------------------------------------
def _display(field: str, value: Any, snapshot: Optional[Dict[str, Any]] = None) -> str:
    if value is None or value == "" or value == []:
        return "정보 없음"
    if field == "overall_status":
        return status_ko(value)
    if field == "phase":
        return phase_ko(value)
    if field == "enrollment_count":
        etype = (snapshot or {}).get("enrollment_type")
        return enrollment_ko(int(value), etype)
    if field == "enrollment_type":
        return {"ESTIMATED": "예상 인원", "ACTUAL": "실제 등록 인원"}.get(value, str(value))
    if field in {"start_date", "primary_completion_date", "completion_date", "source_last_update"}:
        return date_ko(value)
    if field == "has_results":
        return "결과 등록됨" if value else "결과 없음"
    return str(value)


def _raw(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


def _location_key(loc: Dict[str, Any]) -> str:
    facility = (loc.get("facility") or "").strip()
    city = (loc.get("city") or "").strip()
    return f"{facility}|{city}"


def _location_label(loc: Dict[str, Any]) -> str:
    facility = (loc.get("facility") or "이름 미상 기관").strip()
    city = (loc.get("city") or "").strip()
    return f"{facility}({city})" if city else facility


# ---------------------------------------------------------------------------
# 한국어 헤드라인 생성 (요구사항 33-8)
#   기사 제목이 아니라 '무슨 일이 일어났는지'를 문장으로 만든다.
# ---------------------------------------------------------------------------
def _subject(context: Optional[Dict[str, Any]]) -> str:
    """'제프티 댕기열 임상시험' 같은 주어를 만든다."""
    ctx = context or {}
    drug = (ctx.get("drug_ko") or "").strip()
    disease = (ctx.get("disease_ko") or "").strip()
    parts = [p for p in (drug, disease) if p]
    if parts:
        return " ".join(parts) + " 임상시험"
    return (ctx.get("title_ko") or "임상시험").strip()


_STATUS_HEADLINE = {
    "RECRUITING": "{subj}이 환자 모집을 시작했습니다",
    "ENROLLING_BY_INVITATION": "{subj}이 초청 대상자 모집을 시작했습니다",
    "ACTIVE_NOT_RECRUITING": "{subj}의 환자 모집이 끝나고 임상이 진행 중입니다",
    "COMPLETED": "{subj}이 종료되었습니다",
    "SUSPENDED": "{subj}이 일시 중단되었습니다",
    "TERMINATED": "{subj}이 조기 종료(중단)되었습니다",
    "WITHDRAWN": "{subj}이 취소(철회)되었습니다",
    "NOT_YET_RECRUITING": "{subj}이 모집 전 단계로 등록되었습니다",
}


def _headline(field: str, old: Any, new: Any, context: Optional[Dict[str, Any]],
              extra: Optional[Dict[str, Any]] = None) -> str:
    subj = _subject(context)
    subj_i = josa(subj, "이가")            # '임상시험이'
    subj_ui = subj + "의"
    extra = extra or {}

    if field == "overall_status":
        template = _STATUS_HEADLINE.get(new)
        if template:
            # 템플릿의 '{subj}이' 부분은 조사 처리가 이미 들어간 형태로 교체
            return template.format(subj=subj).replace(subj + "이", subj_i, 1)
        return f"{subj_ui} 상태가 '{status_ko(old)}'에서 " \
               f"{josa(chr(39) + status_ko(new) + chr(39), '으로')} 바뀌었습니다"

    if field == "has_results":
        if new and not old:
            return f"{subj_ui} 결과가 공식 등록되었습니다"
        return f"{subj_ui} 결과 등록 상태가 바뀌었습니다"

    if field == "enrollment_count":
        return (f"{subj_ui} 목표 인원이 {enrollment_ko(old) if old is not None else '정보 없음'}에서 "
                f"{josa(enrollment_ko(new) if new is not None else '정보 없음', '으로')} 바뀌었습니다")

    if field == "enrollment_type":
        if old == "ESTIMATED" and new == "ACTUAL":
            return f"{subj_ui} 등록 인원이 실제 인원으로 확정되었습니다"
        return f"{subj_ui} 인원 기준이 바뀌었습니다"

    if field == "primary_completion_date":
        return (f"{subj_ui} 주요 완료 예정일이 {date_ko(old)}에서 "
                f"{josa(date_ko(new), '으로')} 바뀌었습니다")

    if field == "completion_date":
        return (f"{subj_ui} 종료 예정일이 {date_ko(old)}에서 "
                f"{josa(date_ko(new), '으로')} 바뀌었습니다")

    if field == "start_date":
        return f"{subj_ui} 시작일이 {josa(date_ko(new), '으로')} 바뀌었습니다"

    if field == "phase":
        return (f"{subj_ui} 단계가 {phase_ko(old)}에서 "
                f"{josa(phase_ko(new), '으로')} 바뀌었습니다")

    # 기관명은 길고 영문이라 제목에 넣으면 읽기 어렵다.
    # 제목은 '무슨 일이 있었는가'만 짧게, 기관명은 detail 로 내린다 (요구사항 33-8, 33-12).
    if field == "locations_added":
        names = extra.get("names") or []
        return f"{subj_ui} 실시기관 {len(names)}곳이 새로 추가되었습니다"

    if field == "locations_removed":
        names = extra.get("names") or []
        return f"{subj_ui} 실시기관 {len(names)}곳이 제외되었습니다"

    if field == "location_status":
        name = extra.get("name", "한 기관")
        return (f"{name}의 모집 상태가 '{status_ko(old)}'에서 "
                f"{josa(chr(39) + status_ko(new) + chr(39), '으로')} 바뀌었습니다")

    if field == "source_last_update":
        return f"{subj_ui} 등록정보가 갱신되었습니다"

    label = FIELD_KO.get(field, field)
    return f"{subj_ui} {label}이(가) 바뀌었습니다"


# ---------------------------------------------------------------------------
# 메인 diff
# ---------------------------------------------------------------------------
def diff_snapshots(prev: Optional[Dict[str, Any]],
                   curr: Dict[str, Any],
                   context: Optional[Dict[str, Any]] = None) -> List[FieldChange]:
    """이전 스냅샷과 현재 스냅샷을 비교해 변화 목록을 만든다.

    prev 가 None 이면 최초 수집이므로 변화를 만들지 않는다.
    (없던 임상이 새로 생긴 것은 '변화'가 아니라 '신규 등록'이며 별도로 다룬다.)
    """
    if prev is None:
        return []

    changes: List[FieldChange] = []

    # 1) 스칼라 필드
    for field in TRACKED_SCALAR_FIELDS:
        old, new = prev.get(field), curr.get(field)
        if isinstance(old, (list, tuple)) or isinstance(new, (list, tuple)):
            if list(old or []) == list(new or []):
                continue
        elif old == new:
            continue

        severity = sev.classify(field, old, new)
        changes.append(FieldChange(
            field_name=field,
            old_value=_raw(old),
            new_value=_raw(new),
            old_value_ko=_display(field, old, prev),
            new_value_ko=_display(field, new, curr),
            severity=severity,
            headline_ko=_headline(field, old, new, context),
            detail_ko=f"기존: {_display(field, old, prev)}\n현재: {_display(field, new, curr)}",
        ))

    # 2) 실시기관 (요구사항 9: 기관 추가 감지)
    changes.extend(_diff_locations(prev.get("locations") or [],
                                   curr.get("locations") or [],
                                   context))
    return changes


def _diff_locations(prev_locs: List[Dict[str, Any]],
                    curr_locs: List[Dict[str, Any]],
                    context: Optional[Dict[str, Any]]) -> List[FieldChange]:
    prev_map = {_location_key(l): l for l in prev_locs}
    curr_map = {_location_key(l): l for l in curr_locs}

    added_keys = [k for k in curr_map if k not in prev_map]
    removed_keys = [k for k in prev_map if k not in curr_map]
    changes: List[FieldChange] = []

    if added_keys:
        names = [_location_label(curr_map[k]) for k in added_keys]
        changes.append(FieldChange(
            field_name="locations_added",
            old_value=str(len(prev_locs)),
            new_value=str(len(curr_locs)),
            old_value_ko=f"{len(prev_locs)}곳",
            new_value_ko=f"{len(curr_locs)}곳",
            severity=sev.classify("locations_added", None, names),
            headline_ko=_headline("locations_added", None, names, context, {"names": names}),
            detail_ko="추가된 기관:\n" + "\n".join(f"· {n}" for n in names),
        ))

    if removed_keys:
        names = [_location_label(prev_map[k]) for k in removed_keys]
        changes.append(FieldChange(
            field_name="locations_removed",
            old_value=str(len(prev_locs)),
            new_value=str(len(curr_locs)),
            old_value_ko=f"{len(prev_locs)}곳",
            new_value_ko=f"{len(curr_locs)}곳",
            severity=sev.classify("locations_removed", None, names),
            headline_ko=_headline("locations_removed", None, names, context, {"names": names}),
            detail_ko="제외된 기관:\n" + "\n".join(f"· {n}" for n in names),
        ))

    # 기관별 모집 상태 변경
    for key in sorted(set(prev_map) & set(curr_map)):
        old_status = prev_map[key].get("status")
        new_status = curr_map[key].get("status")
        if old_status == new_status:
            continue
        name = _location_label(curr_map[key])
        changes.append(FieldChange(
            field_name="location_status",
            old_value=f"{key}:{old_status}",
            new_value=f"{key}:{new_status}",
            old_value_ko=status_ko(old_status),
            new_value_ko=status_ko(new_status),
            severity=sev.classify("location_status", old_status, new_status),
            headline_ko=_headline("location_status", old_status, new_status, context, {"name": name}),
            detail_ko=f"{name}\n기존: {status_ko(old_status)}\n현재: {status_ko(new_status)}",
        ))

    return changes


def overall_severity(changes: Sequence[FieldChange]) -> str:
    return sev.worst([c.severity for c in changes])
