import { Suspense, lazy, useEffect, useState } from "react";
import { AsyncState } from "./components/common/AsyncState";
import { AppPage } from "./pages/AppPage";
import { AuthCallbackPage } from "./pages/AuthCallbackPage";
import { AuthRequiredPage } from "./pages/AuthRequiredPage";
import { EmailReportDetailPage } from "./pages/EmailReportDetailPage";
import { LandingPage } from "./pages/LandingPage";
import { LegalPage } from "./pages/LegalPage";
import { LoginPage } from "./pages/LoginPage";
import { ProfilePage } from "./pages/ProfilePage";
import { WorkspaceReportDetailPage } from "./pages/WorkspaceReportDetailPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SearchPage } from "./pages/SearchPage";
import { UnsubscribePage } from "./pages/UnsubscribePage";
import { getCurrentSession, isSessionRecentlyValidated, validateCurrentSession } from "./api/authClient";
import {
  ROUTES,
  getCurrentPathWithSearch,
  parseEmailReportDetailId,
  parseReportDetailId,
  sanitizeReturnTo,
} from "./config/routes";
import type { AuthSession } from "./types/auth";

// 이 페이지만 react-dom/server 를 끌어오기 때문에(발송용 HTML 문자열 렌더) 별도 chunk 로 떼어낸다.
// 정적 import 로 두면 실사용자 메인 번들이 190kB 커진다.
const EmailTemplatePreviewPage = lazy(() =>
  import("./pages/EmailTemplatePreviewPage").then((module) => ({ default: module.EmailTemplatePreviewPage })),
);

function normalizePath(pathname: string) {
  return pathname.replace(/\/+$/, "") || "/";
}

function isProtectedRoute(path: string) {
  return (
    path === ROUTES.app ||
    path.startsWith(`${ROUTES.app}/`) ||
    path === ROUTES.reports ||
    parseReportDetailId(path) !== null ||
    parseEmailReportDetailId(path) !== null ||
    path === ROUTES.me ||
    path === ROUTES.notifications ||
    path === ROUTES.search
  );
}

export default function App() {
  return <AppRoutes />;
}

function AppRoutes() {
  const path = normalizePath(window.location.pathname);
  const protectedRoute = isProtectedRoute(path);
  // There is no client-side router, so every navigation remounts the whole app. Blocking
  // the first paint on /auth/me meant a full-screen "세션을 확인하는 중" on every single
  // click. The cached session renders immediately and revalidation happens behind it; only
  // an actual 401 (validateCurrentSession returning null) takes the user to the login page.
  const [session, setSession] = useState<AuthSession | null>(getCurrentSession);

  useEffect(() => {
    if (!protectedRoute || !session || isSessionRecentlyValidated(session)) {
      return;
    }
    let cancelled = false;
    validateCurrentSession()
      .then((validatedSession) => {
        if (!cancelled) {
          setSession(validatedSession);
        }
      })
      .catch((error: unknown) => {
        // A network blip is not a signed-out user. Keep what is on screen and let the
        // next navigation - or the next authenticated request's own 401 - decide.
        console.warn("로그인 세션 재확인에 실패해 기존 세션을 유지합니다.", error);
      });
    return () => {
      cancelled = true;
    };
    // Only the identity matters here; re-running on every session object would loop.
  }, [protectedRoute, session?.user.id]);

  if (path === ROUTES.home) {
    return <LandingPage />;
  }

  if (path === ROUTES.login) {
    return <LoginPage returnTo={sanitizeReturnTo(new URLSearchParams(window.location.search).get("returnTo"))} />;
  }

  if (path === ROUTES.authCallback) {
    return <AuthCallbackPage />;
  }

  if (path === ROUTES.terms) {
    return <LegalPage kind="terms" />;
  }

  if (path === ROUTES.privacy) {
    return <LegalPage kind="privacy" />;
  }

  if (path === ROUTES.disclaimer) {
    return <LegalPage kind="disclaimer" />;
  }

  if (path === ROUTES.unsubscribe) {
    return <UnsubscribePage />;
  }

  if (path === ROUTES.emailTemplatePreview) {
    return (
      <Suspense fallback={<AsyncState title="이메일 템플릿을 불러오는 중입니다" tone="loading" />}>
        <EmailTemplatePreviewPage />
      </Suspense>
    );
  }

  if (protectedRoute && !session) {
    return <AuthRequiredPage returnTo={getCurrentPathWithSearch()} />;
  }

  if (path === ROUTES.app) {
    return <AppPage />;
  }

  if (path === ROUTES.me) {
    return <ProfilePage initialTab="profile" />;
  }

  if (path === ROUTES.notifications) {
    return <ProfilePage initialTab="notifications" />;
  }

  if (path === ROUTES.search) {
    return <SearchPage />;
  }

  if (path === ROUTES.reports) {
    return <ReportsPage />;
  }

  const emailReportDetailId = parseEmailReportDetailId(path);
  if (emailReportDetailId) {
    return <EmailReportDetailPage id={emailReportDetailId} />;
  }

  const reportDetailId = parseReportDetailId(path);
  if (reportDetailId) {
    return <WorkspaceReportDetailPage id={reportDetailId} />;
  }

  return (
    <main className="not-found">
      <h1>페이지를 찾을 수 없습니다</h1>
      <p>Figma HI-FI 구현 대상 route가 아닙니다.</p>
      <a href={ROUTES.home}>홈으로 가기</a>
    </main>
  );
}
