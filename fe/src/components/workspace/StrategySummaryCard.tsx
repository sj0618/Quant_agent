import type { StrategySpec } from "../../types/quantagent";

export function StrategySummaryCard({ strategy }: { strategy: StrategySpec }) {
  return (
    <section className="panel-card strategy-summary-card">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Active Strategy</span>
          <h2>{strategy.name}</h2>
        </div>
        <span className="pill pill--blue">{strategy.universe}</span>
      </div>
      <p className="muted">{strategy.summary}</p>

      <div className="strategy-logic-grid">
        <div>
          <span>Entry logic</span>
          <strong>{strategy.entry_logic}</strong>
        </div>
        <div>
          <span>Exit logic</span>
          <strong>{strategy.exit_logic}</strong>
        </div>
        <div>
          <span>Snapshot</span>
          <strong>{strategy.candidate_snapshot.snapshot_id}</strong>
        </div>
        <div>
          <span>Effective</span>
          <strong>{strategy.candidate_snapshot.effective_from}</strong>
        </div>
      </div>

      <div className="rule-columns">
        <div>
          <h3>Entry rules</h3>
          <ul>
            {strategy.entry_rules.map((rule) => (
              <li key={rule.id}>{rule.label}</li>
            ))}
          </ul>
        </div>
        <div>
          <h3>Exit rules</h3>
          <ul>
            {strategy.exit_rules.map((rule) => (
              <li key={rule.id}>{rule.label}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
