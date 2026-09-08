export const MARKET_INSTRUMENTS = [
  ["KOSPI", "코스피"],
  ["KOSDAQ", "코스닥"],
  ["NASDAQ", "나스닥"],
  ["SP500", "S&P 500"],
  ["BTC", "비트코인"],
  ["ETH", "이더리움"],
  ["USDKRW", "달러/원"],
] as const;

export interface MarketQuote {
  symbol: string;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  currency: string;
  asOf: string | null;
  source: string;
  changeBasis: string;
  status: "available" | "unavailable";
  marketStatus?: string | null;
  delayMinutes?: number | null;
}

export interface MarketTickerResponse {
  quotes: MarketQuote[];
  metadata: { source: string; asOf: string; count: number };
}

const numberFormat = new Intl.NumberFormat("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const wonFormat = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 });

export function formatMarketQuote(quote: MarketQuote | undefined) {
  if (!quote || quote.status !== "available" ||
    !["naver_finance", "upbit"].includes(quote.source) ||
    ![quote.price, quote.change, quote.changePercent].every((value) => typeof value === "number" && Number.isFinite(value)) ||
    !quote.asOf || !Number.isFinite(Date.parse(quote.asOf))) {
    return null;
  }
  const price = quote.price!;
  const change = quote.change!;
  const percent = quote.changePercent!;
  const format = quote.source === "upbit" ? wonFormat : numberFormat;
  const signed = (value: number) => `${value > 0 ? "+" : ""}${format.format(value)}`;
  const time = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(quote.asOf));
  const source = quote.source === "upbit" ? "업비트" : "네이버 금융";
  return {
    price: `${format.format(price)}${quote.currency === "KRW" ? "원" : ""}`,
    change: `${signed(change)} (${percent > 0 ? "+" : ""}${numberFormat.format(percent)}%)`,
    direction: change > 0 ? "up" : change < 0 ? "down" : "flat",
    detail: `${source} · ${time} KST 기준 · ${quote.changeBasis}${quote.marketStatus === "CLOSE" ? " · 장 마감" : ""}${quote.delayMinutes ? ` · ${quote.delayMinutes}분 지연` : ""}`,
  };
}
