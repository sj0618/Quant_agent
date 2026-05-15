import { useEffect, useMemo, useState } from "react";
import type { ChatMessage, ScenarioCode, ScenarioPayload, WorkspacePayload } from "../../types/quantagent";
import {
  createChatMessage,
  getExampleStrategies,
  getInitialMessages,
  getWorkspacePayload,
  parseStrategy,
  selectStrategy,
} from "../../services/mockQuantAgentApi";
import { AnalysisTabs } from "./AnalysisTabs";
import { ChatPanel } from "./ChatPanel";

export function AppWorkspace() {
  const [payload, setPayload] = useState<WorkspacePayload>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [examples, setExamples] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [selectedScenario, setSelectedScenario] = useState<ScenarioCode | "AUTO">("AUTO");
  const [scenarioPayload, setScenarioPayload] = useState<ScenarioPayload>();
  const [isBootstrapping, setIsBootstrapping] = useState(true);

  useEffect(() => {
    let mounted = true;

    const bootstrap = async () => {
      const [initialMessages, initialExamples, initialPayload] = await Promise.all([
        getInitialMessages(),
        getExampleStrategies(),
        getWorkspacePayload(),
      ]);

      if (!mounted) {
        return;
      }

      setMessages(initialMessages);
      setExamples(initialExamples);
      setPayload(initialPayload);
      setIsBootstrapping(false);
    };

    void bootstrap();

    return () => {
      mounted = false;
    };
  }, []);

  const activeScenarioLabel = useMemo(() => {
    if (!scenarioPayload) {
      return "READY";
    }

    return scenarioPayload.scenario;
  }, [scenarioPayload]);

  const handleSubmit = async () => {
    const trimmed = input.trim();

    if (!trimmed) {
      return;
    }

    const result = await parseStrategy(trimmed, selectedScenario);
    setMessages((current) => [
      ...current,
      createChatMessage("user", trimmed),
      createChatMessage("assistant", result.assistantMessage, result.scenario),
    ]);
    setScenarioPayload(result);
    setInput("");

    if (result.scenario === "READY") {
      setPayload(await selectStrategy(result.strategy_id));
    }
  };

  const handleSelectStrategy = async (strategyId: string) => {
    const nextPayload = await selectStrategy(strategyId);
    setPayload(nextPayload);
    setMessages((current) => [
      ...current,
      createChatMessage(
        "system",
        `"${nextPayload.activeStrategy.name}" 전략을 현재 Workspace에 반영했습니다. Signal action은 Signal Judge 결과 그대로 유지됩니다.`,
        "READY",
      ),
    ]);
  };

  const handleUseExample = (example: string) => {
    setInput(example);
  };

  if (isBootstrapping || !payload) {
    return (
      <main className="workspace-shell workspace-shell--loading">
        <div className="loading-card">
          <div className="brand-mark">QA</div>
          <h1>QuantAgent Workspace 준비 중</h1>
          <p>Mock strategy, candidate, report payload를 불러오고 있습니다.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="workspace-shell">
      <div className="workspace-topbar">
        <div className="workspace-topbar__brand">
          <div className="brand-mark">QA</div>
          <div>
            <strong>QuantAgent</strong>
            <span>Premium Financial Dashboard · `/app` MVP</span>
          </div>
        </div>
        <div className="workspace-topbar__meta">
          <span className="status-indicator">
            <i />
            {activeScenarioLabel}
          </span>
          <span className="mock-badge">Mock service layer</span>
        </div>
      </div>

      <div className="workspace-grid">
        <ChatPanel
          messages={messages}
          examples={examples}
          input={input}
          selectedScenario={selectedScenario}
          scenarioPayload={scenarioPayload}
          onInputChange={setInput}
          onScenarioChange={setSelectedScenario}
          onSubmit={handleSubmit}
          onSelectStrategy={handleSelectStrategy}
          onUseExample={handleUseExample}
        />
        <AnalysisTabs payload={payload} scenario={scenarioPayload} />
      </div>
    </main>
  );
}
