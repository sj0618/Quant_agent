export const ROUTES = {
  home: "/",
  app: "/app",
  login: "/login",
  authCallback: "/auth/google/callback",
  reports: "/reports",
  me: "/me",
  notifications: "/me/notifications",
  search: "/search",
  terms: "/terms",
  privacy: "/privacy",
  disclaimer: "/disclaimer",
  unsubscribe: "/unsubscribe",
  reportDetail: (id: string) => `/reports/${encodeURIComponent(id)}`,
  emailReportDetail: (id: string) => `/me/email-reports/${encodeURIComponent(id)}`,
} as const;

const RETIRED_REPORT_ROUTE_SEGMENTS = new Set(["history", "strategies"]);

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

export function parseReportDetailId(pathname: string) {
  const normalizedPath = pathname.replace(/\/+$/, "") || "/";
  if (!normalizedPath.startsWith(`${ROUTES.reports}/`)) {
    return null;
  }

  const encodedId = normalizedPath.slice(ROUTES.reports.length + 1);
  if (!encodedId || encodedId.includes("/")) {
    return null;
  }

  try {
    const reportId = decodeURIComponent(encodedId);
    if (!reportId || reportId.includes("/") || RETIRED_REPORT_ROUTE_SEGMENTS.has(reportId)) {
      return null;
    }
    return reportId;
  } catch {
    return null;
  }
}

export function parseEmailReportDetailId(pathname: string) {
  const normalizedPath = pathname.replace(/\/+$/, "") || "/";
  const prefix = `${ROUTES.me}/email-reports/`;
  if (!normalizedPath.startsWith(prefix)) {
    return null;
  }

  const encodedId = normalizedPath.slice(prefix.length);
  if (!encodedId || encodedId.includes("/")) {
    return null;
  }

  try {
    const reportId = decodeURIComponent(encodedId);
    return reportId && !reportId.includes("/") ? reportId : null;
  } catch {
    return null;
  }
}
