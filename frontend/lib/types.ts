export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

/**
 * 통합 업데이트 카드.
 * 임상시험 등록정보의 변화(TRIAL_CHANGE)와 전자공시(DISCLOSURE)가 같은 모양으로 온다.
 * 한국어 표시 문자열은 전부 서버에서 완성해서 내려주므로 화면은 렌더링만 한다.
 */
export interface UpdateItem {
  id: string;
  kind: "TRIAL_CHANGE" | "DISCLOSURE" | "NEWS";
  headline_ko: string;
  detail_ko: string | null;
  old_value_ko: string | null;
  new_value_ko: string | null;
  severity: Severity;
  severity_ko: string;
  severity_icon: string;
  detected_at: string | null;
  detected_at_ko: string;
  detected_relative_ko: string;
  is_read: boolean;
  source_kind_ko: string;
  source_name_ko: string;
  region_ko: string;
  event_type_ko?: string;
  meta_lines: string[];
  internal_href: string | null;
  external_url: string | null;
}

export interface TrialLocation {
  facility: string | null;
  city: string | null;
  country_ko: string;
  status_ko: string;
  status_icon: string;
}

export interface Snapshot {
  id: number;
  captured_at_ko: string;
  captured_relative_ko: string;
  status: string | null;
  status_ko: string;
  status_icon: string;
  status_help_ko: string;
  phase_ko: string;
  phase_help_ko: string;
  enrollment_ko: string;
  enrollment_count: number | null;
  start_date_ko: string;
  primary_completion_date_ko: string;
  completion_date_ko: string;
  has_results: boolean | null;
  has_results_ko: string;
  source_last_update_ko: string;
  location_count: number | null;
  locations: TrialLocation[];
}

export interface Trial {
  id: number;
  registry: string;
  registry_id: string;
  org_study_id: string | null;
  url: string | null;
  title_en: string | null;
  title_ko: string | null;
  drug_ko: string | null;
  drug_code: string | null;
  disease_ko: string | null;
  company_ko: string | null;
  country_ko: string;
  region: string;
  region_ko: string;
  is_watchlisted: boolean;
  current: Snapshot | null;
  latest_change: UpdateItem | null;
  history?: Snapshot[];
  changes?: UpdateItem[];
  snapshot_count?: number;
}

export interface SummaryRow {
  severity: Severity;
  severity_ko: string;
  icon: string;
  count: number;
}

export interface Dashboard {
  generated_at: string;
  today_ko: string;
  window_days: number;
  period_ko: string;
  total_updates: number;
  summary: SummaryRow[];
  changes: UpdateItem[];
  watchlist: Trial[];
  regulatory: UpdateItem[];
  news_domestic: UpdateItem[];
  news_global: UpdateItem[];
  latest_outside_window: UpdateItem | null;
  trials_domestic: Trial[];
  trials_global: Trial[];
  last_collection: {
    at_ko: string;
    relative_ko: string;
    ok: boolean | null;
    skipped: boolean | null;
    skip_reason: string | null;
  } | null;
}
