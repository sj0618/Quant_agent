import type { ResearchCandidateExecutionSpecV3, RuleDraftOutcome } from "../../api/quantAgentClient";
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
  const researchedSpec = researchSpec(draft);
  return (
    <section className="workspace-content" aria-labelledby="strategy-draft-title">
      <Card>
        <h2 id="strategy-draft-title">
          {researchedSpec
            ? "AI 리서치로 정규화한 전략을 확인해 주세요"
            : draft.exploration
              ? "탐색 연구 가정과 후보를 확인해 주세요"
              : "해석한 전략 조건을 확인해 주세요"}
        </h2>
        <p>{draft.explanation}</p>
      </Card>

      {researchedSpec ? (
        <ResearchedStrategyDraft spec={researchedSpec} />
      ) : draft.exploration ? (
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
            {confirming
              ? "백테스트를 준비하는 중"
              : researchedSpec
                ? "이 AI 연구 규칙으로 백테스트 시작"
                : draft.exploration
                  ? "이 후보군으로 탐색 시작"
                  : "이 조건으로 백테스트 시작"}
          </Button>
        ) : (
          <>
            <strong>AI 리서치 정규화가 완료되지 않았습니다.</strong>
            <p>입력 형식을 고치라는 뜻이 아닙니다. 같은 요청을 다시 시도하거나, 전략 의도를 한 문장 더 덧붙여 다시 분석할 수 있습니다.</p>
            {draft.unsupported_conditions.length ? (
              <ul>
                {draft.unsupported_conditions.map((item) => (
                  <li key={`${item.condition}-${item.reason}`}>{item.reason}</li>
                ))}
              </ul>
            ) : null}
          </>
        )}
      </Card>
    </section>
  );
}

function researchSpec(draft: RuleDraftOutcome): ResearchCandidateExecutionSpecV3 | null {
  const spec = draft.strategy_execution_spec;
  return spec && "classification" in spec && spec.classification === "research_required" ? spec : null;
}

function ResearchedStrategyDraft({ spec }: { spec: ResearchCandidateExecutionSpecV3 }) {
  const candidate = spec.candidates[0];
  const sources = new Map(spec.sources.map((source) => [source.source_id, source]));
  return (
    <>
      <Card>
        <h3>{candidate.title}</h3>
        <p>{spec.resolution_summary}</p>
        <h3>검증 가설</h3>
        <p>{candidate.hypothesis}</p>
        <h3>반대 가설</h3>
        <p>{candidate.counter_hypothesis}</p>
      </Card>
      <Card>
        <h3>진입 조건</h3>
        <p>{candidate.entry_conditions.map(formatResearchCondition).join(" · ")}</p>
        <h3>종료 조건</h3>
        <p>{candidate.exit_conditions.map(formatResearchCondition).join(" · ")}</p>
        <h3>필요 지표와 가정</h3>
        <p>{candidate.required_metrics.join(", ")}</p>
        <ul>{candidate.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
      </Card>
      <Card>
        <h3>전략 의미를 확인한 근거</h3>
        <ul>
          {candidate.source_ids.map((sourceId) => {
            const source = sources.get(sourceId);
            return source ? <li key={sourceId}><a href={source.url} rel="noreferrer" target="_blank">{source.title}</a> · {source.claim}</li> : null;
          })}
        </ul>
        <p>연구 스냅샷 {spec.research_snapshot_hash.slice(0, 12)} · 실행 가능 지표 {spec.capability_hash.slice(0, 12)}</p>
      </Card>
    </>
  );
}

function formatCondition(
  condition: RuleDraftOutcome["entry_conditions"][number] | RuleDraftOutcome["exit_conditions"][number],
) {
  return `${condition.metric} ${condition.comparator} ${condition.value} · ${condition.lookback}일`;
}

function formatResearchCondition(condition: ResearchCandidateExecutionSpecV3["candidates"][number]["entry_conditions"][number]) {
  const right = Array.isArray(condition.right) ? condition.right.join(" ~ ") : condition.right;
  const window = condition.window ? ` · 최근 ${condition.window}일` : "";
  const aggregate = condition.aggregate ? ` ${condition.aggregate}` : "";
  const scale = condition.scale ? ` × ${condition.scale}` : "";
  return `${condition.left}${aggregate} ${condition.operator} ${right}${scale}${window}`;
}
