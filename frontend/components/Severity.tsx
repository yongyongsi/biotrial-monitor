import type { Severity } from "@/lib/types";

/** 중요도 배지. 색상 + 아이콘 + 텍스트를 항상 함께 쓴다 (요구사항 33-5). */
export function SeverityBadge({ severity, label, icon }:
  { severity: Severity; label: string; icon: string }) {
  return (
    <span className={`badge badge-${severity}`}>
      <span aria-hidden="true">{icon}</span>
      <span>{label}</span>
    </span>
  );
}
