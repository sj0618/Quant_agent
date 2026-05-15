import { useState } from "react";
import type { RiskWarning } from "../../types/quantagent";

const severityLabel: Record<RiskWarning["severity"], string> = {
  LOW: "낮음",
  MEDIUM: "주의",
  HIGH: "높음",
};

export function RiskWarningBadge({ warning }: { warning?: RiskWarning }) {
  if (!warning) {
    return <span className="risk-badge risk-badge--none">Risk clear</span>;
  }

  return <span className={`risk-badge risk-badge--${warning.severity.toLowerCase()}`}>Risk {severityLabel[warning.severity]}</span>;
}

export function RiskWarningToggle({ warning }: { warning?: RiskWarning }) {
  const [open, setOpen] = useState(false);

  if (!warning) {
    return <p className="risk-empty">Risk Manager warning 없음. Signal action은 그대로 유지됩니다.</p>;
  }

  return (
    <div className="risk-toggle">
      <button className="link-button" type="button" onClick={() => setOpen((value) => !value)}>
        {open ? "리스크 경고 접기" : "리스크 경고 보기"}
      </button>
      {open ? (
        <div className="risk-detail">
          <div className="risk-detail__header">
            <strong>{warning.reason}</strong>
            <span>{warning.source}</span>
          </div>
          <ul>
            {warning.evidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>{warning.report_note}</p>
        </div>
      ) : null}
    </div>
  );
}
