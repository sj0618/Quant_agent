import { Badge } from "../components/common/Badge";
import { Card } from "../components/common/Card";
import { Footer } from "../components/layout/Footer";
import { ROUTES } from "../config/routes";

type LegalPageKind = "terms" | "privacy" | "disclaimer";

const LEGAL_CONTENT: Record<LegalPageKind, { eyebrow: string; title: string; sections: Array<[string, string]> }> = {
  terms: {
    eyebrow: "TERMS",
    title: "이용약관",
    sections: [
      ["서비스 범위", "QuantAgent는 과거 데이터 기반 전략 분석, 백테스트, 리포트 발송을 제공하는 정보 도구입니다."],
      ["사용자 책임", "서비스가 제공하는 신호는 투자 권유가 아니며, 최종 투자 판단과 손익은 사용자에게 귀속됩니다."],
      ["계정 관리", "Google 계정 기반 로그인과 세션 관리는 연결된 인증 서버 정책을 따릅니다."],
    ],
  },
  privacy: {
    eyebrow: "PRIVACY",
    title: "개인정보처리방침",
    sections: [
      ["수집 항목", "로그인 이메일, 이름, 리포트 수신 설정, 서비스 이용 로그를 최소 범위로 처리합니다."],
      ["처리 목적", "인증, Daily 리포트 발송, 알림 설정 관리, 고객 지원을 위해 사용합니다."],
      ["보관 및 삭제", "수신거부 또는 계정 삭제 요청 시 관련 설정을 비활성화하고 법정 보관 기간을 제외한 데이터를 삭제합니다."],
    ],
  },
  disclaimer: {
    eyebrow: "DISCLAIMER",
    title: "면책 조항",
    sections: [
      ["투자 권유 아님", "리포트와 신호는 참고용 분석이며 특정 종목 매매를 권유하지 않습니다."],
      ["성과 보장 없음", "백테스트와 과거 성과는 미래 수익률을 보장하지 않습니다."],
      ["시장 리스크", "수수료, 세금, 슬리피지, 체결 지연, 변동성 확대에 따라 실제 결과가 달라질 수 있습니다."],
    ],
  },
};

interface LegalPageProps {
  kind: LegalPageKind;
}

export function LegalPage({ kind }: LegalPageProps) {
  const content = LEGAL_CONTENT[kind];

  return (
    <main className="landing-page">
      <nav className="landing-nav">
        <a className="brand" href={ROUTES.home}>
          <span className="brand__mark" />
          <span>QuantAgent</span>
        </a>
        <div>
          <a href={ROUTES.terms}>이용약관</a>
          <a href={ROUTES.privacy}>개인정보처리방침</a>
          <a href={ROUTES.disclaimer}>면책 조항</a>
        </div>
      </nav>
      <section className="legal-page">
        <Badge variant="dark">{content.eyebrow}</Badge>
        <h1>{content.title}</h1>
        <div className="legal-grid">
          {content.sections.map(([title, body]) => (
            <Card key={title}>
              <h2>{title}</h2>
              <p>{body}</p>
            </Card>
          ))}
        </div>
      </section>
      <Footer />
    </main>
  );
}
