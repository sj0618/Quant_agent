import { useMemo, useState } from "react";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { Footer } from "../components/layout/Footer";
import { ROUTES } from "../config/routes";
import { dailyDigestEmailSubject, renderDailyDigestEmailHtml } from "../features/reports/DailyDigestEmail";
import { dailyDigestReport } from "../mocks/dailyDigest.mock";

// 구성안 7개 섹션 ↔ 실제 렌더 소스 대조표. BE가 빠진 섹션 없이 포팅했는지 확인하는 용도라
// 템플릿을 고칠 때 이 목록도 같이 갱신해야 한다.
const SECTION_MAP = [
  { no: "—", title: "Header", source: "header.reportDate / userName / strategyCount" },
  { no: "01", title: "오늘의 전체 요약 + AI 종합 코멘트", source: "overallSummary[] / aiOverallComment" },
  { no: "02", title: "오늘의 시황 및 경제 기사", source: "marketBrief.headline / items[]" },
  { no: "03", title: "구독 전략 요약", source: "comparisonRows[]" },
  { no: "04", title: "전략별 상세 카드", source: "strategyCards[]" },
  { no: "05", title: "상세보기 링크", source: "baseUrl + /reports, /app" },
  { no: "—", title: "Footer", source: "footer[] + 수신거부 / 알림설정" },
];

export function EmailTemplatePreviewPage() {
  const [status, setStatus] = useState<string | null>(null);
  const digest = dailyDigestReport;
  // 미리보기도 발송용과 같은 HTML을 iframe에 넣는다. 앱 CSS가 새지 않고, 여기서 보이는 게
  // 실제 메일 본문과 동일하다는 게 보장된다.
  const html = useMemo(() => renderDailyDigestEmailHtml({ digest, baseUrl: window.location.origin }), [digest]);
  const subject = dailyDigestEmailSubject(digest);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(html);
      setStatus("이메일 HTML을 클립보드에 복사했습니다.");
    } catch {
      setStatus("클립보드 복사에 실패했습니다. HTML 다운로드를 사용하세요.");
    }
  };

  const handleDownload = () => {
    const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "daily-digest.email.html";
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus("daily-digest.email.html 파일을 내려받았습니다.");
  };

  return (
    <main className="landing-page">
      <nav className="landing-nav">
        <a className="brand" href={ROUTES.home}>
          <span className="brand__mark" />
          <span>QuantAgent</span>
        </a>
      </nav>
      <section className="legal-page email-template-page">
        <Badge variant="dark">BE HANDOFF · MOCK</Badge>
        <h1>데일리 다이제스트 이메일 템플릿</h1>
        <p>
          아래 미리보기는 <code>fe/src/features/reports/DailyDigestEmail.tsx</code>의{" "}
          <code>&lt;DailyDigestEmail /&gt;</code>를 <code>renderToStaticMarkup</code>으로 뽑은 이메일 HTML이고, 데이터는{" "}
          <code>fe/src/mocks/dailyDigest.mock.ts</code>의 mock입니다. BE는{" "}
          <code>POST /ai/daily-digest</code>가 돌려주는 <code>DailyDigestReport</code>를 같은 모양으로 넣으면 됩니다.
        </p>

        <Card className="auth-panel email-template-panel">
          <dl className="email-template-meta">
            <div>
              <dt>Subject</dt>
              <dd>{subject}</dd>
            </div>
            <div>
              <dt>Preheader</dt>
              <dd>{digest.overallSummary[0]}</dd>
            </div>
            <div>
              <dt>발송 기준 (mock)</dt>
              <dd>매일 오전 8시 KST · 구독 전략 {digest.header.strategyCount}개</dd>
            </div>
          </dl>

          <div className="form-actions">
            <Button onClick={handleCopy} variant="dark">
              HTML 복사
            </Button>
            <Button onClick={handleDownload}>HTML 다운로드</Button>
          </div>
          {status ? (
            <div className="status-banner status-banner--success">
              <strong>{status}</strong>
            </div>
          ) : null}
        </Card>

        <iframe className="email-template-frame" srcDoc={html} title={`${subject} 이메일 미리보기`} />

        <Card className="auth-panel">
          <strong>구성안 대조</strong>
          <table className="email-template-sections">
            <thead>
              <tr>
                <th>구성안</th>
                <th>섹션</th>
                <th>데이터 소스</th>
              </tr>
            </thead>
            <tbody>
              {SECTION_MAP.map((item) => (
                <tr key={item.title}>
                  <td>{item.no}</td>
                  <td>{item.title}</td>
                  <td>
                    <code>{item.source}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card className="auth-panel">
          <strong>BE 연동 지점 / 미해결</strong>
          <ul className="email-template-notes">
            <li>
              <code>baseUrl</code>은 반드시 절대 주소로 넘겨야 합니다. 메일 클라이언트에는 페이지 컨텍스트가 없어 상대
              경로 링크가 조용히 깨집니다.
            </li>
            <li>
              레이아웃은 table + inline style만 씁니다. Gmail/Outlook이 <code>&lt;style&gt;</code>, flex, grid, CSS 변수를
              제거하므로 서버 템플릿으로 옮길 때도 이 제약을 유지해야 합니다.
            </li>
            <li>
              구성안의 <b>WATCH</b> 신호가 타입에 없습니다. <code>SignalType</code>은 BUY / HOLD / DROP뿐이라 mock은
              관망 전략을 <code>DROP</code>으로 넣어둔 상태인데, DROP은 매도라 의미가 다릅니다. AI 응답 스키마에 WATCH를
              추가할지 결정이 필요합니다.
            </li>
            <li>
              제목의 날짜는 <code>2026-06-29</code> 형식이고 본문 <code>header.reportDate</code>는{" "}
              <code>2026년 6월 29일</code> 형식입니다. 현재는 본문 값을 파싱해 변환하니, BE가 ISO 날짜를 따로 들고 있다면{" "}
              <code>subjectDate</code>로 넘기는 편이 안전합니다.
            </li>
            <li>
              <code>marketBrief.items</code>가 비면 시황 섹션만 안내 문구로 대체되고 나머지 섹션은 그대로 렌더됩니다
              (AOAI web search 미설정/실패 대응).
            </li>
            <li>
              다이제스트 발송 요구사항 전체는 <code>ai/docs/email-digest-be-requirements.md</code>를 따릅니다.
            </li>
          </ul>
        </Card>
      </section>
      <Footer />
    </main>
  );
}
