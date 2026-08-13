import { Badge } from "../components/common/Badge";
import { Card } from "../components/common/Card";
import { AppLayout } from "../components/layout/AppLayout";
import { ROUTES } from "../config/routes";

export function AppPage() {
  return (
    <AppLayout active="reports">
      <main aria-labelledby="archive-title" className="reports-page">
        <div className="reports-page__head">
          <div>
            <Badge variant="soft">읽기 전용 보관함</Badge>
            <h1 id="archive-title">검증 리포트 보관함</h1>
            <p>새 전략 분석과 추천 생성은 현재 제공하지 않습니다. 검증 절차를 통과해 보관된 리포트만 열람할 수 있습니다.</p>
          </div>
        </div>
        <Card>
          <h2>리포트 확인 전 알아둘 점</h2>
          <p>각 리포트의 데이터 기준 시점, 산출식, 검증 범위와 한계를 확인한 뒤 해석하세요. 최신성이나 근거를 확인할 수 없는 기록은 추천으로 사용하지 않습니다.</p>
          <a className="button button--dark" href={ROUTES.reports}>리포트 보관함 열기</a>
        </Card>
      </main>
    </AppLayout>
  );
}
