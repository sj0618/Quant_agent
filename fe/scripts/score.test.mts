import assert from "node:assert/strict";
import test from "node:test";

import { formatScoreValue, selectRecommendationConfidence } from "../src/utils/score.ts";

test("AI report scores remain numeric for filtering and detail rendering", () => {
  assert.equal(formatScoreValue(0.83), "8.3");
  assert.equal(Number(formatScoreValue(0.83)) >= 8, true);
});

test("final risk-adjusted confidence wins over strategy parsing confidence", () => {
  assert.equal(selectRecommendationConfidence(0.82, 0.87), 0.82);
  assert.equal(selectRecommendationConfidence(null, 0.87), 0.87);
});
