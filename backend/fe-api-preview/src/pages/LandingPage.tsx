import { useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { Footer } from "../components/layout/Footer";
import { getLandingSample } from "../api/quantAgentClient";
import { ROUTES, withReturnTo } from "../config/routes";
import { useAsyncData } from "../hooks/useAsyncData";

export function LandingPage() {
  const { data, loading, error } = useAsyncData(getLandingSample, []);
  const [openFaqIndex, setOpenFaqIndex] = useState(0);
  const loginHref = withReturnTo(ROUTES.login, ROUTES.app);

  if (loading) {
    return <AsyncState title="랜딩 데이터를 불러오는 중입니다" tone="loading" />;
  }

  if (error || !data) {
    return <AsyncState title="랜딩 데이터를 불러오지 못했습니다" description={error?.message} tone="error" />;
  }

  return (
    <main className="landing-page">
      <nav className="landing-nav">
        <a className="brand" href={ROUTES.home}>
          <span className="brand__mark" />
          <span>QuantAgent</span>
        </a>
        <div>
          <a href="#service">서비스 소개</a>
          <a href="#how">작동 방식</a>
          <a href="#sample">샘플 리포트</a>
          <a href="#faq">FAQ</a>
        </div>
        <div>
          <a href={loginHref}>로그인</a>
          <Button onClick={() => window.location.assign(loginHref)} variant="dark">Google로 시작</Button>
        </div>
      </nav>

      <section className="hero" id="service">
        <Badge variant="dark">KOSPI200 LIVE · 매일 오전 8시 자동 분석</Badge>
        <h1>
          자연어로 입력한 전략을,
          <br />
          데이터로 <span>검증</span>
        </h1>
        <p>
          TA-Lib 150개 정형 팩터 + 애널리스트·뉴스·외국인 흐름 비정형 신호. LLM 멀티 에이전트가 매일 분석해서
          KOSPI200 추천 종목을 보내드립니다.
        </p>
        <div className="hero__actions">
          <Button onClick={() => window.location.assign(loginHref)} variant="primary">Google 계정으로 시작하기 →</Button>
          <Button onClick={() => window.location.assign(ROUTES.reportDetail("2026-04-18"))} variant="ghost">▷ 샘플 리포트 보기</Button>
        </div>
        <small>무료 · 가입 30초 · 신용카드 등록 없음</small>
        <div className="hero__stats">
          {data.heroStats.map((stat) => (
            <div key={stat.label}>
              <strong>{stat.value}</strong>
              <span>{stat.label}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section" id="how">
        <SectionHead eyebrow="HOW IT WORKS" title="전략 한 줄에서 리포트까지 자동" description="자연어로 한 문장만 입력하시면 정형화 · 백테스트 · 신호 · 리포트까지 모두 자동으로 처리됩니다." />
        <div className="step-grid">
          {data.steps.map((step) => (
            <Card key={step.label}>
              <Badge variant="dark">{step.label}</Badge>
              <h3>{step.title}</h3>
              <p>{step.description}</p>
              <pre>{step.example.join("\n")}</pre>
            </Card>
          ))}
        </div>
      </section>

      <section className="landing-section landing-section--soft" id="sample">
        <SectionHead eyebrow="SAMPLE REPORT" title="이런 리포트를 매일 받게 됩니다" description="실제 서비스 화면과 동일한 구조의 Daily Report 샘플입니다." />
        <Card className="sample-report-card">
          <div className="sample-report-card__head">
            <div>
              <Badge variant="dark">DAILY REPORT</Badge>
              <small>{data.reportPreview.date}</small>
            </div>
            <Badge variant="info">권장도 {data.reportPreview.score}</Badge>
          </div>
          <h3>{data.reportPreview.title}</h3>
          <div className="sample-market-grid">
            {data.reportPreview.market.map((item) => (
              <span key={item.label}>
                <small>{item.label}</small>
                <strong>{item.value}</strong>
              </span>
            ))}
          </div>
          <div className="sample-signal-row">
            {data.reportPreview.signals.map((signal) => (
              <span key={signal.ticker}>
                <Badge signal={signal.signal}>{signal.signal}</Badge>
                {signal.name} <small>{signal.ticker}</small>
              </span>
            ))}
          </div>
          <a href={ROUTES.reportDetail("2026-04-18")}>샘플 리포트 자세히 보기 →</a>
        </Card>
      </section>

      <section className="landing-section">
        <SectionHead eyebrow="WHY" title="기존 도구와 무엇이 다른가?" />
        <Card padded={false}>
          <table className="comparison-table landing-comparison">
            <thead>
              <tr>
                <th>비교 항목</th>
                <th>증권사 HTS</th>
                <th>Bloomberg Terminal</th>
                <th>QuantAgent</th>
              </tr>
            </thead>
            <tbody>
              {data.comparisonRows.map((row) => (
                <tr key={row.item}>
                  <td>{row.item}</td>
                  <td>{row.traditional}</td>
                  <td>{row.terminal}</td>
                  <td><strong>{row.quantAgent}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <div className="principle-grid">
          {data.principles.map((principle) => (
            <Card key={principle.label}>
              <Badge variant="soft">{principle.label}</Badge>
              <h3>{principle.title}</h3>
              <p>{principle.description}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="landing-section landing-section--soft" id="faq">
        <SectionHead eyebrow="FAQ" title="자주 묻는 질문" />
        <div className="faq-list">
          {data.faqs.map((faq, index) => (
            <Card key={faq.question} padded={false}>
              <div className="faq-question">
                <button
                  aria-controls={`faq-answer-${index}`}
                  aria-expanded={openFaqIndex === index}
                  onClick={() => setOpenFaqIndex((current) => (current === index ? -1 : index))}
                  type="button"
                >
                  <strong>{faq.question}</strong>
                  <span>{openFaqIndex === index ? "−" : "+"}</span>
                </button>
              </div>
              {openFaqIndex === index ? <p id={`faq-answer-${index}`}>{faq.answer}</p> : null}
            </Card>
          ))}
        </div>
      </section>

      <section className="landing-cta">
        <h2>
          내일 아침 8시,
          <br />
          데이터 기반 추천을 받아보세요
        </h2>
        <p>가입은 Google 로그인 30초로 끝. 신용카드도, 자산 정보도 필요 없습니다.</p>
        <Button onClick={() => window.location.assign(loginHref)} variant="primary">Google 계정으로 시작하기 →</Button>
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
