import type { Dashboard, Trial } from "./types";

/**
 * 데이터를 읽는 경로는 **한 가지뿐**이다.
 *
 *     data/dashboard-0.json
 *     data/trials/NCT07576868.json
 *
 * 배포 방식이 세 가지(집 PC·휴대폰·GitHub Pages)인데 경로를 나눠두면
 * 한 군데만 틀려도 조용히 깨진다. 그래서 주소를 통일하고,
 * 서버가 있는 쪽(FastAPI)이 같은 주소로 내려주도록 맞췄다.
 *
 *   GitHub Pages  ->  실제 파일
 *   FastAPI       ->  /data/... 경로로 같은 내용을 내려줌
 */

/** 사이트 최상위. GitHub Pages 는 /저장소이름/ 아래에 놓인다. */
function siteRoot(): string {
  if (typeof window === "undefined") return "";
  return window.location.pathname.replace(/\/trial\/?$/, "").replace(/\/$/, "");
}

async function getJson<T>(file: string): Promise<T> {
  // 내용이 주기적으로 바뀌므로 캐시를 피한다
  const stamp = Math.floor(Date.now() / 60000);
  const res = await fetch(`${siteRoot()}/data/${file}?t=${stamp}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`정보를 불러오지 못했습니다 (${res.status})`);
  return (await res.json()) as T;
}

/** days=0 은 '오늘'(한국시간 자정부터) */
export function getDashboard(days = 0): Promise<Dashboard> {
  return getJson<Dashboard>(`dashboard-${days}.json`);
}

/** 서버가 내려줄 때만 live=true 가 들어 있다. */
export function getMeta(): Promise<{ generated_at: string; live?: boolean }> {
  return getJson(`meta.json`);
}

export function getTrial(registryId: string): Promise<Trial> {
  return getJson<Trial>(`trials/${encodeURIComponent(registryId)}.json`);
}

/** 서버가 있을 때만 쓸 수 있다. GitHub Pages 에서는 호출해도 실패한다. */
export async function runCollect(force = false): Promise<{
  ok: boolean; skipped: boolean; changes_detected: number; skip_reason: string | null;
}> {
  const res = await fetch(`${siteRoot()}/api/collect?force=${force}`, { method: "POST" });
  if (!res.ok) throw new Error("수집 요청 실패");
  return res.json();
}

/** 이 화면이 서버 없이(읽기 전용으로) 돌고 있는가 */
let readOnly = true;
export const isStaticMode = () => readOnly;
export function markServerAvailable() { readOnly = false; }
