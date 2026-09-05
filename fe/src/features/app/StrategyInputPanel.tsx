import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUp, ChevronDown, Plus, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type {
  ChatConversationPreview,
  ChatMessage,
  StrategyCandidateCard,
  StrategySpec,
  WorkspaceAnalysisStatus,
} from "@/types/quantagent";

interface StrategyInputPanelProps {
  /** Extra classes for the panel shell, used by the phone pane switch to hide it. */
  className?: string;
  history: ChatConversationPreview[];
  strategy: StrategySpec;
  messages: ChatMessage[];
  onAnalyze: (query: string) => Promise<void>;
  /** Set while an analysis is running, so the submit control becomes a stop control. */
  onCancel?: () => Promise<void>;
  running?: boolean;
  /** True from the moment stop is pressed, before the server has acknowledged. */
  cancelRequested?: boolean;
  cancelError?: string | null;
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

const cardButtonClass =
  "w-full rounded-2xl border border-dark-line bg-dark-surface p-3 text-left transition-colors hover:border-cornflower/60";

export function StrategyInputPanel({
  className,
  history,
  strategy,
  messages,
  onAnalyze,
  onCancel,
  running = false,
  cancelRequested = false,
  cancelError = null,
  onNewConversation,
  onRestoreConversation,
}: StrategyInputPanelProps) {
  const [draft, setDraft] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const streamEndRef = useRef<HTMLDivElement | null>(null);
  const activeStrategyLabel = messages.length
    ? strategy.name ?? strategy.natural_language_strategy
    : "채팅으로 전략을 입력하면 워크스페이스를 채웁니다.";
  // Without this the newest agent message lands below the fold and the panel looks stuck.
  useEffect(() => {
    streamEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);

  const submitQuery = async (query: string) => {
    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      setSubmitError("분석할 자연어 전략을 입력하세요.");
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
    const query = card.backtest_query || `후보 확정: strategy_id=${card.strategy_id}; ${card.title}. ${card.summary} 조건: ${card.key_conditions.join(", ")}.`;
    setDraft(query);
    setSubmitError(null);
    await submitQuery(query);
  };

  const handleNewConversation = () => {
    setDraft("");
    setSubmitError(null);
    onNewConversation();
  };

  // An analysis is already in flight; a second submit would start a parallel paid run.
  const inputDisabled = submitting || running;

  return (
    <aside
      className={cn(
        "sticky flex min-h-0 w-full shrink-0 flex-col bg-dark text-[#edeff4]",
        // Phone: sits under the top bar (56px) plus the pane switch (60px), and takes the
        // rest of the small viewport. Desktop: full height beside the workspace.
        "top-29 h-[calc(100dvh-7.25rem)] md:top-14 md:h-[calc(100dvh-3.5rem)] md:w-80 xl:w-[400px]",
        className,
      )}
    >
      <div className="flex shrink-0 items-start justify-between gap-3 border-b border-dark-line p-5">
        <div className="min-w-0">
          <strong className="text-[13px]">전략 채팅</strong>
          <p className="mt-1 truncate text-[11px] text-subdued">{activeStrategyLabel}</p>
        </div>
        <Button className="shrink-0 rounded-full" onClick={handleNewConversation} size="sm" variant="onDark">
          <Plus aria-hidden className="size-3.5" />새 대화
        </Button>
      </div>

      {history.length ? (
        <details className="group max-h-56 shrink-0 overflow-y-auto border-b border-dark-line px-5 py-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-xs font-extrabold [&::-webkit-details-marker]:hidden">
            <span className="flex items-center gap-1.5">
              <ChevronDown aria-hidden className="size-3.5 transition-transform group-open:rotate-180" />
              이전 대화
            </span>
            <small className="text-[10px] font-bold text-subdued">{history.length}</small>
          </summary>
          <div className="mt-3 flex flex-col gap-2">
            {history.map((conversation) => (
              <details className="rounded-2xl border border-dark-line bg-white/3 p-2.5" key={conversation.id}>
                <summary className="flex cursor-pointer list-none items-start justify-between gap-3 text-[11px] font-extrabold leading-snug [&::-webkit-details-marker]:hidden">
                  <span className="min-w-0 truncate">{conversation.title}</span>
                  <small className="shrink-0 text-[10px] font-bold text-subdued">
                    {formatHistoryTime(conversation.updatedAt)} · {STATUS_LABELS[conversation.status]}
                  </small>
                </summary>
                <div className="mt-2.5 flex flex-col gap-1.5">
                  {conversation.messages.slice(0, HISTORY_MESSAGE_LIMIT).map((message) => (
                    <p className="border-t border-dark-line pt-1.5 text-[10px] leading-relaxed" key={message.id}>
                      <strong className="mb-0.5 block text-[9px] text-subdued">{message.label}</strong>
                      <span className="line-clamp-2">{message.body}</span>
                    </p>
                  ))}
                </div>
                <Button
                  className="mt-2.5 w-full rounded-xl"
                  disabled={running}
                  onClick={() => onRestoreConversation(conversation.id)}
                  size="sm"
                  variant="onDark"
                >
                  이 대화 열기
                </Button>
              </details>
            ))}
          </div>
        </details>
      ) : null}

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-5">
        {messages.map((message) => (
          <article
            className={cn("flex flex-col", message.sender === "user" ? "items-end" : "items-start")}
            key={message.id}
          >
            <div className="mb-1.5 flex items-center gap-1.5">
              <span
                className={cn(
                  "rounded px-1.5 py-px text-[9px] font-extrabold",
                  message.sender === "user"
                    ? "bg-cornflower text-white"
                    : "border border-dark-line bg-dark-surface text-subdued",
                )}
              >
                {message.label}
              </span>
              <small className="text-[10px] text-subdued">{message.time}</small>
            </div>

            {/* Toss-ish bubbles: generously rounded, with the corner nearest the speaker
                tightened so the direction of the message stays readable. whitespace-pre-line
                keeps the agent's line breaks - a completed analysis lists the conditions it
                chose on the user's behalf, which collapses into one run-on line without it. */}
            <p
              className={cn(
                "max-w-[92%] whitespace-pre-line rounded-bubble px-3.5 py-3 text-xs leading-relaxed",
                message.sender === "user"
                  ? "rounded-br-md bg-cornflower text-white"
                  : "rounded-bl-md border border-dark-line bg-dark-surface",
              )}
            >
              {message.body}
            </p>

            {message.clarification && !message.candidateCards?.length ? (
              <div className="mt-2.5 w-full rounded-2xl border border-dark-line bg-white/3 p-2.5">
                <strong className="block text-xs">{message.clarification.question}</strong>
                <div className="mt-2 flex flex-col gap-2">
                  {message.clarification.options.map((option) => (
                    <button
                      className={cn(
                        cardButtonClass,
                        message.clarification?.recommended === message.clarification?.options.indexOf(option) &&
                          "border-cornflower shadow-[inset_3px_0_0_var(--color-cornflower)]",
                      )}
                      disabled={inputDisabled}
                      key={`${message.id}:option:${option.label}`}
                      onClick={() => {
                        const retryQuery = message.clarification?.retryQuery;
                        if (option.label === "다시 시도" && retryQuery) {
                          setSubmitError(null);
                          void submitQuery(retryQuery);
                          return;
                        }
                        setDraft(option.label);
                      }}
                      type="button"
                    >
                      <span className="block text-xs font-bold">{option.label}</span>
                      <small className="mt-1 block text-[10px] leading-relaxed text-subdued">{option.reason}</small>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {message.candidateCards?.length ? (
              <div className="mt-2.5 flex w-full flex-col gap-2">
                {message.candidateCards.map((card) => (
                  <button
                    className={cardButtonClass}
                    disabled={inputDisabled}
                    key={`${message.id}:card:${card.strategy_id}`}
                    onClick={() => void handleCandidateSelect(card)}
                    type="button"
                  >
                    <span className="flex items-center justify-between gap-2">
                      <strong className="text-xs">{card.title}</strong>
                      <small className="text-[10px] font-bold text-subdued">
                        AI confidence {Math.round(card.confidence * 100)}%
                      </small>
                    </span>
                    <p className="mt-2 text-[11px] leading-relaxed text-[#dfe3ee]">{card.summary}</p>
                    <em className="mt-2 block text-[10px] not-italic leading-relaxed text-cornflower">
                      {card.key_conditions.join(" · ")}
                    </em>
                    {card.reason ? (
                      <small className="mt-1 block text-[10px] leading-relaxed text-subdued">{card.reason}</small>
                    ) : null}
                  </button>
                ))}
              </div>
            ) : null}

            {message.stats ? (
              <div className="mt-2.5 grid w-full grid-cols-3 gap-1.5">
                {message.stats.map((stat) => (
                  <span className="rounded-xl border border-dark-line px-2.5 py-1.5" key={stat.label}>
                    <small className="block text-[9px] text-subdued">{stat.label}</small>
                    <strong className="text-sm">{stat.value}</strong>
                  </span>
                ))}
              </div>
            ) : null}
          </article>
        ))}
        <div ref={streamEndRef} />
      </div>

      <form className="shrink-0 border-t border-dark-line bg-dark p-5" onSubmit={handleSubmit}>
        <div
          className={cn(
            "flex items-center gap-2 rounded-field border border-dark-line bg-dark-surface px-3 py-2.5",
            "transition-colors focus-within:border-cornflower",
          )}
        >
          <input
            aria-label="자연어 전략"
            className="min-w-0 flex-1 bg-transparent text-xs text-[#edeff4] outline-none placeholder:text-subdued disabled:text-subdued"
            disabled={inputDisabled}
            maxLength={2000}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={running ? "분석이 진행 중입니다" : "전략을 자연어로 입력하세요"}
            required
            value={draft}
          />
          {running && onCancel ? (
            // While a run is in flight the same control stops it: an analysis costs money
            // for every node it completes, so leaving the user no way out is expensive.
            <button
              aria-label="분석 중단"
              className="flex size-10 shrink-0 items-center justify-center rounded-full bg-drop text-white transition-opacity disabled:opacity-60 md:size-8"
              disabled={cancelRequested}
              onClick={() => void onCancel()}
              type="button"
            >
              {cancelRequested ? (
                <span className="text-[9px] font-bold leading-none">중단</span>
              ) : (
                <Square aria-hidden className="size-3 fill-current" />
              )}
            </button>
          ) : (
            <button
              aria-label="분석 요청"
              className="flex size-10 shrink-0 items-center justify-center rounded-full bg-cornflower text-white transition-opacity disabled:opacity-60 md:size-8"
              disabled={submitting}
              type="submit"
            >
              <ArrowUp aria-hidden className="size-4" />
            </button>
          )}
        </div>
        {submitError ? <small className="mt-2 block text-[11px] text-[#ffb4a8]">{submitError}</small> : null}
        {cancelError ? <small className="mt-2 block text-[11px] text-[#ffb4a8]">{cancelError}</small> : null}
        <small className="mt-2 block text-[11px] text-subdued">
          거래비용 0.015% / 0.23% / 0.1% 반영 · KRX 상장 보통주 지원
        </small>
      </form>
    </aside>
  );
}
