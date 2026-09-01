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
  // 이메일 템플릿 확인용 예비 라우트. mock 데이터만 쓰고 로그인도 요구하지 않으므로 BE가 바로 열어볼 수 있다.
  emailTemplatePreview: "/dev/email-template",
  reportDetail: (id: string) => `/reports/${encodeURIComponent(id)}`,
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
