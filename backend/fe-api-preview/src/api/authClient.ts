import { AUTH_ENDPOINTS, appConfig } from "../config/appConfig";
import { ROUTES } from "../config/routes";
import type { AuthSession } from "../types/auth";

const AUTH_SESSION_STORAGE_KEY = "quantagent.auth.session.v1";

interface StartGoogleResponse {
  authorizationUrl?: string;
}

interface CallbackResponse {
  session?: AuthSession;
  user?: AuthSession["user"];
  accessToken?: string;
  expiresAt?: string;
  returnTo?: string;
}

interface MeResponse {
  user?: AuthSession["user"];
  session?: AuthSession;
}

type CompletedGoogleSignIn = {
  session: AuthSession;
  returnTo?: string;
};

const googleCallbackRequests = new Map<string, Promise<CompletedGoogleSignIn>>();

interface BackendErrorResponse {
  error?: {
    component?: string;
    code?: string;
    message?: string;
    details?: unknown;
  };
}

function readJson<T>(value: string | null): T | null {
  if (!value) {
    return null;
  }

  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

function requireAuthApiBaseUrl() {
  if (!appConfig.authApiBaseUrl) {
    throw new Error("VITE_AUTH_API_BASE_URL 설정이 필요합니다.");
  }
  return appConfig.authApiBaseUrl;
}

function buildRedirectUri() {
  return `${window.location.origin}${ROUTES.authCallback}`;
}

async function assertOk(response: Response) {
  if (!response.ok) {
    let backendError: BackendErrorResponse | null = null;
    try {
      backendError = (await response.json()) as BackendErrorResponse;
    } catch {
      backendError = null;
    }

    const error = backendError?.error;
    if (error?.message) {
      const code = error.code ? ` (${error.code})` : "";
      throw new Error(`${error.message}${code}`);
    }
    throw new Error(`인증 서버 응답 실패: ${response.status}`);
  }
}

export function getCurrentSession(): AuthSession | null {
  const session = readJson<AuthSession>(window.localStorage.getItem(AUTH_SESSION_STORAGE_KEY));
  if (session?.user?.provider !== "google") {
    clearCurrentSession();
    return null;
  }
  return session;
}

export function saveCurrentSession(session: AuthSession) {
  window.localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(session));
}

export function clearCurrentSession() {
  window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
}

export async function startGoogleSignIn(returnTo: string) {
  const baseUrl = requireAuthApiBaseUrl();
  const url = new URL(`${baseUrl}${AUTH_ENDPOINTS.googleStart}`);
  url.searchParams.set("redirect_uri", buildRedirectUri());
  url.searchParams.set("return_to", returnTo);

  const response = await fetch(url.toString(), { credentials: "include" });
  await assertOk(response);

  const data = (await response.json()) as StartGoogleResponse;
  if (!data.authorizationUrl) {
    throw new Error("인증 서버가 Google authorizationUrl을 반환하지 않았습니다.");
  }

  window.location.assign(data.authorizationUrl);
}

export async function fetchCurrentSession(): Promise<AuthSession | null> {
  const baseUrl = requireAuthApiBaseUrl();
  const response = await fetch(`${baseUrl}/auth/me`, {
    credentials: "include",
  });
  if (response.status === 401) {
    clearCurrentSession();
    return null;
  }
  await assertOk(response);

  const data = (await response.json()) as MeResponse;
  const session = data.session ?? (data.user ? { user: data.user } : null);
  if (!session) {
    clearCurrentSession();
    return null;
  }
  saveCurrentSession(session);
  return session;
}

export async function completeGoogleSignIn(params: URLSearchParams) {
  const code = params.get("code");
  const state = params.get("state");
  const error = params.get("error");

  if (error) {
    throw new Error(`Google 로그인이 취소되었거나 실패했습니다: ${error}`);
  }

  if (!code) {
    throw new Error("Google callback code가 없습니다.");
  }
  if (!state) {
    throw new Error("Google callback state가 없습니다.");
  }

  const callbackKey = `${state}:${code}`;
  const existingRequest = googleCallbackRequests.get(callbackKey);
  if (existingRequest) {
    return existingRequest;
  }

  const request = completeGoogleSignInRequest({ code, state });
  googleCallbackRequests.set(callbackKey, request);
  request.catch(() => {
    googleCallbackRequests.delete(callbackKey);
  });
  return request;
}

async function completeGoogleSignInRequest({ code, state }: { code: string; state: string }): Promise<CompletedGoogleSignIn> {
  const baseUrl = requireAuthApiBaseUrl();
  const response = await fetch(`${baseUrl}${AUTH_ENDPOINTS.googleCallback}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code,
      state,
      redirectUri: buildRedirectUri(),
    }),
  });
  await assertOk(response);

  const data = (await response.json()) as CallbackResponse;
  const session = data.session ?? (data.user ? { user: data.user, accessToken: data.accessToken, expiresAt: data.expiresAt } : null);
  if (!session) {
    throw new Error("인증 서버가 세션 정보를 반환하지 않았습니다.");
  }

  saveCurrentSession(session);
  return { session, returnTo: data.returnTo };
}

export async function signOut() {
  const session = getCurrentSession();
  if (appConfig.authApiBaseUrl && session?.user.provider === "google") {
    const response = await fetch(`${appConfig.authApiBaseUrl}${AUTH_ENDPOINTS.logout}`, {
      method: "POST",
      credentials: "include",
    });
    await assertOk(response);
  }
  clearCurrentSession();
}
