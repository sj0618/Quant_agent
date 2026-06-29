export const AUTH_ENDPOINTS = {
  googleStart: "/auth/google/start",
  googleCallback: "/auth/google/callback",
  logout: "/auth/logout",
} as const;

export const REPORT_ACTION_ENDPOINTS = {
  resend: (id: string) => `/reports/${encodeURIComponent(id)}/resend`,
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
} as const;

function trimTrailingSlash(value: string | undefined) {
  return value ? value.replace(/\/+$/, "") : "";
}

function aiApiBaseUrl() {
  return import.meta.env.DEV ? "/ai-api" : trimTrailingSlash(import.meta.env.VITE_AI_API_BASE_URL);
}

function backendApiBaseUrl() {
  return import.meta.env.DEV ? "/backend-api" : trimTrailingSlash(import.meta.env.VITE_BACKEND_API_BASE_URL);
}

function authApiBaseUrl() {
  const configured = trimTrailingSlash(import.meta.env.VITE_AUTH_API_BASE_URL);
  if (configured) {
    return configured;
  }
  return import.meta.env.DEV ? "http://127.0.0.1:8000" : backendApiBaseUrl();
}

export const appConfig = {
  backendApiBaseUrl: backendApiBaseUrl(),
  aiApiBaseUrl: aiApiBaseUrl(),
  authApiBaseUrl: authApiBaseUrl(),
  reportActionApiBaseUrl: trimTrailingSlash(import.meta.env.VITE_REPORT_ACTION_API_BASE_URL) || backendApiBaseUrl(),
  strategyApiBaseUrl: trimTrailingSlash(import.meta.env.VITE_STRATEGY_API_BASE_URL) || backendApiBaseUrl(),
} as const;
