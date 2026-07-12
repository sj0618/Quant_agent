import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import type { DailyDigestReport } from "../../types/quantagent";

interface DailyDigestPreviewProps {
  digest: DailyDigestReport;
  onClose: () => void;
}

function formatPercent(value: number) {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

export function DailyDigestPreview({ digest, onClose }: DailyDigestPreviewProps) {
  const { header } = digest;

  return (
    <div className="digest-preview-overlay" onClick={onClose} role="presentation">
      <Card className="digest-preview" onClick={(event) => event.stopPropagation()}>
        <div className="digest-preview__head">
          <div>
            <Badge variant="dark">EMAIL PREVIEW</Badge>
            <h2>[QuantAgent] {header.reportDate} 데일리 전략 리포트</h2>
          </div>
          <button onClick={onClose} type="button">닫기 ✕</button>
        </div>

        <section className="digest-preview__section">
          <strong>QuantAgent Daily Report</strong>
          <p>{header.reportDate} 기준</p>
          <p>
            {header.userName}님이 구독 중인 전략 {header.strategyCount}개의 오늘 리포트입니다.
          </p>
        </section>

        <section className="digest-preview__section">
          <strong>오늘의 전체 요약</strong>
          <ul>
            {digest.overallSummary.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>

        <section className="digest-preview__section">
          <strong>구독 전략 요약</strong>
          <table className="digest-preview__table">
            <thead>
              <tr>
                <th>전략명</th>
                <th>오늘 신호</th>
                <th>수익률</th>
                <th>MDD</th>
                <th>Sharpe</th>
                <th>상태</th>
              </tr>
            </thead>
            <tbody>
              {digest.comparisonRows.map((row) => (
                <tr key={row.strategyId}>
                  <td>{row.name}</td>
                  <td><Badge signal={row.todaySignal}>{row.todaySignal}</Badge></td>
                  <td>{formatPercent(row.totalReturn)}</td>
                  <td>{formatPercent(row.maxDrawdown)}</td>
                  <td>{row.sharpeRatio.toFixed(2)}</td>
                  <td>{row.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="digest-preview__section">
          <strong>전략별 상세 카드</strong>
          <div className="digest-preview__cards">
            {digest.strategyCards.map((card, index) => (
              <Card className="digest-preview__card" key={card.strategyId}>
                <strong>전략 {index + 1}. {card.title}</strong>
                <p><b>오늘의 신호:</b> <Badge signal={card.todaySignal}>{card.todaySignal}</Badge></p>
                <p><b>대상 종목:</b> {card.targets.join(", ")}</p>
                <p><b>성과 요약</b></p>
                <ul>
                  <li>기간 수익률: {formatPercent(card.totalReturn)}</li>
                  <li>MDD: {formatPercent(card.maxDrawdown)}</li>
                  <li>Sharpe Ratio: {card.sharpeRatio.toFixed(2)}</li>
                  <li>승률: {(card.winRate * 100).toFixed(1)}%</li>
                  <li>거래 수: {card.tradeCount}건</li>
                </ul>
                <p><b>AI 해석</b><br />{card.aiInterpretation}</p>
                <p><b>주의사항</b><br />{card.caution}</p>
              </Card>
            ))}
          </div>
        </section>

        <section className="digest-preview__section">
          <strong>AI 종합 코멘트</strong>
          <p>{digest.aiOverallComment}</p>
        </section>

        <section className="digest-preview__section">
          <strong>{digest.marketBrief.headline}</strong>
          <ul>
            {digest.marketBrief.items.map((item) => (
              <li key={item.title}>
                <Badge variant={item.tone}>{item.source}</Badge> {item.title}
                <br />
                <small>{item.summary}</small>
              </li>
            ))}
          </ul>
          {digest.marketBrief.items.length === 0 ? <p>오늘의 시황 브리핑을 가져오지 못했습니다.</p> : null}
        </section>

        <section className="digest-preview__section">
          <strong>상세보기</strong>
          <p>웹 대시보드에서 전략별 백테스트 상세 결과를 확인할 수 있습니다.</p>
        </section>

        <footer className="digest-preview__footer">
          {digest.footer.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </footer>
      </Card>
    </div>
  );
}
