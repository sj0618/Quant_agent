import { useEffect, useState } from "react";
import { backendRequest } from "../../api/backendClient";
import { MARKET_INSTRUMENTS, formatMarketQuote, type MarketTickerResponse } from "../../utils/marketTicker";

export function MarketTicker() {
  const [data, setData] = useState<MarketTickerResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const result = await backendRequest<MarketTickerResponse>("/market-ticker", {
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(12_000)]),
        });
        if (!controller.signal.aborted) setData(result);
      } catch {
        if (!controller.signal.aborted) setData(null);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          timer = setTimeout(refresh, 60_000);
        }
      }
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, []);

  return (
    <aside className="market-ticker" aria-label="주요 시장 시세">
      <div className="market-ticker__label"><strong>시장 현황</strong><small>지연 가능</small></div>
      <div className="market-ticker__scroll" role="region" aria-label="시장 시세 목록, 좌우로 스크롤할 수 있습니다" tabIndex={0}>
        <ul>
          {MARKET_INSTRUMENTS.map(([symbol, name]) => {
            const quote = formatMarketQuote(data?.quotes?.find((item) => item.symbol === symbol));
            return (
              <li key={symbol} title={quote?.detail}>
                <span className="market-ticker__name">{name}</span>
                <strong>{quote?.price ?? "—"}</strong>
                {quote ? (
                  <span className={`market-ticker__change market-ticker__change--${quote.direction}`}>
                    {quote.change}<span className="sr-only"> · {quote.detail}</span>
                  </span>
                ) : <span className="market-ticker__unavailable">{loading ? "조회 중" : "조회 불가"}</span>}
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}
