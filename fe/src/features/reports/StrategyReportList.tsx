import { useState } from "react";
import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import {
  MAX_EMAIL_DIGEST_STRATEGIES,
  getDigestStrategySelection,
  toggleDigestStrategySelection,
} from "../../api/emailDigestClient";
import { ROUTES } from "../../config/routes";
import type { SignalType, StrategyReportSummary } from "../../types/quantagent";
import {
  DEFAULT_STRATEGY_REPORT_FILTERS,
  type StrategyReportFilters,
  type StrategyReportRange,
} from "./strategyReportFilters";

interface StrategyReportListProps {
  allStrategies: StrategyReportSummary[];
  filters: StrategyReportFilters;
  onApplyFilters: (filters: StrategyReportFilters) => void;
  onResetFilters: () => void;
  strategies: StrategyReportSummary[];
}

const SIGNALS: SignalType[] = ["BUY", "HOLD", "DROP"];
const RANGE_OPTIONS: Array<[string, StrategyReportRange]> = [
  ["오늘", "1"],
  ["최근 7일", "7"],
  ["최근 30일", "30"],
  ["최근 3개월", "90"],
  ["전체", "all"],
];

function statusVariant(status: StrategyReportSummary["latestStatus"]) {
  if (status === "failed") {
    return "negative";
  }
  return "info";
}

function statusLabel(status: StrategyReportSummary["latestStatus"]) {
  if (status === "failed") {
    return "전송 실패";
  }
  if (status === "resent") {
    return "재전송";
  }
  if (status === "draft") {
    return "초안";
  }
  return "전송 완료";
}

export function StrategyReportList({
  allStrategies,
  filters,
  onApplyFilters,
  onResetFilters,
  strategies,
}: StrategyReportListProps) {
  const [draftFilters, setDraftFilters] = useState(filters);
  const [selection, setSelection] = useState<string[]>(() => getDigestStrategySelection());
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const updateSignal = (signal: SignalType, checked: boolean) => {
    setDraftFilters((current) => ({
      ...current,
      signals: { ...current.signals, [signal]: checked },
    }));
  };

  const handleToggle = (strategy: StrategyReportSummary, checked: boolean) => {
    try {
      const next = toggleDigestStrategySelection(strategy.id, checked);
      setSelection(next);
      setError(null);
      setStatus(
        checked
          ? `${strategy.name} 전략을 이메일 수신 목록에 추가했습니다.`
          : `${strategy.name} 전략을 이메일 수신 목록에서 제외했습니다.`,
      );
    } catch (toggleError) {
      setError(toggleError instanceof Error ? toggleError.message : "선택을 저장하지 못했습니다.");
    }
  };

  return (
    <div className="reports-layout">
      <aside className="reports-sidebar">
        <Card className="filter-group">
          <strong>기간</strong>
          {RANGE_OPTIONS.map(([label, value]) => (
            <button
              className={draftFilters.range === value ? "is-active" : ""}
              key={value}
              onClick={() => setDraftFilters((current) => ({ ...current, range: value }))}
              type="button"
            >
              <span className="filter-check" />
              <span>{label}</span>
            </button>
          ))}
        </Card>

        <Card className="filter-group">
          <strong>포함 신호</strong>
          {SIGNALS.map((signal) => (
            <label className={draftFilters.signals[signal] ? "is-active" : ""} key={signal}>
              <input checked={draftFilters.signals[signal]} onChange={(event) => updateSignal(signal, event.target.checked)} type="checkbox" />
              <span className="filter-check" />
              <span>{signal} 포함</span>
              <Badge variant="soft">
                {allStrategies.filter((strategy) => strategy.signals[signal] > 0).length}
              </Badge>
            </label>
          ))}
        </Card>

        <Card className="score-filter">
          <strong>권장도</strong>
          <span>최소 점수 <b>{draftFilters.minScore.toFixed(1)}</b></span>
          <input
            max="10"
            min="0"
            onChange={(event) => setDraftFilters((current) => ({ ...current, minScore: Number(event.target.value) }))}
            step="0.1"
            type="range"
            value={draftFilters.minScore}
          />
          <div>
            <button
              onClick={() => {
                setDraftFilters(DEFAULT_STRATEGY_REPORT_FILTERS);
                onResetFilters();
              }}
              type="button"
            >
              초기화
            </button>
            <button onClick={() => onApplyFilters(draftFilters)} type="button">적용</button>
          </div>
        </Card>
      </aside>

      <section className="reports-main">
        {status ? <div className="action-feedback">{status}</div> : null}
        {error ? <div className="action-feedback action-feedback--error">{error}</div> : null}

        <div className="report-list-head">
          <strong>전략 레포트</strong>
          <span>{strategies.length}개</span>
          <Badge variant="info">{selection.length}/{MAX_EMAIL_DIGEST_STRATEGIES}개 이메일 구독</Badge>
        </div>

        {strategies.length === 0 ? (
          <Card className="empty-inline">
            <strong>조건에 맞는 전략 레포트가 없습니다</strong>
            <p>기간, 신호, 권장도 필터를 조정해 보세요.</p>
          </Card>
        ) : (
          <div className="strategy-report-grid">
            {strategies.map((strategy) => {
              const checked = selection.includes(strategy.id);
              const disabled = !checked && selection.length >= MAX_EMAIL_DIGEST_STRATEGIES;

              return (
                <Card className="strategy-report-card" key={strategy.id}>
                  <div className="strategy-report-card__top">
                    <Badge variant="dark">PARENT STRATEGY</Badge>
                    <label className={["strategy-report-card__checkbox", checked ? "is-checked" : "", disabled ? "is-disabled" : ""].filter(Boolean).join(" ")}>
                      <input
                        checked={checked}
                        disabled={disabled}
                        onChange={(event) => handleToggle(strategy, event.target.checked)}
                        type="checkbox"
                      />
                      <span>이메일 구독</span>
                    </label>
                  </div>

                  <div className="strategy-report-card__head">
                    <div>
                      <h2>{strategy.name}</h2>
                      <p>{strategy.description}</p>
                    </div>

                  </div>

                  <div className="strategy-report-card__meta">
                    <div className="strategy-report-card__meta-item">
                      <small>유니버스</small>
                      <strong>{strategy.universe}</strong>
                    </div>
                    <div className="strategy-report-card__meta-item">
                      <small>진입 기준</small>
                      <strong>{strategy.entrySummary}</strong>
                    </div>
                    <div className="strategy-report-card__meta-item">
                      <small>권장도</small>
                      <strong>{strategy.recommendationScore}</strong>
                    </div>
                    <div className="strategy-report-card__meta-item">
                      <small>신호</small>
                      <div className="strategy-report-card__signal-stack">
                        {strategy.signals.BUY ? <Badge signal="BUY">BUY {strategy.signals.BUY}</Badge> : null}
                        {strategy.signals.HOLD ? <Badge signal="HOLD">HOLD {strategy.signals.HOLD}</Badge> : null}
                        {strategy.signals.DROP ? <Badge signal="DROP">DROP {strategy.signals.DROP}</Badge> : null}
                      </div>
                    </div>
                  </div>

                  <p className="strategy-report-card__summary">{strategy.summary}</p>

                  <div className="strategy-report-card__footer">
                    <small>{strategy.latestReportDate} · {strategy.latestSentAt}</small>
                    <a href={ROUTES.strategyReportDetail(strategy.id)}>전략 상세 보기 →</a>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
