import { useState, type FormEvent } from "react";
import type { ChatConversationPreview, ChatMessage, StrategyCandidateCard, StrategySpec, WorkspaceAnalysisStatus } from "../../types/quantagent";
import { Button } from "../../components/common/Button";

interface StrategyInputPanelProps {
  history: ChatConversationPreview[];
  strategy: StrategySpec;
  messages: ChatMessage[];
  onAnalyze: (query: string) => Promise<void>;
  onNewConversation: () => void;
  onRestoreConversation: (conversationId: string) => void;
}

const STATUS_LABELS: Record<WorkspaceAnalysisStatus, string> = {
  failed: "실패",
  need_clarification: "선택 필요",
  ready: "완료",
  rejected: "거절",
  running: "진행 중",
};

const HISTORY_MESSAGE_LIMIT = 3;

function formatHistoryTime(value: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function StrategyInputPanel({
  history,
  strategy,
  messages,
  onAnalyze,
  onNewConversation,
  onRestoreConversation,
}: StrategyInputPanelProps) {
  const [draft, setDraft] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const activeStrategyLabel = messages.length
    ? strategy.name ?? strategy.natural_language_strategy
    : "채팅으로 전략을 입력하면 워크스페이스를 채웁니다.";

  const submitQuery = async (query: string) => {
    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      return;
    }

    setSubmitting(true);
    try {
      await onAnalyze(trimmedQuery);
      setDraft("");
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "AI 분석 요청에 실패했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError(null);
    await submitQuery(draft);
  };

  const handleCandidateSelect = async (card: StrategyCandidateCard) => {
    const query = `후보 확정: strategy_id=${card.strategy_id}; ${card.title}. ${card.summary} 조건: ${card.key_conditions.join(", ")}.`;
    setDraft(query);
    setSubmitError(null);
    await submitQuery(query);
  };

  const handleNewConversation = () => {
    setDraft("");
    setSubmitError(null);
    onNewConversation();
  };

  return (
    <aside className="chat-panel">
      <div className="chat-panel__head">
        <div>
          <strong>전략 채팅</strong>
          <p>{activeStrategyLabel}</p>
        </div>
        <Button onClick={handleNewConversation} variant="ghost">+ 새 대화</Button>
      </div>
      {history.length ? (
        <details className="chat-history">
          <summary>
            <span>이전 대화</span>
            <small>{history.length}</small>
          </summary>
          <div className="chat-history__list">
            {history.map((conversation) => (
              <details className="chat-history__item" key={conversation.id}>
                <summary>
                  <span>{conversation.title}</span>
                  <small>{formatHistoryTime(conversation.updatedAt)} · {STATUS_LABELS[conversation.status]}</small>
                </summary>
                <div className="chat-history__messages">
                  {conversation.messages.slice(0, HISTORY_MESSAGE_LIMIT).map((message) => (
                    <p key={message.id}>
                      <strong>{message.label}</strong>
                      <span>{message.body}</span>
                    </p>
                  ))}
                </div>
                <button disabled={submitting} onClick={() => onRestoreConversation(conversation.id)} type="button">
                  이 대화 열기
                </button>
              </details>
            ))}
          </div>
        </details>
      ) : null}
      <div className="chat-panel__stream">
        {messages.map((message) => (
          <article className={`chat-message chat-message--${message.sender}`} key={message.id}>
            <div className="chat-message__meta">
              <span>{message.label}</span>
              <small>{message.time}</small>
            </div>
            <p>{message.body}</p>
            {message.clarification ? (
              <div className="chat-message__clarification">
                <strong>{message.clarification.question}</strong>
                <div>
                  {message.clarification.options.map((option, index) => (
                    <button
                      className={message.clarification?.recommended === index ? "is-recommended" : ""}
                      disabled={submitting}
                      key={`${message.id}:option:${option.label}`}
                      onClick={() => {
                        setDraft(option.label);
                      }}
                      type="button"
                    >
                      <span>{option.label}</span>
                      <small>{option.reason}</small>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            {message.candidateCards?.length ? (
              <div className="chat-message__cards">
                {message.candidateCards.map((card) => (
                  <button
                    disabled={submitting}
                    key={`${message.id}:card:${card.strategy_id}`}
                    onClick={() => void handleCandidateSelect(card)}
                    type="button"
                  >
                    <span>
                      <strong>{card.title}</strong>
                      <small>{Math.round(card.confidence * 100)}%</small>
                    </span>
                    <p>{card.summary}</p>
                    <em>{card.key_conditions.join(" · ")}</em>
                    {card.reason ? <small>{card.reason}</small> : null}
                  </button>
                ))}
              </div>
            ) : null}
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
            {message.sender === "agent" ? (
              <button onClick={() => window.scrollTo({ behavior: "smooth", top: 0 })} type="button">워크스페이스 보기 →</button>
            ) : null}
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
