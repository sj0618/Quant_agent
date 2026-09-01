import { useEffect, useState } from "react";

import { getResearchAppendix, type ResearchAppendix } from "../../api/quantAgentClient";
import { Card } from "../../components/common/Card";
import type { AIBaseReportV2 } from "../../types/quantagent";

const APPENDIX_POLL_MS = 3_000;
const OBSERVATION_LABEL = {
  observed: "비용 반영 후 양(+) 수익 후보 관측",
  not_observed: "비용 반영 후 양(+) 수익 후보 미관측",
  inconclusive: "표본 부족으로 결론 보류",
} as const;

function formatPercent(value: number | null | undefined) {
  return value == null ? "—" : `${(value * 100).toFixed(2)}%`;
}

export function ExplorationBaseReport({
  jobId,
  report,
}: {
  jobId: string;
  report: AIBaseReportV2;
}) {
  const [appendix, setAppendix] = useState<ResearchAppendix | null>(null);

  useEffect(() => {
    let disposed = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const next = await getResearchAppendix(jobId);
        if (disposed) return;
        setAppendix(next);
        if (next.status === "pending") timer = window.setTimeout(poll, APPENDIX_POLL_MS);
      } catch {
        if (!disposed) timer = window.setTimeout(poll, APPENDIX_POLL_MS);
      }
    };
    void poll();
    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [jobId]);

  return (
    <div className="workspace-content">
      <Card>
        <h2>사전등록 후보 검증 결과</h2>
        <p>과거 미래 구간 관측: {OBSERVATION_LABEL[report.historical_observation]} · 개인별 매매 추천이 아닙니다.</p>
        <p>정책 {report.policy_version} ({report.policy_hash.slice(0, 12)}) · 롤링 워크포워드 검증 · KRX 공식 총수익 지수</p>
        <p>기본 보고서 {(report.elapsed_ms / 1_000).toFixed(1)}초 · 해석·스크리닝 SQL·Python 생성 AI 호출 0회</p>
      </Card>
      <Card padded={false}>
        <div className="table-scroll">
          <table className="comparison-table">
            <thead><tr><th>후보</th><th>상태</th><th>수익률</th><th>MDD</th><th>Sharpe</th><th>비용</th><th>표본</th></tr></thead>
            <tbody>
              {report.candidates.map((candidate) => (
                <tr key={candidate.catalog_id}>
                  <td>{candidate.title}</td>
                  <td>{candidate.status === "available" ? "검증 가능" : candidate.reason ?? "표본 부족"}</td>
                  <td>{formatPercent(candidate.total_return)}</td>
                  <td>{formatPercent(candidate.max_drawdown)}</td>
                  <td>{candidate.sharpe_ratio?.toFixed(2) ?? "—"}</td>
                  <td>{candidate.costs?.toLocaleString("ko-KR") ?? "—"}</td>
                  <td>{candidate.evaluation_session_count.toLocaleString("ko-KR")}회</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card>
        <strong>검증 가정과 한계</strong>
        <ul>{[...report.assumptions, ...report.limitations].map((item) => <li key={item}>{item}</li>)}</ul>
      </Card>
      <Card>
        <strong>추가 심층 리서치</strong>
        {!appendix || appendix.status === "pending" ? <p>기본 보고서와 분리해 근거를 조사하고 있습니다.</p> : null}
        {appendix?.status === "unavailable" ? <p>추가 리서치를 불러오지 못했습니다. 기본 보고서의 서버 계산 결과는 바뀌지 않습니다.</p> : null}
        {appendix?.status === "ready" ? (
          <>
            <p>{appendix.payload.strategy_reading}</p>
            <ul>{appendix.payload.metrics?.map((metric) => <li key={metric.name}><strong>{metric.name}</strong> · {metric.definition}</li>)}</ul>
            <p>{appendix.payload.citations?.map((citation) => <a href={citation.url} key={citation.url} rel="noreferrer" target="_blank">{citation.title}</a>)}</p>
          </>
        ) : null}
      </Card>
    </div>
  );
}
