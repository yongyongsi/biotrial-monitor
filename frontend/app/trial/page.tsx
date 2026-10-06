"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChangeCard } from "@/components/ChangeCard";
import { getTrial } from "@/lib/api";
import type { Trial } from "@/lib/types";

/**
 * 임상시험 상세 (요구사항 19: 임상시험 상세 페이지 제공).
 *
 * 레이블과 값을 분리하고(33-3), 영어 원문은 작게 아래에 붙이고(33-4),
 * 진행 상황은 복잡한 차트 대신 단순 타임라인으로 보여준다(33-14).
 */
export default function TrialPage() {
  // 정적 내보내기(휴대폰용)에서도 동작하도록 동적 경로 대신 ?id= 를 쓴다.
  return (
    <Suspense fallback={<div className="empty">불러오는 중입니다…</div>}>
      <TrialDetail />
    </Suspense>
  );
}

function TrialDetail() {
  const registryId = useSearchParams().get("id") ?? "";
  const [trial, setTrial] = useState<Trial | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!registryId) {
      setError("임상시험을 찾을 수 없습니다.");
      return;
    }
    getTrial(registryId)
      .then(setTrial)
      .catch(() => setError("임상시험 정보를 불러오지 못했습니다."));
  }, [registryId]);

  if (error) {
    return (
      <>
        <Link href="/" className="back-link">← 처음으로</Link>
        <div className="notice warn">{error}</div>
      </>
    );
  }
  if (!trial) {
    return (
      <>
        <Link href="/" className="back-link">← 처음으로</Link>
        <div className="empty">불러오는 중입니다…</div>
      </>
    );
  }

  const c = trial.current;

  return (
    <>
      <Link href="/" className="back-link">← 처음으로</Link>

      <header className="app-header" style={{ paddingTop: 4 }}>
        <h1 className="app-title">
          {[trial.drug_ko, trial.disease_ko].filter(Boolean).join(" · ") || trial.registry_id}
        </h1>
        <div className="app-date">
          {trial.region === "KR" ? trial.region_ko : `${trial.region_ko} · ${trial.country_ko}`}
          {trial.company_ko ? ` · ${trial.company_ko}` : ""}
        </div>
      </header>

      {/* 현재 상태를 가장 크게 */}
      <section className="section" style={{ marginTop: 10 }}>
        <div className="card">
          <div className="kv-grid">
            <div className="kv">
              <div className="k">현재 상태</div>
              <div className="v">
                <span className="status-big">
                  <span aria-hidden="true">{c?.status_icon ?? "⚪"}</span>
                  <span>{c?.status_ko ?? "확인 전"}</span>
                </span>
                {/* 원문 데이터의 의미가 달라질 수 있으므로 영어 원문을 함께 작게 표시 (33-4) */}
                {c?.status && <span className="en">{c.status}</span>}
              </div>
              {c?.status_help_ko && (
                <details className="help">
                  <summary>ⓘ 이 상태가 무슨 뜻인가요?</summary>
                  <p>{c.status_help_ko}</p>
                </details>
              )}
            </div>

            <div className="kv">
              <div className="k">임상시험 단계</div>
              <div className="v">{c?.phase_ko ?? "정보 없음"}</div>
              {c?.phase_help_ko && (
                <details className="help">
                  <summary>ⓘ 이 단계는 무엇인가요?</summary>
                  <p>{c.phase_help_ko}</p>
                </details>
              )}
            </div>

            <div className="kv">
              <div className="k">👤 목표 등록 인원</div>
              <div className="v">{c?.enrollment_ko ?? "정보 없음"}</div>
            </div>
            <div className="kv">
              <div className="k">시험 시작일</div>
              <div className="v">{c?.start_date_ko ?? "정보 없음"}</div>
            </div>
            <div className="kv">
              <div className="k">주요 임상 완료 예정일</div>
              <div className="v">{c?.primary_completion_date_ko ?? "정보 없음"}</div>
              <details className="help">
                <summary>ⓘ 주요 임상 완료 예정일이란?</summary>
                <p>
                  가장 중요한 평가 항목의 측정이 끝나는 시점입니다.
                  이 날짜가 미뤄지면 결과 발표도 함께 늦어지는 경우가 많습니다.
                  (영어 원문: Primary Completion Date)
                </p>
              </details>
            </div>
            <div className="kv">
              <div className="k">시험 전체 종료 예정일</div>
              <div className="v">{c?.completion_date_ko ?? "정보 없음"}</div>
            </div>
            <div className="kv">
              <div className="k">결과 등록 여부</div>
              <div className="v">
                {c?.has_results ? "✅ " : "▫️ "}{c?.has_results_ko ?? "정보 없음"}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 진행 상황 타임라인 (요구사항 33-14) */}
      {c && (
        <section className="section">
          <h2 className="section-title"><span aria-hidden="true">📅</span>진행 상황</h2>
          <div className="card">
            <ul className="timeline">
              <li>
                <div className="t-when">{c.start_date_ko}</div>
                <div className="t-what">임상시험 시작</div>
              </li>
              <li className="is-now">
                <div className="t-when">지금</div>
                <div className="t-what">{c.status_icon} {c.status_ko}</div>
              </li>
              <li>
                <div className="t-when">{c.primary_completion_date_ko}</div>
                <div className="t-what">주요 임상 완료 예정</div>
              </li>
              <li>
                <div className="t-when">{c.completion_date_ko}</div>
                <div className="t-what">시험 전체 종료 예정</div>
              </li>
            </ul>
          </div>
        </section>
      )}

      {/* 실시기관 */}
      {c && c.locations.length > 0 && (
        <section className="section">
          <h2 className="section-title">
            <span aria-hidden="true">🏥</span>실시기관 {c.location_count}곳
          </h2>
          <div className="card">
            {c.locations.map((loc, i) => (
              <div className="facility" key={i}>
                <div className="fname">{loc.facility ?? "이름 미상"}</div>
                <div className="fmeta">
                  {loc.country_ko}
                  {loc.city ? ` · ${loc.city}` : ""}
                  {" · "}
                  <span aria-hidden="true">{loc.status_icon}</span> {loc.status_ko}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 변경 이력 */}
      <section className="section">
        <h2 className="section-title"><span aria-hidden="true">🔁</span>변경 이력</h2>
        <p className="section-note">
          공식 등록정보에서 달라진 내용만 모았습니다.
          {typeof trial.snapshot_count === "number" && ` (보관된 기록 ${trial.snapshot_count}개)`}
        </p>
        {!trial.changes || trial.changes.length === 0
          ? <div className="empty">아직 기록된 변화가 없습니다.</div>
          : trial.changes.map((ch) => <ChangeCard key={ch.id} change={ch} />)}
      </section>

      {/* 출처 - 모든 정보에 원문 링크를 남긴다 (요구사항 29-2) */}
      <section className="section">
        <h2 className="section-title"><span aria-hidden="true">🏛</span>정보 출처</h2>
        <div className="card">
          <div className="kv-grid">
            <div className="kv">
              <div className="k">출처</div>
              <div className="v">
                미국 임상시험 등록소
                <span className="en">ClinicalTrials.gov · 공식 등록정보</span>
              </div>
            </div>
            <div className="kv">
              <div className="k">임상시험 등록번호</div>
              <div className="v">{trial.registry_id}</div>
            </div>
            {trial.org_study_id && (
              <div className="kv">
                <div className="k">회사 자체 과제번호</div>
                <div className="v">{trial.org_study_id}</div>
              </div>
            )}
            <div className="kv">
              <div className="k">등록정보 갱신일</div>
              <div className="v">{c?.source_last_update_ko ?? "정보 없음"}</div>
            </div>
            {trial.title_en && (
              <div className="kv">
                <div className="k">영문 제목(원문)</div>
                <div className="v" style={{ fontWeight: 500, fontSize: "var(--fs-small)" }}>
                  {trial.title_en}
                </div>
              </div>
            )}
          </div>
          {trial.url && (
            <a className="source-link" href={trial.url} target="_blank" rel="noreferrer">
              공식 원문 보기 ↗
            </a>
          )}
        </div>
      </section>
    </>
  );
}
