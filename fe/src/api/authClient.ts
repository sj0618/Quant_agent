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

/** How long a `/auth/me` result is trusted before the next navigation re-checks it.
 *
 * Navigation is a full page load, so without this every click paid a round-trip to the
 * auth server before anything could render. The server still owns expiry - this only
 * decides how quickly the client notices a session that died on the server side. */
const SESSION_REVALIDATE_INTERVAL_MS = 60_000;

export function isSessionRecentlyValidated(session: AuthSession | null): boolean {
  if (!session?.validatedAt) {
    return false;
  }
  const age = Date.now() - session.validatedAt;
  return age >= 0 && age < SESSION_REVALIDATE_INTERVAL_MS;
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

  const validatedSession = { ...session, user: backendSession.user, validatedAt: Date.now() };
  saveCurrentSession(validatedSession);
  return validatedSession;
}

/**
 * Adopt a server-established session when the browser has a valid HttpOnly cookie but
 * localStorage does not yet contain a cached QuantAgent session.
 *
 * This is the browser state after a successful backend callback that set the cookie
 * without first hydrating localStorage in the SPA.
 */
export async function bootstrapSessionFromCookie(): Promise<AuthSession | null> {
  const backendSession = await fetchAuthenticatedSession();
  if (!backendSession) {
    return null;
  }

  const session: AuthSession = { user: backendSession.user, validatedAt: Date.now() };
  saveCurrentSession(session);
  return session;
}

/**
 * Reconcile the login page against the live backend session before trusting any cached
 * browser identity.
 *
 * - If localStorage has a session, validate it against `/auth/me`.
 * - If localStorage is empty, bootstrap from the HttpOnly session cookie.
 * - 401/403 clears stale QuantAgent auth state via the validation path.
 * - Transient failures are surfaced to the caller instead of silently trusting cache.
 */
export async function reconcileLoginSession(): Promise<AuthSession | null> {
  const currentSession = getCurrentSession();
  return currentSession ? validateCurrentSession() : bootstrapSessionFromCookie();
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
