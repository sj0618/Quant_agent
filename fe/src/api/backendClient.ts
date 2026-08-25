import { AUTH_ENDPOINTS, appConfig } from "../config/appConfig";

interface BackendErrorEnvelope {
  error?: {
    code?: string;
    component?: string;
    message?: string;
    details?: unknown;
  };
}

interface BackendRequestOptions extends RequestInit {
  csrf?: boolean;
}

const CSRF_STORAGE_KEY = "quantagent.backend-csrf.v1";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class BackendApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly component?: string;
  readonly details?: unknown;

  constructor(response: Response, payload: BackendErrorEnvelope | null) {
    const error = payload?.error;
    super(error?.message || `Backend request failed: ${response.status}`);
    this.name = "BackendApiError";
    this.status = response.status;
    this.code = error?.code || "backend_request_failed";
    this.component = error?.component;
    this.details = error?.details;
  }
}

function apiUrl(path: string) {
  return `${appConfig.backendApiBaseUrl}${path}`;
}

function readCachedCsrfToken() {
  return window.sessionStorage.getItem(CSRF_STORAGE_KEY);
}

function clearCachedCsrfToken() {
  window.sessionStorage.removeItem(CSRF_STORAGE_KEY);
}

async function loadCsrfToken(forceRefresh = false) {
  if (!forceRefresh) {
    const cached = readCachedCsrfToken();
    if (cached) {
      return cached;
    }
  }

  const response = await fetch(apiUrl(AUTH_ENDPOINTS.csrf), { credentials: "include" });
  const payload = (await response.json().catch(() => null)) as ({ csrfToken?: string } & BackendErrorEnvelope) | null;
  if (!response.ok) {
    throw new BackendApiError(response, payload);
  }
  if (!payload?.csrfToken) {
    throw new Error("Backend did not return a CSRF token.");
  }
  window.sessionStorage.setItem(CSRF_STORAGE_KEY, payload.csrfToken);
  return payload.csrfToken;
}

export function clearBackendCsrfToken() {
  clearCachedCsrfToken();
}

export async function backendRequest<T>(
  path: string,
  options: BackendRequestOptions = {},
  retriedCsrf = false,
): Promise<T> {
  const { csrf = true, headers: providedHeaders, ...requestOptions } = options;
  const method = (requestOptions.method || "GET").toUpperCase();
  const headers = new Headers(providedHeaders);
  if (requestOptions.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (csrf && UNSAFE_METHODS.has(method)) {
    headers.set("X-CSRF-Token", await loadCsrfToken(retriedCsrf));
  }

  const response = await fetch(apiUrl(path), {
    ...requestOptions,
    method,
    headers,
    credentials: "include",
  });
  if (response.status === 204) {
    return undefined as T;
  }

  const payload = (await response.json().catch(() => null)) as (T & BackendErrorEnvelope) | null;
  if (!response.ok) {
    const error = new BackendApiError(response, payload);
    if (csrf && !retriedCsrf && error.code === "csrf_invalid") {
      clearCachedCsrfToken();
      return backendRequest<T>(path, options, true);
    }
    throw error;
  }
  return payload as T;
}
