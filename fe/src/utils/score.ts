export const SCORE_SCALE = 10;

export function formatScoreValue(confidence: number) {
  return (Math.round(confidence * SCORE_SCALE * SCORE_SCALE) / SCORE_SCALE).toFixed(1);
}

export function selectRecommendationConfidence(finalConfidence: number | null | undefined, strategyConfidence: number) {
  return finalConfidence ?? strategyConfidence;
}
