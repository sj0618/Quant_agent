import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { isFiniteMetricValue, metricDisplay } from "../src/features/app/metricAvailability.ts";

const source = (path: string) => readFile(new URL(path, import.meta.url), "utf8");

test("fixture, stale, and non-finite metrics never render invented numbers", () => {
  const fixture = metricDisplay({
    key: "sharpe",
    label: "Sharpe",
    value: "1.42",
    tone: "positive",
    caption: "예시",
    source: "fixture",
    asOf: "2026-08-20",
    freshness: "eod_current",
  });
  const stale = metricDisplay({
    key: "return",
    label: "수익률",
    value: "+12.4%",
    tone: "positive",
    caption: "보관값",
    source: "postgres",
    asOf: "2026-08-20",
    freshness: "stale",
  });
  const nonFinite = metricDisplay({
    key: "profit_factor",
    label: "수익팩터",
    value: "NaN",
    tone: "positive",
    caption: "계산값",
    source: "postgres",
    asOf: "2026-08-20",
    freshness: "eod_current",
  });
  const nonFinitePercent = metricDisplay({
    key: "return",
    label: "수익률",
    value: "NaN%",
    tone: "positive",
    caption: "계산값",
    source: "postgres",
    asOf: "2026-08-20",
    freshness: "eod_current",
  });

  for (const display of [fixture, stale, nonFinite, nonFinitePercent]) {
    assert.equal(display.isUnavailable, true);
    assert.equal(display.value, "검증 불가");
    assert.equal(display.asOf, "2026-08-20");
    assert.ok(display.reason);
  }
  assert.equal(fixture.source, "예시 데이터");
  assert.equal(stale.source, "PostgreSQL 실데이터");
  assert.doesNotMatch(nonFinite.value, /NaN|Infinity|∞/u);
});

test("missing freshness or as-of provenance and non-finite deltas are fail-closed", () => {
  const base = {
    key: "sharpe",
    label: "Sharpe",
    value: "1.42",
    tone: "positive" as const,
    caption: "검증 구간",
    source: "postgres" as const,
  };

  for (const metric of [
    { ...base, asOf: "2026-08-20" },
    { ...base, asOf: null, freshness: "eod_current" as const },
    { ...base, asOf: "   ", freshness: "eod_current" as const },
  ]) {
    const display = metricDisplay(metric);
    assert.equal(display.isUnavailable, true);
    assert.equal(display.value, "검증 불가");
  }

  assert.equal(isFiniteMetricValue("NaN%"), false);
  assert.equal(isFiniteMetricValue("Infinity%"), false);
  assert.equal(isFiniteMetricValue("-∞"), false);
  assert.equal(isFiniteMetricValue("+12.4%"), true);
});

test("only a runtime PostgreSQL provenance value can render a current metric", () => {
  const base = {
    key: "sharpe",
    label: "Sharpe",
    value: "1.42",
    tone: "positive" as const,
    caption: "검증 구간",
    freshness: "eod_current" as const,
    asOf: "2026-08-20",
  };

  for (const source of ["api", "", "unknown"]) {
    const display = metricDisplay({
      ...base,
      source: source as unknown as "postgres",
    });
    assert.equal(display.isUnavailable, true);
    assert.equal(display.value, "검증 불가");
    assert.equal(display.source, "출처 미확인");
  }
});

test("current PostgreSQL metric retains its backend value and provenance", () => {
  const display = metricDisplay({
    key: "sharpe",
    label: "Sharpe",
    value: "1.42",
    tone: "positive",
    caption: "검증 구간",
    source: "postgres",
    asOf: "2026-08-20",
    freshness: "eod_current",
  });

  assert.equal(display.isUnavailable, false);
  assert.equal(display.value, "1.42");
  assert.equal(display.source, "PostgreSQL 실데이터");
  assert.equal(display.asOf, "2026-08-20");
});

test("metric card exposes unavailable reason, as-of, and source to readers", async () => {
  const component = await source("../src/features/app/MetricCard.tsx");

  assert.match(component, /검증 사유/);
  assert.match(component, /기준일/);
  assert.match(component, /출처/);
  assert.match(component, /metricDisplay/);
  assert.match(component, /isFiniteMetricValue\(metric\.delta\)/);
});
