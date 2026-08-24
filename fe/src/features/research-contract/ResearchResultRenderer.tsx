import type { ResearchResultV1 } from "@/types/researchContract";

interface ResearchResultRendererProps {
  result: ResearchResultV1;
}

/**
 * Contract renderer kept off the public route until the release gate wires a verified
 * ResearchResultV1 endpoint. It consumes only the safe public projection.
 */
export function ResearchResultRenderer({ result }: ResearchResultRendererProps) {
  switch (result.status) {
    case "ready":
      return (
        <section aria-labelledby="research-result-title">
          <h2 id="research-result-title">조건 일치 결과</h2>
          <p>
            출처 PostgreSQL · 기준일 {result.provenance.as_of} · 조회 범위 {result.provenance.universe_count}개 · 조건 일치 {result.provenance.candidate_count}개
          </p>
          <ul>
            {result.candidates.map((candidate) => (
              <li key={`${candidate.ticker}:${candidate.as_of}`}>
                <strong>{candidate.name}</strong> ({candidate.ticker}) · {candidate.matched_conditions.join(" · ")}
              </li>
            ))}
          </ul>
        </section>
      );
    case "need_clarification":
      return (
        <section aria-labelledby="research-result-title">
          <h2 id="research-result-title">입력 확인이 필요합니다</h2>
          <p>{result.explanation}</p>
          <ul>
            {result.choices.map((choice) => (
              <li key={choice.label}>
                <strong>{choice.label}</strong> · {choice.reason}
              </li>
            ))}
          </ul>
        </section>
      );
    case "no_match":
      return (
        <section aria-labelledby="research-result-title">
          <h2 id="research-result-title">조건 일치 항목이 없습니다</h2>
          <p>{result.explanation}</p>
          <p>출처 PostgreSQL · 기준일 {result.provenance.as_of}의 조건 일치 수는 0개입니다.</p>
        </section>
      );
    case "unavailable":
      return (
        <section aria-labelledby="research-result-title">
          <h2 id="research-result-title">결과를 표시할 수 없습니다</h2>
          <p>{result.explanation}</p>
          <p>{result.retryable ? "운영 데이터 상태가 확인된 뒤 다시 시도할 수 있습니다." : "현재는 다시 시도할 수 없습니다."}</p>
        </section>
      );
    case "failed":
      return (
        <section aria-labelledby="research-result-title">
          <h2 id="research-result-title">처리에 실패했습니다</h2>
          <p>{result.explanation}</p>
          <p>문의 시 참조 번호: {result.support_reference}</p>
        </section>
      );
    case "dev_preview":
      return (
        <section aria-labelledby="research-result-title">
          <h2 id="research-result-title">개발 검증 미리보기</h2>
          <p>{result.explanation}</p>
          <p>이 상태는 운영 데이터 결과가 아니며 공개 화면에서 사용하지 않습니다.</p>
        </section>
      );
  }
}
