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
  run: (id: string) => `/strategies/${encodeURIComponent(id)}/analysis-runs`,
} as const;

export const AI_ENDPOINTS = {
  apiStatus: "/api-status",
  analysisJobs: "/analysis-jobs",
  analysisJob: (id: string) => `/analysis-jobs/${encodeURIComponent(id)}`,
  analysisJobEvents: (id: string) => `/analysis-jobs/${encodeURIComponent(id)}/events`,
  analysisJobCancel: (id: string) => `/analysis-jobs/${encodeURIComponent(id)}/cancel`,
  analysisJobResearchAppendix: (id: string) => `/analysis-jobs/${encodeURIComponent(id)}/research-appendix`,
  strategyDescriptions: "/api/strategies/descriptions",
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
  reportActionApiBaseUrl: trimTrailingSlash(import.meta.env.VITE_REPORT_ACTION_API_BASE_URL) || backendApiBaseUrl(),
  strategyApiBaseUrl: trimTrailingSlash(import.meta.env.VITE_STRATEGY_API_BASE_URL) || backendApiBaseUrl(),
} as const;
