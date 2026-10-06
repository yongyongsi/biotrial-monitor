import Link from "next/link";
import type { Trial } from "@/lib/types";

/** 관심 임상시험 요약 카드. 레이블과 값을 분리해 보여준다 (요구사항 33-3). */
export function TrialCard({ trial }: { trial: Trial }) {
  const c = trial.current;
  return (
    <Link
      href={`/trial/?id=${trial.registry_id}`}
      className={`card trial-card ${trial.is_watchlisted ? "is-watch" : ""}`}
    >
      <p className="trial-name">
        {trial.is_watchlisted ? "⭐ " : ""}
        {[trial.drug_ko, trial.disease_ko].filter(Boolean).join(" · ") || trial.registry_id}
      </p>
      {/* 국내 임상은 '국내 · 대한민국'이 중복이므로 한 번만 표시한다 */}
      <div className="trial-sub">
        {trial.region === "KR"
          ? trial.region_ko
          : `${trial.region_ko} · ${trial.country_ko || "국가 정보 없음"}`}
      </div>

      <div className="kv-grid">
        <div className="kv">
          <div className="k">현재 상태</div>
          <div className="v">
            <span className="status-big">
              <span aria-hidden="true">{c?.status_icon ?? "⚪"}</span>
              <span>{c?.status_ko ?? "아직 확인 전"}</span>
            </span>
          </div>
        </div>
        <div className="kv">
          <div className="k">임상시험 단계</div>
          <div className="v">{c?.phase_ko ?? "정보 없음"}</div>
        </div>
        <div className="kv">
          <div className="k">주요 임상 완료 예정일</div>
          <div className="v">{c?.primary_completion_date_ko ?? "정보 없음"}</div>
        </div>
      </div>

      {trial.latest_change && (
        <div className="card-meta">
          <span className="src">
            {trial.latest_change.severity_icon} 최근 변화 · {trial.latest_change.detected_relative_ko}
          </span>
          <span>{trial.latest_change.headline_ko}</span>
        </div>
      )}
    </Link>
  );
}
