export const AUTH_ENDPOINTS = {
  googleStart: "/auth/google/start",
  googleCallback: "/auth/google/callback",
  me: "/auth/me",
  csrf: "/auth/csrf",
  logout: "/auth/logout",
} as const;

export const STRATEGY_ENDPOINTS = {
  create: "/strategies",
  update: (id: string) => `/strategies/${encodeURIComponent(id)}`,
} as const;

export const AI_ENDPOINTS = {
  apiStatus: "/api-status",
  analysisJobs: "/analysis-jobs",
  analysisJob: (id: string) => `/analysis-jobs/${encodeURIComponent(id)}`,
  analysisJobCancel: (id: string) => `/analysis-jobs/${encodeURIComponent(id)}/cancel`,
  researchRuleReview: "/api/strategies/parse",
  researchJobs: "/api/research/jobs",
  researchJobResult: (id: string) => `/api/research/jobs/${encodeURIComponent(id)}/result`,
} as const;

function trimTrailingSlash(value: string | undefined) {
  return value ? value.replace(/\/+$/, "") : "";
}

function aiApiBaseUrl() {
  return import.meta.env.DEV ? "/ai-api" : trimTrailingSlash(import.meta.env.VITE_AI_API_BASE_URL) || "/ai-api";
}

function backendApiBaseUrl() {
  return trimTrailingSlash(import.meta.env.VITE_BACKEND_API_BASE_URL) || "/api/v1";
}

export const appConfig = {
  aiApiBaseUrl: aiApiBaseUrl(),
  backendApiBaseUrl: backendApiBaseUrl(),
  authApiBaseUrl: trimTrailingSlash(import.meta.env.VITE_AUTH_API_BASE_URL) || backendApiBaseUrl(),
  strategyApiBaseUrl: trimTrailingSlash(import.meta.env.VITE_STRATEGY_API_BASE_URL) || backendApiBaseUrl(),
} as const;
