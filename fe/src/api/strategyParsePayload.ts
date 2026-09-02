/**
 * Build the one parse-review payload accepted by both sides of a rolling
 * QuantAgent deployment.
 *
 * `natural_language` is the current public name. `query` is intentionally
 * retained as an equivalent compatibility alias while a browser bundle and
 * the AI process can be deployed at different revisions.  The server treats
 * them as the same request text, never as separate strategy inputs.
 */
export function createStrategyParsePayload(query: string) {
  return {
    natural_language: query,
    query,
  };
}
