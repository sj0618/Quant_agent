import assert from "node:assert/strict";
import test from "node:test";
import { formatMarketQuote, type MarketQuote } from "../src/utils/marketTicker.ts";

// Local synthetic display checks only; these values are not current market data.
test("market ticker preserves signed changes and the source timestamp, never inventing unavailable prices", () => {
  const quote: MarketQuote = {
    symbol: "KOSPI", price: 2500.12, change: -12.34, changePercent: -0.49, currency: "KRW_INDEX",
    asOf: "2026-01-02T15:30:00+09:00", source: "naver_finance", changeBasis: "전일 종가 대비", status: "available",
    marketStatus: "CLOSE", delayMinutes: 20,
  };
  assert.deepEqual(formatMarketQuote(quote), {
    price: "2,500.12", change: "-12.34 (-0.49%)", direction: "down",
    detail: "네이버 금융 · 2026. 01. 02. 15:30 KST 기준 · 전일 종가 대비 · 장 마감 · 20분 지연",
  });
  assert.equal(formatMarketQuote({ ...quote, price: 100000000, change: 2000000, changePercent: 2, source: "upbit", currency: "KRW" })?.price, "100,000,000원");
  assert.equal(formatMarketQuote({ ...quote, change: 0, changePercent: 0 })?.direction, "flat");
  assert.equal(formatMarketQuote({ ...quote, status: "unavailable" }), null);
  assert.equal(formatMarketQuote({ ...quote, price: null }), null);
  assert.equal(formatMarketQuote({ ...quote, changePercent: Number.NaN }), null);
  assert.equal(formatMarketQuote({ ...quote, asOf: "bad date" }), null);
  assert.equal(formatMarketQuote({ ...quote, source: "fixture" }), null);
  assert.equal(formatMarketQuote(undefined), null);
});
