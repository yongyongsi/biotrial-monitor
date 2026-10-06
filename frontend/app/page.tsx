"use client";

import { useCallback, useEffect, useState } from "react";
import { ChangeCard } from "@/components/ChangeCard";
import { TrialCard } from "@/components/TrialCard";
import { getDashboard, markServerAvailable, runCollect } from "@/lib/api";
import type { Dashboard } from "@/lib/types";

/** 기간 선택. 기본은 '오늘' — 지금 무슨 일이 있었는지가 가장 중요하다. */
const PERIODS = [
  { days: 0, label: "오늘" },
  { days: 3, label: "3일" },
  { days: 7, label: "7일" },
  { days: 30, label: "30일" },
] as const;
const PERIOD_KEY = "biotrial.period";

/**
 * 첫 화면 (요구사항 16, 33-2, 33-15).
 *
 * 30초 안에 아래 질문에 답할 수 있어야 한다:
 *   1) 오늘 새로운 정보가 있는가        -> 요약 카운트
 *   2) 관심 약물에 변화가 있는가        -> 관심 정보 섹션 (맨 위 고정)
 *   3) 임상시험은 어떻게 진행 중인가     -> 카드의 '현재 상태'
 *   4) 해외에서 먼저 나온 것이 있는가    -> 국내/해외 탭
 *   5) 규제기관 발표가 있는가           -> 출처 표시 (Phase 2 에서 확장)
 *   6) 정상 진행 중인가                -> 상태 아이콘 + 텍스트
 */
export default function HomePage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [tab, setTab] = useState<"KR" | "GLOBAL">("GLOBAL");
  const [days, setDays] = useState<number>(0);
  const [hasServer, setHasServer] = useState(false);  // 직접 수집할 수 있는 서버가 있는가
  // 요구사항 33-12: 첫 화면에 카드를 너무 많이 쌓지 않는다. 필요하면 눌러서 펼친다.
  const [showAllUpdates, setShowAllUpdates] = useState(false);
  const [showAllRegulatory, setShowAllRegulatory] = useState(false);

  const load = useCallback(async (d: number) => {
    try {
      setData(await getDashboard(d));
      setError(null);
    } catch {
      setError("정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.");
    }
  }, []);

  // 마지막으로 고른 기간을 기억한다
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(PERIOD_KEY);
      if (saved !== null) setDays(Number(saved));
    } catch {
      /* 시크릿 모드 등에서 막혀도 기본값으로 동작한다 */
    }
  }, []);

  useEffect(() => { void load(days); }, [load, days]);

  // 서버가 있으면 '지금 확인하기' 버튼을 보여준다.
  // GitHub Pages 처럼 서버가 없는 곳에서는 조용히 넘어간다.
  useEffect(() => {
    fetch("api/health")
      .then((r) => { if (r.ok) { markServerAvailable(); setHasServer(true); } })
      .catch(() => { /* 서버 없음 — 읽기 전용으로 동작한다 */ });
  }, []);

  function pickPeriod(d: number) {
    setDays(d);
    setShowAllUpdates(false);
    setShowAllRegulatory(false);
    try { window.localStorage.setItem(PERIOD_KEY, String(d)); } catch { /* 무시 */ }
  }

  async function refresh() {
    setBusy(true);
    setNotice(null);
    try {
      const r = await runCollect(false);
      if (r.skipped) {
        setNotice("공식 등록 사이트에 아직 새로운 내용이 없습니다.");
      } else if (r.changes_detected > 0) {
        setNotice(`새로운 변화 ${r.changes_detected}건을 찾았습니다.`);
      } else {
        setNotice("확인했습니다. 바뀐 내용이 없습니다.");
      }
      await load(days);
    } catch {
      setNotice("확인에 실패했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  if (error) {
    return (
      <>
        <Header />
        <div className="notice warn">{error}</div>
        <button className="btn" onClick={() => void load(days)}>다시 불러오기</button>
      </>
    );
  }

  if (!data) {
    return (
      <>
        <Header />
        <div className="empty">정보를 불러오는 중입니다…</div>
      </>
    );
  }

  const trials = tab === "KR" ? data.trials_domestic : data.trials_global;

  return (
    <>
      <header className="app-header">
        <h1 className="app-title">오늘의 바이오 임상 정보</h1>
        <div className="app-date">{data.today_ko}</div>
        {data.last_collection && (
          <div className="app-freshness">
            <span aria-hidden="true">🕒</span>
            <span>마지막 확인 {data.last_collection.relative_ko || data.last_collection.at_ko}</span>
            {!hasServer && <span>· 1시간마다 자동</span>}
          </div>
        )}
      </header>

      {/* 기간 선택 (요구사항 33-13: 텍스트가 들어간 큰 버튼) */}
      <nav className="period" aria-label="기간 선택">
        {PERIODS.map((p) => (
          <button
            key={p.days}
            className="period-btn"
            aria-pressed={days === p.days}
            onClick={() => pickPeriod(p.days)}
          >
            {p.label}
          </button>
        ))}
      </nav>

      {/* 1) 오늘 새로운 정보가 있는가 */}
      <section className="section">
        <h2 className="section-title">
          <span aria-hidden="true">🔔</span>
          {data.period_ko} 업데이트 {data.total_updates}건
        </h2>
        <p className="section-note">중요한 것부터 위에 있습니다.</p>
        <div className="summary">
          {data.summary.map((row) => (
            <div
              key={row.severity}
              className={`summary-row sev-${row.severity} ${row.count === 0 ? "is-zero" : ""}`}
            >
              <span className="icon" aria-hidden="true">{row.icon}</span>
              <span className="label">{row.severity_ko}</span>
              <span className="count">{row.count}</span>
              <span className="unit">건</span>
            </div>
          ))}
        </div>
        {/* 서버가 없는 곳(GitHub Pages)에서는 직접 수집할 수 없다.
            대신 자동으로 언제 확인했는지를 보여준다. */}
        {!hasServer ? (
          <button className="btn" onClick={() => void load(days)}>
            🔄 새로고침
          </button>
        ) : (
          <button className="btn btn-primary" onClick={() => void refresh()} disabled={busy}>
            {busy ? "확인하는 중…" : "🔄 지금 새 정보 확인하기"}
          </button>
        )}
        {notice && <div className="notice">{notice}</div>}
      </section>

      {/* 2) 관심 약물에 변화가 있는가 - 항상 맨 위 (요구사항 33-11) */}
      <section className="section">
        <h2 className="section-title"><span aria-hidden="true">⭐</span>관심 정보</h2>
        <p className="section-note">등록해 두신 약물과 임상시험입니다.</p>
        {data.watchlist.length === 0
          ? <div className="empty">등록된 관심 정보가 없습니다.</div>
          : data.watchlist.map((t) => <TrialCard key={t.id} trial={t} />)}
      </section>

      {/* 새로운 변화 목록 */}
      <section className="section">
        <h2 className="section-title"><span aria-hidden="true">🧪</span>새로 바뀐 내용</h2>
        <p className="section-note">
          공식 임상시험 등록정보와 전자공시에서 달라진 부분입니다.
        </p>
        {data.changes.length === 0
          ? (
            <div className="empty">
              <p className="empty-title">✅ {data.period_ko}은 새로운 변화가 없습니다</p>
              <p className="empty-sub">
                임상시험과 공시를 계속 확인하고 있습니다.
                {data.latest_outside_window && (
                  <> 가장 최근 소식은 {data.latest_outside_window.detected_at_ko} 입니다.</>
                )}
              </p>
              {days !== 30 && (
                <button className="btn" onClick={() => pickPeriod(30)}>
                  최근 30일 보기
                </button>
              )}
            </div>
          )
          : (showAllUpdates ? data.changes : data.changes.slice(0, 5))
              .map((c) => <ChangeCard key={c.id} change={c} />)}
        {!showAllUpdates && data.changes.length > 5 && (
          <button className="btn" onClick={() => setShowAllUpdates(true)}>
            나머지 {data.changes.length - 5}건 더 보기
          </button>
        )}
      </section>

      {/* 5) 규제기관에서 새로운 발표가 있는가 (요구사항 16, 33-9) */}
      <section className="section">
        <h2 className="section-title"><span aria-hidden="true">🏛</span>규제기관 · 기업 공시</h2>
        <p className="section-note">
          식약처·FDA 승인과 회사의 법적 공시입니다. 뉴스보다 먼저 나옵니다.
        </p>
        {data.regulatory.length === 0
          ? (
            <div className="empty">
              <p className="empty-title">{data.period_ko}은 새로운 공시가 없습니다</p>
              <p className="empty-sub">식약처·FDA 승인이나 회사 공시가 올라오면 여기 표시됩니다.</p>
            </div>
          )
          : (showAllRegulatory ? data.regulatory : data.regulatory.slice(0, 3))
              .map((r) => <ChangeCard key={r.id} change={r} />)}
        {!showAllRegulatory && data.regulatory.length > 3 && (
          <button className="btn" onClick={() => setShowAllRegulatory(true)}>
            나머지 {data.regulatory.length - 3}건 더 보기
          </button>
        )}
      </section>

      {/* 4) 국내/해외 분리 (요구사항 7, 33-9) */}
      <section className="section">
        <h2 className="section-title"><span aria-hidden="true">🗂</span>임상시험 전체</h2>
        <div className="tabs">
          <button className="tab" aria-pressed={tab === "KR"} onClick={() => setTab("KR")}>
            🇰🇷 국내 ({data.trials_domestic.length})
          </button>
          <button className="tab" aria-pressed={tab === "GLOBAL"} onClick={() => setTab("GLOBAL")}>
            🌎 해외 ({data.trials_global.length})
          </button>
        </div>
        {trials.length === 0
          ? <div className="empty">해당하는 임상시험이 없습니다.</div>
          : trials.map((t) => <TrialCard key={t.id} trial={t} />)}
      </section>
    </>
  );
}

function Header() {
  return (
    <header className="app-header">
      <h1 className="app-title">오늘의 바이오 임상 정보</h1>
    </header>
  );
}
