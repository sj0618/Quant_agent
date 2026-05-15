import type { ScenarioPayload, StrategyOption } from "../../types/quantagent";

function StrategyOptionCard({
  option,
  onSelectStrategy,
}: {
  option: StrategyOption;
  onSelectStrategy: (strategyId: string) => void;
}) {
  return (
    <article className="scenario-option-card">
      <div>
        <h4>{option.title}</h4>
        <p>{option.description}</p>
      </div>
      <div className="condition-chip-list">
        {option.keyConditions.map((condition) => (
          <span key={condition}>{condition}</span>
        ))}
      </div>
      <button className="secondary-button" type="button" onClick={() => onSelectStrategy(option.strategy_id)}>
        이 전략 선택
      </button>
    </article>
  );
}

export function ScenarioCards({
  scenario,
  onSelectStrategy,
  onUseExample,
}: {
  scenario?: ScenarioPayload;
  onSelectStrategy: (strategyId: string) => void;
  onUseExample: (example: string) => void;
}) {
  if (!scenario || scenario.scenario === "READY") {
    return null;
  }

  if (scenario.scenario === "C1_INPUT_AMBIGUOUS") {
    return (
      <section className="scenario-card scenario-card--info">
        <span className="eyebrow">C1 · INPUT_AMBIGUOUS</span>
        <h3>이런 전략을 원하시나요?</h3>
        <p>사용자 입력 자체가 모호하여 선검색 → Query smooth 후보를 먼저 제안합니다.</p>
        <div className="scenario-option-grid">
          {scenario.options.map((option) => (
            <StrategyOptionCard key={option.strategy_id} option={option} onSelectStrategy={onSelectStrategy} />
          ))}
        </div>
      </section>
    );
  }

  if (scenario.scenario === "C2_TERM_UNKNOWN") {
    return (
      <section className="scenario-card scenario-card--definition">
        <span className="eyebrow">C2 · TERM_UNKNOWN</span>
        <h3>다음 의미로 해석했어요</h3>
        <div className="term-definition-box">
          <strong>{scenario.termDefinition.term}</strong>
          <p>{scenario.termDefinition.definition}</p>
          <div className="condition-chip-list">
            {scenario.termDefinition.matchedSources.map((source) => (
              <span key={source}>{source}</span>
            ))}
            <span>confidence {Math.round(scenario.termDefinition.confidence * 100)}%</span>
          </div>
        </div>
        {scenario.termDefinition.requiresConfirmation ? (
          <button
            className="primary-button"
            type="button"
            onClick={() => onSelectStrategy(scenario.termDefinition.mappedStrategyId)}
          >
            이 정의로 계속하기
          </button>
        ) : null}
      </section>
    );
  }

  if (scenario.scenario === "C4_CONFLICTING") {
    return (
      <section className="scenario-card scenario-card--warning">
        <span className="eyebrow">C4 · CONFLICTING</span>
        <h3>{scenario.conflict.title}</h3>
        <div className="conflict-list">
          {scenario.conflict.conflictPoints.map((point) => (
            <p key={point}>
              <span>충돌 지점</span>
              {point}
            </p>
          ))}
        </div>
        <h4>대안 전략 후보</h4>
        <div className="scenario-option-grid">
          {scenario.conflict.alternatives.map((option) => (
            <StrategyOptionCard key={option.strategy_id} option={option} onSelectStrategy={onSelectStrategy} />
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="scenario-card scenario-card--rejected">
      <span className="eyebrow">C5 · INFEASIBLE</span>
      <h3>{scenario.infeasible.title}</h3>
      <p>{scenario.infeasible.reason}</p>
      <div className="support-scope">{scenario.infeasible.supportedScope}</div>
      <div className="example-fill-list">
        {scenario.infeasible.examples.map((example) => (
          <button className="ghost-button" type="button" key={example} onClick={() => onUseExample(example)}>
            {example}
          </button>
        ))}
      </div>
    </section>
  );
}
