import assert from "node:assert/strict";
import test from "node:test";

import { countScoredSignals } from "../src/utils/signalCounts.ts";

test("active and candidate totals count the same per-ticker signals", () => {
  const counts = countScoredSignals([
    {
      id: "338220",
      ticker: "338220",
      name: "뷰노",
      sector: "",
      signal: "HOLD",
      price: "5,250원",
      rationale: "청산 조건 미충족 - 보유 유지",
      evidence: [],
      riskReasons: [],
    },
    {
      id: "432430",
      ticker: "432430",
      name: "와이랩",
      sector: "",
      signal: "HOLD",
      price: "2,065원",
      rationale: "청산 조건 미충족 - 보유 유지",
      evidence: [],
      riskReasons: [],
    },
  ]);

  assert.deepEqual(counts, { BUY: 0, HOLD: 2, DROP: 0 });
  assert.equal((counts?.BUY ?? 0) + (counts?.HOLD ?? 0) + (counts?.DROP ?? 0), 2);
});
