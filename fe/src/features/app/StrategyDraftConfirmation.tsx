import type { RuleDraftOutcome } from "../../api/quantAgentClient";
import { Button } from "../../components/common/Button";
import { Card } from "../../components/common/Card";

export function StrategyDraftConfirmation({
  draft,
  confirming,
  onConfirm,
}: {
  draft: RuleDraftOutcome;
  confirming: boolean;
  onConfirm: () => void;
}) {
  return (
    <section className="workspace-content" aria-labelledby="strategy-draft-title">
      <Card>
        <h2 id="strategy-draft-title">
          {draft.exploration ? "탐색 연구 가정과 후보를 확인해 주세요" : "해석한 전략 조건을 확인해 주세요"}
        </h2>
        <p>{draft.explanation}</p>
      </Card>

      {draft.exploration ? (
        <>
          <Card>
            <h3>연구 가설</h3>
            <p>{draft.exploration.research_hypothesis}</p>
            <h3>반대 가설</h3>
            <p>{draft.exploration.opposing_hypothesis}</p>
            <p>시장·기간: {draft.exploration.market} · {draft.exploration.period}</p>
          </Card>
          <Card>
            <h3>적용한 기본값</h3>
            <ul>{draft.exploration.defaults.map((item) => <li key={item}>{item}</li>)}</ul>
            <h3>대안</h3>
            <ul>{draft.exploration.alternatives.map((item) => <li key={item}>{item}</li>)}</ul>
          </Card>
          <Card>
            <h3>성과 확인 전에 고정할 후보</h3>
            <ul>
              {draft.exploration.candidate_reasons.map((candidate) => (
                <li key={candidate.catalog_id}><strong>{candidate.title}</strong> · {candidate.reason}</li>
              ))}
            </ul>
            <p>
              정책 {draft.exploration.policy_version} ({draft.exploration.policy_hash.slice(0, 12)}) · 후보 카탈로그 {draft.exploration.catalog_version} ({draft.exploration.catalog_hash.slice(0, 12)})
            </p>
            <ul>{draft.exploration.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
          </Card>
        </>
      ) : (
        <Card>
          <h3>진입 조건</h3>
          <p>{draft.entry_conditions.map(formatCondition).join(" · ") || "없음"}</p>
          <h3>종료 조건</h3>
          <p>{draft.exit_conditions.map(formatCondition).join(" · ") || "없음"}</p>
        </Card>
      )}

      {draft.indicator_selections.length ? (
        <Card>
          <h3>선택한 지표</h3>
          <ul>{draft.indicator_selections.map((item) => <li key={item.metric}><strong>{item.metric}</strong> · {item.reason}</li>)}</ul>
        </Card>
      ) : null}

      <Card>
        {draft.is_executable ? (
          <Button disabled={confirming} onClick={onConfirm} variant="primary">
            {confirming ? "백테스트를 준비하는 중" : draft.exploration ? "이 후보군으로 탐색 시작" : "이 조건으로 백테스트 시작"}
          </Button>
        ) : <p>조건을 보완한 뒤 다시 확인해 주세요.</p>}
      </Card>
    </section>
  );
}

function formatCondition(
  condition: RuleDraftOutcome["entry_conditions"][number] | RuleDraftOutcome["exit_conditions"][number],
) {
  return `${condition.metric} ${condition.comparator} ${condition.value} · ${condition.lookback}일`;
}
