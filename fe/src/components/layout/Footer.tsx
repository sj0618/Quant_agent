export function Footer() {
  return (
    <footer className="site-footer">
      <div>
        <div className="brand">
          <span className="brand__mark" />
          <span>QuantAgent</span>
        </div>
        <p>KOSPI200 LLM 퀀트 에이전트. TA-Lib 150개 지표와 10년 시계열 백테스팅을 무료로 제공합니다.</p>
      </div>
      <div className="site-footer__links">
        <span>이용약관</span>
        <span>개인정보처리방침</span>
        <span>면책 조항</span>
        <span>수신 거부</span>
      </div>
      <small>본 서비스는 투자 권유가 아니며, 과거 데이터 기반 시뮬레이션입니다.</small>
    </footer>
  );
}
