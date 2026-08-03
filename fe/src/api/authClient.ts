import { AUTH_ENDPOINTS, appConfig } from "../config/appConfig";
import { ROUTES } from "../config/routes";
import type { AuthSession } from "../types/auth";
import { AUTH_SESSION_STORAGE_KEY, clearUserScopedStorage } from "../utils/userScopedStorage";
import { backendRequest, clearBackendCsrfToken } from "./backendClient";

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
    throw new Error("VITE_AUTH_API_BASE_URL is required.");
  }
  return appConfig.authApiBaseUrl;
}

function buildRedirectUri() {
  return `${window.location.origin}${ROUTES.authCallback}`;
}

function assertOk(response: Response) {
  if (!response.ok) {
    throw new Error(`Backend request failed: ${response.status}`);
  }
}

async function fetchAuthenticatedSession(): Promise<AuthSession | null> {
  const response = await fetch(`${requireAuthApiBaseUrl()}${AUTH_ENDPOINTS.me}`, {
    credentials: "include",
  });

  if (response.status === 401 || response.status === 403) {
    return null;
  }

  assertOk(response);
  const payload = (await response.json()) as AuthMeResponse;
  return { user: payload.user };
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

export function clearCurrentSession() {
  clearBackendCsrfToken();
  clearUserScopedStorage();
}

export async function validateCurrentSession(): Promise<AuthSession | null> {
  const session = getCurrentSession();
  if (!session) {
    return null;
  }

  const backendSession = await fetchAuthenticatedSession();
  if (!backendSession) {
    clearCurrentSession();
    return null;
  }

  const validatedSession = { ...session, user: backendSession.user };
  saveCurrentSession(validatedSession);
  return validatedSession;
}

export async function startGoogleSignIn(returnTo: string) {
  const baseUrl = requireAuthApiBaseUrl();
  const url = new URL(`${baseUrl}${AUTH_ENDPOINTS.googleStart}`, window.location.origin);
  url.searchParams.set("redirect_uri", buildRedirectUri());
  url.searchParams.set("return_to", returnTo);

  const response = await fetch(url.toString(), { credentials: "include" });
  assertOk(response);

  const data = (await response.json()) as StartGoogleResponse;
  if (!data.authorizationUrl) {
    throw new Error("Backend did not return a Google authorizationUrl.");
  }

  window.location.assign(data.authorizationUrl);
}

export async function completeGoogleSignIn(params: URLSearchParams) {
  const code = params.get("code");
  const state = params.get("state");
  const error = params.get("error");

  if (error) {
    throw new Error(`Google sign-in was cancelled or failed: ${error}`);
  }

  if (!code) {
    throw new Error("Google callback code is missing.");
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
    throw new Error("Backend did not return an authenticated session.");
  }

  saveCurrentSession(session);
  return { session, returnTo: data.returnTo };
}

export async function signOut() {
  const session = getCurrentSession();
  try {
    if (appConfig.authApiBaseUrl && session) {
      await backendRequest<void>(AUTH_ENDPOINTS.logout, {
        method: "POST",
      });
    }
  } finally {
    clearCurrentSession();
  }
}
