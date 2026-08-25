import type { ResearchResultV1 } from "@/types/researchContract";
import { ResultTrustLinks } from "@/components/common/ResultTrustLinks";

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
          <ResearchResultDisclosure />
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
          <ResultTrustLinks resultId={result.result_id} version={result.rule_version} />
        </section>
      );
    case "need_clarification":
      return (
        <section aria-labelledby="research-result-title">
          <h2 id="research-result-title">입력 확인이 필요합니다</h2>
          <ResearchResultDisclosure />
          <p>{result.explanation}</p>
          <ul>
            {result.choices.map((choice) => (
              <li key={choice.label}>
                <strong>{choice.label}</strong> · {choice.reason}
              </li>
            ))}
          </ul>
          <ResultTrustLinks resultId={result.result_id} version={result.rule_version} />
        </section>
      );
    case "no_match":
      return (
        <section aria-labelledby="research-result-title">
          <h2 id="research-result-title">조건 일치 항목이 없습니다</h2>
          <ResearchResultDisclosure />
          <p>{result.explanation}</p>
          <p>출처 PostgreSQL · 기준일 {result.provenance.as_of}의 조건 일치 수는 0개입니다.</p>
          <ResultTrustLinks resultId={result.result_id} version={result.rule_version} />
        </section>
      );
    case "unavailable":
      return (
        <section aria-labelledby="research-result-title">
          <h2 id="research-result-title">결과를 표시할 수 없습니다</h2>
          <ResearchResultDisclosure />
          <p>{result.explanation}</p>
          <p>{result.retryable ? "운영 데이터 상태가 확인된 뒤 다시 시도할 수 있습니다." : "현재는 다시 시도할 수 없습니다."}</p>
          <ResultTrustLinks resultId={result.result_id} version={result.rule_version} />
        </section>
      );
    case "failed":
      return (
        <section aria-labelledby="research-result-title">
          <h2 id="research-result-title">처리에 실패했습니다</h2>
          <ResearchResultDisclosure />
          <p>{result.explanation}</p>
          <p>문의 시 참조 번호: {result.support_reference}</p>
          <ResultTrustLinks resultId={result.result_id} version={result.rule_version} />
        </section>
      );
    case "dev_preview":
      return (
        <section aria-labelledby="research-result-title">
          <h2 id="research-result-title">개발 검증 미리보기</h2>
          <ResearchResultDisclosure />
          <p>{result.explanation}</p>
          <p>이 상태는 운영 데이터 결과가 아니며 공개 화면에서 사용하지 않습니다.</p>
          <ResultTrustLinks resultId={result.result_id} version={result.rule_version} />
        </section>
      );
  }
}

function ResearchResultDisclosure() {
  return (
    <p className="research-result-disclosure">
      연구 전용 결과입니다. AI가 만든 설명은 운영 데이터의 출처·기준일·검증 계약을 대신하지 않으며, 개인별 투자 판단이나 주문을 제공하지 않습니다.
    </p>
  );
}
