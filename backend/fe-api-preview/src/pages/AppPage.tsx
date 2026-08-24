import { AppLayout } from "../components/layout/AppLayout";
import { ROUTES } from "../config/routes";

/** The retained preview is an archive reader, not an on-demand analysis workspace. */
export function AppPage() {
  return (
    <AppLayout active="workspace">
      <main className="reports-page">
        <section className="workspace-empty" aria-labelledby="archive-only-title">
          <h1 id="archive-only-title">새 분석은 지원하지 않습니다</h1>
          <p>검증을 마친 과거 리포트만 읽기 전용으로 확인할 수 있습니다.</p>
          <a href={ROUTES.reports}>리포트 보관함으로 이동</a>
        </section>
      </main>
    </AppLayout>
  );
}
