import { Badge } from "../components/common/Badge";
import { Card } from "../components/common/Card";
import { Footer } from "../components/layout/Footer";
import { ROUTES, withReturnTo } from "../config/routes";

export function LandingPage() {
  const reportsHref = withReturnTo(ROUTES.login, ROUTES.reports);

  return (
    <main className="landing-page">
      <nav className="landing-nav">
        <a className="brand" href={ROUTES.home}>
          <span className="brand__mark" />
          <span>QuantAgent</span>
        </a>
        <div>
          <a href="#principles">검증 원칙</a>
          <a href="#archive">리포트 보관함</a>
          <a href="#limits">이용 범위</a>
        </div>
        <a className="button button--dark" href={reportsHref}>리포트 로그인</a>
      </nav>

      <section className="hero" id="service">
        <Badge variant="dark">릴리스 검증 진행 중</Badge>
        <h1>
          수익률보다 먼저,
          <br />
          검증 근거를 <span>확인</span>합니다
        </h1>
        <p>
          QuantAgent는 전략 검증 리포트의 데이터 기준 시점, 산출식, 재현 조건과 한계를 함께 기록하는 것을 목표로 합니다.
          현재 공개 화면은 검증을 통과한 보관 리포트 열람에만 집중합니다.
        </p>
        <div className="hero__actions">
          <a className="button button--primary" href={reportsHref}>리포트 보관함 보기 →</a>
          <a className="button button--ghost" href="#limits">현재 이용 범위</a>
        </div>
        <small>새 전략 입력·분석 실행·투자 추천은 제공하지 않습니다.</small>
      </section>

      <section className="landing-section" id="principles">
        <SectionHead eyebrow="검증 원칙" title="읽을 수 있는 리포트가 아니라, 검증할 수 있는 리포트" />
        <div className="principle-grid">
          <Card>
            <Badge variant="soft">출처</Badge>
            <h3>근거와 기준 시점</h3>
            <p>데이터 출처, 관측 시점, 사용 범위가 확인되지 않으면 수치와 추천을 신뢰 가능한 결과로 표시하지 않습니다.</p>
          </Card>
          <Card>
            <Badge variant="soft">산출식</Badge>
            <h3>지표의 산출식과 단위</h3>
            <p>지표 이름만 제시하지 않고 입력값, 산출 절차, 적용 구간, 결측·비정상값 처리 원칙을 함께 검토합니다.</p>
          </Card>
          <Card>
            <Badge variant="soft">재현성</Badge>
            <h3>재현 가능한 검증</h3>
            <p>동일한 입력과 버전에서 결과를 다시 확인할 수 있는 실행 기록과 검증 증적을 릴리스 조건으로 둡니다.</p>
          </Card>
        </div>
      </section>

      <section className="landing-section landing-section--soft" id="archive">
        <SectionHead eyebrow="읽기 전용 보관함" title="검증된 기록만 보관함에서 확인하세요" description="리포트마다 최신성, 검증 범위, 제한 사항을 확인한 뒤 해석해야 합니다." />
        <Card className="sample-report-card">
          <div className="sample-report-card__head">
            <div>
              <Badge variant="dark">보관 원칙</Badge>
              <small>읽기 전용</small>
            </div>
          </div>
          <h3>새 분석을 시작하지 않는 리포트 경험</h3>
          <p>보관 리포트는 과거 기록을 확인하기 위한 화면입니다. 검증 상태가 불충분하거나 출처가 확인되지 않는 기록은 추천 행동으로 연결하지 않습니다.</p>
          <a href={reportsHref}>로그인 후 리포트 보관함 열기 →</a>
        </Card>
      </section>

      <section className="landing-section" id="limits">
        <SectionHead eyebrow="현재 제공 범위" title="현재 제공하지 않는 기능" />
        <Card>
          <ul>
            <li>자연어 전략 입력을 통한 신규 분석과 백테스트 실행</li>
            <li>개인별 투자 추천 또는 자동 주문을 유도하는 기능</li>
            <li>검증 근거가 없는 예시 성과를 실제 성과처럼 제시하는 화면</li>
          </ul>
          <p>이 제한은 부족한 결과를 정상 결과처럼 보이지 않게 하기 위한 릴리스 안전장치입니다.</p>
        </Card>
      </section>
      <Footer />
    </main>
  );
}

function SectionHead({ eyebrow, title, description }: { eyebrow: string; title: string; description?: string }) {
  return (
    <div className="section-head">
      <Badge variant="soft">{eyebrow}</Badge>
      <h2>{title}</h2>
      {description ? <p>{description}</p> : null}
    </div>
  );
}
