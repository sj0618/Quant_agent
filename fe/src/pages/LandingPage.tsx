import { Badge } from "../components/common/Badge";
import { Card } from "../components/common/Card";
import { PublicClaimDisclosure } from "../components/common/PublicClaimDisclosure";
import { Footer } from "../components/layout/Footer";
import { ROUTES, withReturnTo } from "../config/routes";

export function LandingPage() {
  const reportsHref = withReturnTo(ROUTES.login, ROUTES.reports);
  const workspaceHref = withReturnTo(ROUTES.login, ROUTES.app);
  const workspaceAccessNoteId = "workspace-access-note";
  const archiveAccessNoteId = "archive-access-note";

  return (
    <main className="landing-page">
      <nav className="landing-nav">
        <a className="brand" href={ROUTES.home}>
          <span className="brand__mark" />
          <span>QuantAgent</span>
        </a>
        <div>
          <a href="#principles">검증 원칙</a>
          <a href="#workspace">전략 검증</a>
          <a href="#archive">리포트 보관함</a>
          <a href="#limits">안전 기준</a>
        </div>
        <a aria-describedby={workspaceAccessNoteId} className="button button--dark" href={workspaceHref}>전략 분석 시작</a>
      </nav>

      <section className="hero" id="service">
        <Badge variant="dark">릴리스 검증 진행 중</Badge>
        <h1>
          수익률보다 먼저,
          <br />
          검증 근거를 <span>확인</span>합니다
        </h1>
        <p>
          QuantAgent는 자연어 전략을 실데이터 백테스트로 검증하고, 데이터 기준 시점·산출식·재현 조건·한계를 함께 설명하는 것을 목표로 합니다.
          검증 조건이 부족하면 결과를 꾸며내지 않고 이유를 알려드립니다.
        </p>
        <div className="hero__actions">
          <a aria-describedby={workspaceAccessNoteId} className="button button--primary" href={workspaceHref}>자연어 전략 분석 시작 →</a>
          <a className="button button--ghost" href="#principles">검증 원칙 보기</a>
        </div>
        <small id={workspaceAccessNoteId}>로그인 후 전략 검증 워크스페이스로 이동합니다. 실데이터 실행 준비가 안 되면 성과 수치 없이 안전하게 안내합니다.</small>
      </section>

      <section className="landing-section landing-section--soft" id="workspace">
        <SectionHead eyebrow="전략 검증" title="말로 입력하고, 근거와 한계를 함께 확인하세요" description="전략 조건을 자연어로 입력하면 서버가 검토하고 실데이터 기반 백테스트 job으로 처리합니다." />
        <Card className="sample-report-card">
          <div className="sample-report-card__head"><Badge variant="dark">CORE WORKFLOW</Badge></div>
          <h3>자연어 전략 → 실데이터 백테스트 → 자연어 리포트</h3>
          <p>기간, 데이터 기준일, 체결·비용 가정, 표본 한계가 확인된 결과만 표시합니다. 준비되지 않은 데이터나 provider 오류는 예시 성과로 바꾸지 않습니다.</p>
          <a aria-describedby={workspaceAccessNoteId} href={workspaceHref}>전략 검증 시작 →</a>
        </Card>
      </section>

      <section className="landing-section" id="principles">
        <SectionHead eyebrow="검증 원칙" title="읽을 수 있는 리포트가 아니라, 검증할 수 있는 리포트" />
        <div className="principle-grid">
          <Card>
            <Badge variant="soft">출처</Badge>
            <h3>근거와 기준 시점</h3>
            <p>데이터 출처, 관측 시점, 사용 범위가 확인되지 않으면 수치와 종목 선정을 신뢰 가능한 결과로 표시하지 않습니다.</p>
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
        <SectionHead eyebrow="읽기 전용 보관함" title="완료된 분석 기록은 보관함에서 다시 확인하세요" description="리포트마다 최신성, 검증 범위, 제한 사항을 확인한 뒤 해석해야 합니다." />
        <Card className="sample-report-card">
          <div className="sample-report-card__head">
            <div>
              <Badge variant="dark">보관 원칙</Badge>
              <small>읽기 전용</small>
            </div>
          </div>
          <h3>실행 화면과 분리된 과거 기록</h3>
          <p>보관 리포트는 과거 결과를 확인하기 위한 읽기 전용 화면입니다. 새 분석은 전략 검증 워크스페이스에서 시작합니다.</p>
          <a aria-describedby={archiveAccessNoteId} href={reportsHref}>로그인 후 리포트 보관함 열기 →</a>
          <small id={archiveAccessNoteId}>로그인 후 읽기 전용 리포트 보관함으로 이동합니다.</small>
        </Card>
      </section>

      <section className="landing-section" id="limits">
        <SectionHead eyebrow="이용 안전 기준" title="전략 분석은 제공하고, 개인화·주문은 제공하지 않습니다" />
        <Card>
          <ul>
            <li>개인 보유 종목·계좌·수량·위험성향을 전제로 한 맞춤 자문</li>
            <li>자동 주문이나 직접 거래 실행을 유도하는 기능</li>
            <li>검증 근거가 없는 예시 성과를 실제 성과처럼 제시하는 화면</li>
          </ul>
          <p>이 기준은 자연어 전략 분석과 백테스트를 막기 위한 것이 아니라, 준비되지 않은 데이터를 정상 결과처럼 보이지 않게 하기 위한 안전장치입니다.</p>
        </Card>
      </section>
      <section aria-labelledby="public-claim-title" className="landing-section landing-section--soft">
        <SectionHead eyebrow="공개 문구 기준" title="성과 수치와 검증 범위를 함께 공개합니다" />
        <Card>
          <h3 id="public-claim-title">보관 리포트의 공개 범위</h3>
          <p>랜딩에는 예시 성과 수치를 표시하지 않습니다. 전략 검증 결과와 보관 리포트에서 기준일·방법·한계를 확인해 주세요.</p>
          <PublicClaimDisclosure claimKey="landingArchiveScope" />
          <a href={ROUTES.trust}>신뢰센터에서 데이터·표시 원칙 확인 →</a>
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
