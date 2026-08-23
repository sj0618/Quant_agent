import { ROUTES, trustFeedback } from "../../config/routes";

interface ResultTrustLinksProps {
  resultId: string;
  version?: string | null;
}

/**
 * Keeps the support hand-off bound to the result the reader is viewing.  The
 * trust centre deliberately owns the feedback transport: the public result
 * pages do not guess a support mailbox or send report data from the browser.
 */
export function ResultTrustLinks({ resultId, version }: ResultTrustLinksProps) {
  return (
    <p className="result-trust-links">
      <a href={ROUTES.trust}>신뢰센터</a>
      <span aria-hidden="true">·</span>
      <a href={trustFeedback(resultId, version)}>이 결과의 데이터·설명·규칙 문제 기록</a>
    </p>
  );
}
