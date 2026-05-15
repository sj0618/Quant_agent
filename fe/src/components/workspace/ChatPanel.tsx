import type { FormEvent, KeyboardEvent } from "react";
import type { ChatMessage, ScenarioCode, ScenarioPayload } from "../../types/quantagent";
import { ScenarioCards } from "./ScenarioCards";

const SCENARIO_OPTIONS: Array<{ value: ScenarioCode | "AUTO"; label: string }> = [
  { value: "AUTO", label: "Auto detect" },
  { value: "C1_INPUT_AMBIGUOUS", label: "C1 INPUT_AMBIGUOUS" },
  { value: "C2_TERM_UNKNOWN", label: "C2 TERM_UNKNOWN" },
  { value: "C4_CONFLICTING", label: "C4 CONFLICTING" },
  { value: "C5_INFEASIBLE", label: "C5 INFEASIBLE" },
];

export function ChatPanel({
  messages,
  examples,
  input,
  selectedScenario,
  scenarioPayload,
  onInputChange,
  onScenarioChange,
  onSubmit,
  onSelectStrategy,
  onUseExample,
}: {
  messages: ChatMessage[];
  examples: string[];
  input: string;
  selectedScenario: ScenarioCode | "AUTO";
  scenarioPayload?: ScenarioPayload;
  onInputChange: (value: string) => void;
  onScenarioChange: (value: ScenarioCode | "AUTO") => void;
  onSubmit: () => void;
  onSelectStrategy: (strategyId: string) => void;
  onUseExample: (example: string) => void;
}) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  };

  return (
    <aside className="chat-panel" aria-labelledby="strategy-console-title">
      <div className="chat-panel__header">
        <div>
          <span className="eyebrow">Strategy Console</span>
          <h2 id="strategy-console-title">전략 입력</h2>
          <p>자연어 전략을 입력하면 전략 후보와 신호를 생성합니다.</p>
        </div>
      </div>

      <div className="mock-control">
        <label htmlFor="scenario-select">Mock scenario selector</label>
        <select
          id="scenario-select"
          value={selectedScenario}
          onChange={(event) => onScenarioChange(event.target.value as ScenarioCode | "AUTO")}
        >
          {SCENARIO_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="message-stream" aria-label="QuantAgent message stream">
        <div className="message-stream__label">
          <span>대화 기록</span>
          <small>{messages.length} messages</small>
        </div>
        {messages.map((message) => (
          <article className={`message message--${message.role}`} key={message.id}>
            <span>{message.role === "user" ? "사용자" : message.role === "system" ? "상태" : "QuantAgent"}</span>
            <p>{message.content}</p>
          </article>
        ))}
        <ScenarioCards scenario={scenarioPayload} onSelectStrategy={onSelectStrategy} onUseExample={onUseExample} />
      </div>

      <div className="example-buttons">
        <span>예시 전략</span>
        {examples.map((example) => (
          <button type="button" key={example} onClick={() => onUseExample(example)}>
            {example}
          </button>
        ))}
      </div>

      <form className="strategy-input-box" onSubmit={submit}>
        <textarea
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="예: RSI가 낮고 거래량이 증가한 종목 찾아줘"
          rows={4}
        />
        <button className="primary-button" type="submit">
          전략 분석
        </button>
      </form>

      <p className="disclaimer">본 서비스는 투자 참고용이며, 매매 판단의 책임은 사용자에게 있습니다.</p>
    </aside>
  );
}
