import type { ChatMessage, StrategySpec } from "../../types/quantagent";
import { Button } from "../../components/common/Button";

interface StrategyInputPanelProps {
  strategy: StrategySpec;
  messages: ChatMessage[];
}

export function StrategyInputPanel({ strategy, messages }: StrategyInputPanelProps) {
  return (
    <aside className="chat-panel">
      <div className="chat-panel__head">
        <div>
          <strong>전략 채팅</strong>
          <p>활성 전략: 반도체 모멘텀 + 기관 매수</p>
        </div>
        <Button variant="ghost">+ 새 대화</Button>
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
            {message.sender === "agent" ? <button type="button">대시보드에서 결과 보기 →</button> : null}
          </article>
        ))}
      </div>
      <div className="chat-panel__input">
        <div className="chat-panel__inputbox">
          <span>{strategy.natural_language_strategy || "전략을 자연어로 입력하세요"}</span>
          <button type="button">↑</button>
        </div>
        <small>거래비용 0.015% / 0.23% / 0.1% 반영 · KOSPI200 현물만 지원</small>
      </div>
    </aside>
  );
}
