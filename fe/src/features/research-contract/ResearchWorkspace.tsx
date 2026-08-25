import { FormEvent, useEffect, useState } from "react";

import {
  ResearchApiError,
  confirmResearchJob,
  getResearchJobResult,
  reviewResearchRule,
} from "@/api/researchClient";
import type {
  ResearchJobAcceptedV1,
  ResearchResultV1,
  ResearchRuleDraftV1,
  ResearchScopeRefusalV1,
} from "@/types/researchContract";
import { ResearchResultRenderer } from "./ResearchResultRenderer";

const RESULT_POLL_INTERVAL_MS = 1_000;

/**
 * The authenticated research workspace. It keeps raw input in component memory only
 * and can make a job only from a server-signed canonical rule review.
 */
export function ResearchWorkspace() {
  const [naturalLanguage, setNaturalLanguage] = useState("");
  const [draft, setDraft] = useState<ResearchRuleDraftV1 | null>(null);
  const [scopeRefusal, setScopeRefusal] = useState<ResearchScopeRefusalV1 | null>(null);
  const [acceptedJob, setAcceptedJob] = useState<ResearchJobAcceptedV1 | null>(null);
  const [result, setResult] = useState<ResearchResultV1 | null>(null);
  const [isReviewing, setIsReviewing] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!acceptedJob || result) {
      return undefined;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const nextResult = await getResearchJobResult(acceptedJob.job_id);
        if (!cancelled) {
          setResult(nextResult);
        }
      } catch {
        if (!cancelled) {
          setError("결과 상태를 확인할 수 없습니다. 잠시 뒤 다시 시도해 주세요.");
        }
      }
    };
    void poll();
    const interval = window.setInterval(() => void poll(), RESULT_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [acceptedJob, result]);

  async function handleReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const requestText = naturalLanguage.trim();
    if (!requestText) {
      setError("일반 조건식을 입력해 주세요.");
      return;
    }
    setIsReviewing(true);
    setError(null);
    setDraft(null);
    setScopeRefusal(null);
    setAcceptedJob(null);
    setResult(null);
    try {
      const review = await reviewResearchRule(requestText);
      if (review.kind === "rule_draft") {
        setDraft(review);
      } else {
        setScopeRefusal(review);
      }
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setIsReviewing(false);
    }
  }

  async function handleConfirmation() {
    if (!draft?.is_executable || !draft.canonical_rule) {
      return;
    }
    setIsConfirming(true);
    setError(null);
    try {
      setAcceptedJob(await confirmResearchJob(draft.canonical_rule, draft.draft_token));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setIsConfirming(false);
    }
  }

  return (
    <section aria-labelledby="research-workspace-title" className="research-workspace">
      <div className="research-workspace__head">
        <div>
          <p className="research-workspace__eyebrow">일반 조건식 검토</p>
          <h1 id="research-workspace-title">한국 주식 EOD 리서치</h1>
          <p>개인 보유나 직접 행동 요청 없이, 일반 조건식의 일치 여부만 검토합니다.</p>
        </div>
      </div>

      <form className="research-workspace__form" onSubmit={handleReview}>
        <label htmlFor="research-rule-input">검토할 일반 조건식</label>
        <textarea
          id="research-rule-input"
          value={naturalLanguage}
          onChange={(event) => setNaturalLanguage(event.target.value)}
          placeholder="예: RSI가 30 이하이고 RSI가 70 이상인 KRX 일봉 조건식"
          maxLength={500}
          rows={4}
          disabled={isReviewing || isConfirming}
        />
        <div className="research-workspace__form-footer">
          <small>입력은 규칙 검토에만 사용되며 브라우저 저장소에 보관하지 않습니다.</small>
          <button className="button button--dark" type="submit" disabled={isReviewing || isConfirming}>
            {isReviewing ? "조건을 확인하는 중" : "조건식 검토"}
          </button>
        </div>
      </form>

      {scopeRefusal ? (
        <section aria-live="polite" className="research-workspace__notice">
          <h2>현재 범위에서 검토할 수 없습니다</h2>
          <p>{scopeRefusal.explanation}</p>
          <p>{scopeRefusal.guidance}</p>
          <p>일반 예시: {scopeRefusal.general_example}</p>
        </section>
      ) : null}

      {draft ? <RuleDraftReview draft={draft} isConfirming={isConfirming} onConfirm={handleConfirmation} /> : null}
      {acceptedJob && !result ? <p aria-live="polite">검토 결과 상태를 확인하는 중입니다.</p> : null}
      {result ? <ResearchResultRenderer result={result} /> : null}
      {error ? <p className="research-workspace__error" role="alert">{error}</p> : null}
    </section>
  );
}

function RuleDraftReview({
  draft,
  isConfirming,
  onConfirm,
}: {
  draft: ResearchRuleDraftV1;
  isConfirming: boolean;
  onConfirm: () => void;
}) {
  return (
    <section aria-labelledby="rule-review-title" className="research-workspace__review">
      <h2 id="rule-review-title">검토된 조건식</h2>
      <p>{draft.editable_summary}</p>
      {draft.clarifications.length ? (
        <ul>
          {draft.clarifications.map((choice) => (
            <li key={choice.label}>
              <strong>{choice.label}</strong> · {choice.reason}
            </li>
          ))}
        </ul>
      ) : null}
      {draft.is_executable ? (
        <button className="button button--dark" type="button" onClick={onConfirm} disabled={isConfirming}>
          {isConfirming ? "검토를 시작하는 중" : "이 조건식으로 검토 시작"}
        </button>
      ) : (
        <p>조건식을 보완하면 다음 단계로 진행할 수 있습니다.</p>
      )}
    </section>
  );
}

function errorMessage(cause: unknown) {
  if (cause instanceof ResearchApiError && cause.status === 503) {
    return "현재 운영 검증이 완료되지 않아 조건식 실행을 시작할 수 없습니다.";
  }
  return "요청을 처리할 수 없습니다. 잠시 뒤 다시 시도해 주세요.";
}
