import Link from "next/link";
import type { UpdateItem } from "@/lib/types";
import { SeverityBadge } from "./Severity";

/**
 * 업데이트 1건 카드 (임상시험 변화 / 전자공시 공통).
 *
 * 뉴스 제목이 아니라 '무슨 일이 일어났는가'를 가장 크게 보여준다 (요구사항 33-8).
 * 출처의 성격(공식 임상정보 / 기업 공시)을 항상 함께 표시한다 (요구사항 33-10).
 */
export function ChangeCard({ change }: { change: UpdateItem }) {
  const body = (
    <>
      <div className="card-top">
        <SeverityBadge
          severity={change.severity}
          label={change.severity_ko}
          icon={change.severity_icon}
        />
        <span className="card-time">{change.detected_relative_ko}</span>
      </div>

      <p className="card-headline">{change.headline_ko}</p>

      {/* 기존 -> 현재 (임상시험 변화에만 있다) */}
      {change.old_value_ko && change.new_value_ko && (
        <div className="change-compare">
          <div className="from">
            <div className="k">기존</div>
            <div className="v">{change.old_value_ko}</div>
          </div>
          <div className="to">
            <div className="k">현재</div>
            <div className="v">{change.new_value_ko}</div>
          </div>
        </div>
      )}

      {/* 공시 상세는 '레이블: 값' 목록으로 온다 */}
      {change.kind === "DISCLOSURE" && change.detail_ko && (
        <dl className="detail-list">
          {change.detail_ko.split("\n").filter(Boolean).map((line, i) => {
            const at = line.indexOf(":");
            if (at === -1) return <p className="detail-lead" key={i}>{line}</p>;
            return (
              <div className="detail-row" key={i}>
                <dt>{line.slice(0, at).trim()}</dt>
                <dd>{line.slice(at + 1).trim()}</dd>
              </div>
            );
          })}
        </dl>
      )}

      <div className="card-meta">
        <span className="src">
          {change.source_kind_ko}
          {change.event_type_ko ? ` · ${change.event_type_ko}` : ""}
        </span>
        <span>{change.source_name_ko}</span>
        {change.meta_lines.map((line, i) => <span key={i}>{line}</span>)}
        {change.external_url && (
          <span className="src-link">원문 보기 ↗</span>
        )}
      </div>
    </>
  );

  const className = `card card-tap sev-${change.severity}`;

  if (change.internal_href) {
    return <Link href={change.internal_href} className={className}>{body}</Link>;
  }
  if (change.external_url) {
    return (
      <a href={change.external_url} target="_blank" rel="noreferrer" className={className}>
        {body}
      </a>
    );
  }
  return <div className={className}>{body}</div>;
}
