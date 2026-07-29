import { Suspense, lazy, useEffect, useState } from "react";
// TEMP(dev-auth-gate): this import and the wrapper below, remove once the product is
// ready for public access.
import { SitePasswordGate } from "./components/common/SitePasswordGate";
import { AsyncState } from "./components/common/AsyncState";
import { AppPage } from "./pages/AppPage";
import { AuthCallbackPage } from "./pages/AuthCallbackPage";
import { AuthRequiredPage } from "./pages/AuthRequiredPage";
import { LandingPage } from "./pages/LandingPage";
import { LegalPage } from "./pages/LegalPage";
import { LoginPage } from "./pages/LoginPage";
import { ProfilePage } from "./pages/ProfilePage";
import { ReportsHistoryPage } from "./pages/ReportsHistoryPage";
import { ReportDetailPage } from "./pages/ReportDetailPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SearchPage } from "./pages/SearchPage";
import { StrategyReportDetailPage } from "./pages/StrategyReportDetailPage";
import { UnsubscribePage } from "./pages/UnsubscribePage";
import { getCurrentSession, validateCurrentSession } from "./api/authClient";
import { ROUTES, getCurrentPathWithSearch, sanitizeReturnTo } from "./config/routes";
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
    path.startsWith(`${ROUTES.reports}/`) ||
    path === ROUTES.me ||
    path === ROUTES.notifications ||
    path === ROUTES.search
  );
}

export default function App() {
  return (
    <SitePasswordGate>
      <AppRoutes />
    </SitePasswordGate>
  );
}

function AppRoutes() {
  const path = normalizePath(window.location.pathname);
  const protectedRoute = isProtectedRoute(path);
  const [authState, setAuthState] = useState<{
    error: Error | null;
    loading: boolean;
    session: AuthSession | null;
  }>(() => {
    const session = getCurrentSession();
    return { error: null, loading: protectedRoute && Boolean(session), session };
  });

  useEffect(() => {
    if (!protectedRoute) {
      return;
    }
    let cancelled = false;
    validateCurrentSession()
      .then((session) => {
        if (!cancelled) {
          setAuthState({ error: null, loading: false, session });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setAuthState({
            error: error instanceof Error ? error : new Error("세션 확인에 실패했습니다."),
            loading: false,
            session: null,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [protectedRoute]);

  if (protectedRoute && authState.loading) {
    return <AsyncState title="로그인 세션을 확인하는 중입니다" tone="loading" />;
  }

  if (protectedRoute && authState.error) {
    return <AsyncState title="로그인 세션을 확인하지 못했습니다" description={authState.error.message} tone="error" />;
  }

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

  if (protectedRoute && !authState.session) {
    return <AuthRequiredPage returnTo={getCurrentPathWithSearch()} />;
  }

  if (path === ROUTES.app) {
    return <AppPage />;
  }

  if (path === ROUTES.me) {
    return <ProfilePage />;
  }

  if (path === ROUTES.notifications) {
    return <ProfilePage />;
  }

  if (path === ROUTES.search) {
    return <SearchPage />;
  }

  if (path === ROUTES.reports) {
    return <ReportsPage />;
  }

  if (path === ROUTES.reportsHistory) {
    return <ReportsHistoryPage />;
  }

  if (path.startsWith(`${ROUTES.reportStrategies}/`)) {
    return <StrategyReportDetailPage id={decodeURIComponent(path.replace(`${ROUTES.reportStrategies}/`, ""))} />;
  }

  if (path.startsWith(`${ROUTES.reports}/`)) {
    return <ReportDetailPage id={decodeURIComponent(path.replace(`${ROUTES.reports}/`, ""))} />;
  }

  return (
    <main className="not-found">
      <h1>페이지를 찾을 수 없습니다</h1>
      <p>Figma HI-FI 구현 대상 route가 아닙니다.</p>
      <a href={ROUTES.home}>홈으로 가기</a>
    </main>
  );
}
