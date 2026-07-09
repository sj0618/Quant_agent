export const ROUTES = {
  home: "/",
  app: "/app",
  login: "/login",
  authCallback: "/auth/google/callback",
  reports: "/reports",
  reportsHistory: "/reports/history",
  reportStrategies: "/reports/strategies",
  me: "/me",
  notifications: "/me/notifications",
  search: "/search",
  terms: "/terms",
  privacy: "/privacy",
  disclaimer: "/disclaimer",
  unsubscribe: "/unsubscribe",
  reportDetail: (id: string) => `/reports/${encodeURIComponent(id)}`,
  strategyReportDetail: (id: string) => `/reports/strategies/${encodeURIComponent(id)}`,
} as const;

export function withReturnTo(route: string, returnTo: string) {
  const params = new URLSearchParams({ returnTo });
  return `${route}?${params.toString()}`;
}

export function getCurrentPathWithSearch() {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

export function sanitizeReturnTo(value: string | null) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return ROUTES.app;
  }
  return value;
}
