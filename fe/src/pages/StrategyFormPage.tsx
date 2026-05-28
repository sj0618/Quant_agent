import { useState, type FormEvent } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { AppLayout } from "../components/layout/AppLayout";
import { getAppOverview } from "../api/quantAgentClient";
import { getStrategyDraft, persistStrategy, requestStrategyAnalysis, type StrategyDraft } from "../api/strategyClient";
import { ROUTES } from "../config/routes";
import { useAsyncData } from "../hooks/useAsyncData";

interface StrategyFormPageProps {
  mode: "new" | "edit";
  strategyId?: string;
}

function buildDraft(base: StrategyDraft | null, fallback: StrategyDraft): StrategyDraft {
  return base ?? fallback;
}

export function StrategyFormPage({ mode, strategyId }: StrategyFormPageProps) {
  const { data, loading, error } = useAsyncData(getAppOverview, []);
  const [status, setStatus] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [draft, setDraft] = useState<StrategyDraft | null>(() => (mode === "edit" ? getStrategyDraft() : null));

  if (loading) {
    return <AsyncState title="전략 정보를 불러오는 중입니다" tone="loading" />;
  }

  if (error || !data) {
    return <AsyncState title="전략 정보를 불러오지 못했습니다" description={error?.message} tone="error" />;
  }

  const queryDraft = new URLSearchParams(window.location.search).get("draft");
  const fallbackDraft: StrategyDraft = {
    id: strategyId ?? "active",
    name: mode === "new" ? "새 전략" : "반도체 모멘텀 + 기관 매수 회귀",
    updatedAt: new Date().toISOString(),
    ...data.strategy,
    natural_language_strategy: queryDraft ?? data.strategy.natural_language_strategy,
  };
  const currentDraft = buildDraft(draft, fallbackDraft);
  const strategyStatus = window.localStorage.getItem("quantagent.strategy-status.v1");

  const updateDraft = (field: keyof StrategyDraft, value: string) => {
    setDraft((current) => ({ ...buildDraft(current, currentDraft), [field]: value, updatedAt: new Date().toISOString() }));
  };

  const handleSave = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatus(null);
    setFormError(null);
    const nextDraft = { ...currentDraft, updatedAt: new Date().toISOString() };
    setDraft(nextDraft);

    try {
      await persistStrategy(mode === "edit" ? currentDraft.id : null, nextDraft);
      window.localStorage.setItem("quantagent.strategy-status.v1", "active");
      setStatus("전략을 저장했습니다.");
    } catch (saveError) {
      setFormError(saveError instanceof Error ? saveError.message : "전략 저장에 실패했습니다.");
    }
  };

  const handleRunAnalysis = async () => {
    setRunning(true);
    setStatus(null);
    setFormError(null);
    try {
      const job = await requestStrategyAnalysis(currentDraft.id, currentDraft.natural_language_strategy);
      setStatus(job ? `AI 분석이 완료되었습니다. Trace ${job.trace_id}` : "분석 실행을 요청했습니다.");
    } catch (runError) {
      setFormError(runError instanceof Error ? runError.message : "분석 실행 요청에 실패했습니다.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <AppLayout active="workspace">
      <main className="strategy-page">
        <div className="settings-page__head">
          <div>
            <Badge variant="dark">{mode === "new" ? "NEW STRATEGY" : "EDIT STRATEGY"}</Badge>
            <h1>{mode === "new" ? "새 전략 만들기" : "전략 수정"}</h1>
            <p>자연어 전략을 구조화하고 분석 실행 요청까지 연결합니다.</p>
          </div>
          <a className="button button--secondary" href={ROUTES.app}>워크스페이스로</a>
        </div>

        {status ? <div className="status-banner status-banner--success"><strong>{status}</strong></div> : null}
        {formError ? <div className="status-banner status-banner--error"><strong>{formError}</strong></div> : null}
        {strategyStatus === "inactive" ? (
          <div className="status-banner">
            <strong>전략이 비활성화된 상태입니다.</strong>
            <span>저장 후 분석 실행을 요청하면 다시 활성 전략으로 전환할 수 있습니다.</span>
          </div>
        ) : null}

        <Card>
          <form className="strategy-form" onSubmit={handleSave}>
            <div className="form-grid">
              <label className="field">
                <span>전략명</span>
                <input onChange={(event) => updateDraft("name", event.target.value)} value={currentDraft.name} />
              </label>
              <label className="field">
                <span>유니버스</span>
                <input onChange={(event) => updateDraft("universe", event.target.value)} value={currentDraft.universe} />
              </label>
              <label className="field field--wide">
                <span>자연어 전략</span>
                <textarea
                  onChange={(event) => updateDraft("natural_language_strategy", event.target.value)}
                  rows={4}
                  value={currentDraft.natural_language_strategy}
                />
              </label>
              <label className="field">
                <span>섹터</span>
                <input onChange={(event) => updateDraft("sector", event.target.value)} value={currentDraft.sector} />
              </label>
              <label className="field">
                <span>리밸런싱</span>
                <input onChange={(event) => updateDraft("rebalance", event.target.value)} value={currentDraft.rebalance} />
              </label>
              <label className="field">
                <span>매수 조건</span>
                <input onChange={(event) => updateDraft("buy_condition", event.target.value)} value={currentDraft.buy_condition} />
              </label>
              <label className="field">
                <span>보유 조건</span>
                <input onChange={(event) => updateDraft("hold_condition", event.target.value)} value={currentDraft.hold_condition} />
              </label>
              <label className="field field--wide">
                <span>매도 조건</span>
                <input onChange={(event) => updateDraft("drop_condition", event.target.value)} value={currentDraft.drop_condition} />
              </label>
            </div>
            <div className="form-actions">
              <Button type="submit" variant="dark">전략 저장</Button>
              <Button disabled={running} onClick={handleRunAnalysis} variant="secondary">
                {running ? "분석 요청 중" : "분석 실행"}
              </Button>
            </div>
          </form>
        </Card>
      </main>
    </AppLayout>
  );
}
