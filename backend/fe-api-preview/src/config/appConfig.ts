export const AUTH_ENDPOINTS = {
  googleStart: "/auth/google/start",
  googleCallback: "/auth/google/callback",
  logout: "/auth/logout",
} as const;

function trimTrailingSlash(value: string | undefined) {
  return value ? value.replace(/\/+$/, "") : "";
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
  authApiBaseUrl: authApiBaseUrl(),
} as const;
