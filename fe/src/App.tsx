import { AppPage } from "./pages/AppPage";
import { LandingPage } from "./pages/LandingPage";
import { ReportDetailPage } from "./pages/ReportDetailPage";
import { ReportsPage } from "./pages/ReportsPage";

function normalizePath(pathname: string) {
  return pathname.replace(/\/+$/, "") || "/";
}

export default function App() {
  const path = normalizePath(window.location.pathname);

  if (path === "/") {
    return <LandingPage />;
  }

  if (path === "/app") {
    return <AppPage />;
  }

  if (path === "/reports") {
    return <ReportsPage />;
  }

  if (path.startsWith("/reports/")) {
    return <ReportDetailPage id={decodeURIComponent(path.replace("/reports/", ""))} />;
  }

  return (
    <main className="not-found">
      <h1>페이지를 찾을 수 없습니다</h1>
      <p>Figma HI-FI 구현 대상 route가 아닙니다.</p>
      <a href="/">홈으로 가기</a>
    </main>
  );
}
