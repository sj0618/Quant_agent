import { AUTH_ENDPOINTS, appConfig } from "../config/appConfig";
import { ROUTES } from "../config/routes";
import type { AuthSession } from "../types/auth";
import { AUTH_SESSION_STORAGE_KEY, clearUserScopedStorage } from "../utils/userScopedStorage";

// TEMP(dev-auth-gate): test-login bypass until BE session integration ships.
const TEST_AUTH_SESSION: AuthSession = {
  user: {
    id: "local-test-user",
    name: "테스트 사용자",
    email: "test.user@quantagent.local",
    provider: "test",
  },
};

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

interface AuthMeResponse {
  user: AuthSession["user"];
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

function assertOk(response: Response) {
  if (!response.ok) {
    throw new Error(`인증 서버 응답 실패: ${response.status}`);
  }
}

export function getCurrentSession(): AuthSession | null {
  return readJson<AuthSession>(window.localStorage.getItem(AUTH_SESSION_STORAGE_KEY));
}

export function saveCurrentSession(session: AuthSession) {
  const currentSession = getCurrentSession();
  if (!currentSession || currentSession.user.id !== session.user.id) {
    clearUserScopedStorage();
  }
  window.localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(session));
}

// TEMP(dev-auth-gate): remove once BE session integration ships.
export function saveTestSession() {
  const session = {
    ...TEST_AUTH_SESSION,
    user: { ...TEST_AUTH_SESSION.user },
  };
  saveCurrentSession(session);
  return session;
}

export function clearCurrentSession() {
  clearUserScopedStorage();
}

export async function validateCurrentSession(): Promise<AuthSession | null> {
  const session = getCurrentSession();
  if (!session) {
    return null;
  }
  if (session.user.provider === "test" && appConfig.testLoginEnabled) {
    return session;
  }

  const response = await fetch(`${requireAuthApiBaseUrl()}${AUTH_ENDPOINTS.me}`, {
    credentials: "include",
  });
  if (response.status === 401 || response.status === 403) {
    clearCurrentSession();
    return null;
  }
  assertOk(response);

  const payload = (await response.json()) as AuthMeResponse;
  const validatedSession = { ...session, user: payload.user };
  saveCurrentSession(validatedSession);
  return validatedSession;
}

export async function startGoogleSignIn(returnTo: string) {
  const baseUrl = requireAuthApiBaseUrl();
  const url = new URL(`${baseUrl}${AUTH_ENDPOINTS.googleStart}`);
  url.searchParams.set("redirect_uri", buildRedirectUri());
  url.searchParams.set("return_to", returnTo);

  const response = await fetch(url.toString(), { credentials: "include" });
  assertOk(response);

  const data = (await response.json()) as StartGoogleResponse;
  if (!data.authorizationUrl) {
    throw new Error("인증 서버가 Google authorizationUrl을 반환하지 않았습니다.");
  }

  window.location.assign(data.authorizationUrl);
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
  assertOk(response);

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
  try {
    if (appConfig.authApiBaseUrl && session?.user.provider !== "test") {
      const response = await fetch(`${appConfig.authApiBaseUrl}${AUTH_ENDPOINTS.logout}`, {
        method: "POST",
        credentials: "include",
      });
      assertOk(response);
    }
  } finally {
    clearCurrentSession();
  }
}
