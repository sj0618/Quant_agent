import { ROUTES } from "../../config/routes";

export function Footer() {
  return (
    <footer className="site-footer">
      <div>
        <div className="brand">
          <span className="brand__mark" />
          <span>QuantAgent</span>
        </div>
        <p>QuantAgent는 데이터 기준 시점, 산출식, 검증 범위와 한계를 확인할 수 있는 리포트 열람 경험을 제공합니다.</p>
      </div>
      <div className="site-footer__links">
        <a href={ROUTES.terms}>이용약관</a>
        <a href={ROUTES.privacy}>개인정보처리방침</a>
        <a href={ROUTES.disclaimer}>면책 조항</a>
        <a href={ROUTES.unsubscribe}>수신 거부</a>
      </div>
      <small>본 서비스는 투자 권유가 아니며, 과거 데이터 기반 시뮬레이션입니다.</small>
    </footer>
  );
}
