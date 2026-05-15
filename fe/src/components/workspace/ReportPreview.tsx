import type { ReportSection } from "../../types/quantagent";

export function ReportPreview({ sections, compact = false }: { sections: ReportSection[]; compact?: boolean }) {
  const visibleSections = compact ? sections.slice(0, 4) : sections;

  return (
    <section className="panel-card report-preview">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Report Preview</span>
          <h2>7섹션 리포트 미리보기</h2>
        </div>
        <span className="pill pill--slate">Mock</span>
      </div>

      <div className="report-section-list">
        {visibleSections.map((section) => (
          <article className="report-section" key={section.id}>
            <h3>{section.title}</h3>
            <p>{section.summary}</p>
            {section.signalJudgeNote ? (
              <div className="report-note report-note--signal">
                <strong>Signal Judge</strong>
                <span>{section.signalJudgeNote}</span>
              </div>
            ) : null}
            {section.riskManagerNote ? (
              <div className="report-note report-note--risk">
                <strong>Risk Manager Warning</strong>
                <span>{section.riskManagerNote}</span>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
