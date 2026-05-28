import { useState, type FormEvent } from "react";
import type { ChatMessage, StrategySpec } from "../../types/quantagent";
import { Button } from "../../components/common/Button";
import { ROUTES } from "../../config/routes";

interface StrategyInputPanelProps {
  strategy: StrategySpec;
  messages: ChatMessage[];
  onAnalyze?: (query: string) => Promise<void>;
}

export function StrategyInputPanel({ strategy, messages, onAnalyze }: StrategyInputPanelProps) {
  const [draft, setDraft] = useState(strategy.natural_language_strategy);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError(null);

    if (!onAnalyze) {
      const params = new URLSearchParams({ draft });
      window.location.assign(`${ROUTES.strategyNew}?${params.toString()}`);
      return;
    }

    setSubmitting(true);
    try {
      await onAnalyze(draft);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "AI 분석 요청에 실패했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <aside className="chat-panel">
      <div className="chat-panel__head">
        <div>
          <strong>전략 채팅</strong>
          <p>활성 전략: {strategy.name ?? strategy.natural_language_strategy}</p>
        </div>
        <Button onClick={() => window.location.assign(ROUTES.strategyNew)} variant="ghost">+ 새 대화</Button>
      </div>
      <div className="chat-panel__stream">
        {messages.map((message) => (
          <article className={`chat-message chat-message--${message.sender}`} key={message.id}>
            <div className="chat-message__meta">
              <span>{message.label}</span>
              <small>{message.time}</small>
            </div>
            <p>{message.body}</p>
            {message.stats ? (
              <div className="chat-message__stats">
                {message.stats.map((stat) => (
                  <span key={stat.label}>
                    <small>{stat.label}</small>
                    <strong>{stat.value}</strong>
                  </span>
                ))}
              </div>
            ) : null}
            {message.sender === "agent" ? <button onClick={() => window.location.assign(ROUTES.app)} type="button">대시보드에서 결과 보기 →</button> : null}
          </article>
        ))}
      </div>
      <form className="chat-panel__input" onSubmit={handleSubmit}>
        <div className="chat-panel__inputbox">
          <input
            aria-label="자연어 전략"
            disabled={submitting}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="전략을 자연어로 입력하세요"
            value={draft}
          />
          <button disabled={submitting} type="submit">{submitting ? "…" : "↑"}</button>
        </div>
        {submitError ? <small className="chat-panel__error">{submitError}</small> : null}
        <small>거래비용 0.015% / 0.23% / 0.1% 반영 · KOSPI200 현물만 지원</small>
      </form>
    </aside>
  );
}
