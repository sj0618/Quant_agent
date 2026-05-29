import { AppPage } from "./pages/AppPage";
import { AuthCallbackPage } from "./pages/AuthCallbackPage";
import { AuthRequiredPage } from "./pages/AuthRequiredPage";
import { LandingPage } from "./pages/LandingPage";
import { LegalPage } from "./pages/LegalPage";
import { LoginPage } from "./pages/LoginPage";
import { ProfilePage } from "./pages/ProfilePage";
import { ReportDetailPage } from "./pages/ReportDetailPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SearchPage } from "./pages/SearchPage";
import { UnsubscribePage } from "./pages/UnsubscribePage";
import { getCurrentSession } from "./api/authClient";
import { ROUTES, getCurrentPathWithSearch, sanitizeReturnTo } from "./config/routes";

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
  const path = normalizePath(window.location.pathname);
  const session = getCurrentSession();

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

  if (isProtectedRoute(path) && !session) {
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
