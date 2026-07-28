import type { CSSProperties, ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type {
  DailyDigestMarketBriefItem,
  DailyDigestReport,
  DailyDigestStrategyCard,
  SignalType,
  Tone,
} from "../../types/quantagent";

// 발송용 이메일 본문. Gmail/Outlook/Naver가 <style> 블록, flex, grid, CSS 변수를 지우기 때문에
// 앱 컴포넌트와 달리 className 대신 table 레이아웃 + inline style만 쓰고, styles/tokens.ts 값도
// CSS 변수가 아니라 hex 리터럴로 복제한다. 섹션 순서는 구성안과 DailyDigestPreview.tsx를 따른다:
// Header → 전체 요약 → 전략 비교표 → 전략별 상세 카드 → AI 종합 코멘트 → 시황 → 상세보기 → Footer.

export interface DailyDigestEmailProps {
  digest: DailyDigestReport;
  /**
   * 모든 링크에 붙는 절대 주소(`https://quant-agent.example`). 메일 클라이언트에는 페이지
   * 컨텍스트가 없어 상대 경로가 조용히 깨지므로 BE는 항상 채워서 넘겨야 한다.
   */
  baseUrl?: string;
  /** 받은 편지함에서 제목 옆에 보이는 미리보기 문구. 없으면 전체 요약 첫 줄을 쓴다. */
  preheader?: string;
}

const COLORS = {
  bg: "#f8fafc",
  surface: "#ffffff",
  ink: "#0f172a",
  muted: "#475669",
  subdued: "#94a3b8",
  line: "#e2e8f0",
  soft: "#f1f5f9",
  dark: "#0b101b",
  blue: "#2563eb",
} as const;

const TONE_COLORS: Record<Tone, { color: string; background: string }> = {
  positive: { color: "#108a41", background: "#dcfcdf" },
  warning: { color: "#b4790b", background: "#fef3c7" },
  negative: { color: "#ca2b2b", background: "#fee2e2" },
  neutral: { color: COLORS.muted, background: COLORS.soft },
  info: { color: COLORS.blue, background: "#eaf0ff" },
};

const SIGNAL_TONES: Record<SignalType, Tone> = { BUY: "positive", HOLD: "warning", DROP: "negative" };

const EMAIL_FONT = "'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',Arial,sans-serif";

const styles = {
  paragraph: { margin: 0, color: COLORS.muted, fontSize: "13px", lineHeight: 1.7 },
  sectionCell: { padding: "22px 28px", borderBottom: `1px solid ${COLORS.line}` },
  sectionTitle: { color: COLORS.ink, fontSize: "13px", fontWeight: 800, paddingBottom: "12px" },
  sectionIndex: { color: COLORS.subdued, paddingRight: "6px" },
  label: { color: COLORS.subdued, fontSize: "11px", fontWeight: 700, padding: "3px 0" },
  cardLabel: { color: COLORS.ink, fontSize: "11px", fontWeight: 800, paddingTop: "14px" },
  outlinedBox: { border: `1px solid ${COLORS.line}`, borderRadius: "10px" },
  empty: { margin: 0, color: COLORS.subdued, fontSize: "12px", lineHeight: 1.7 },
  footerLine: { color: COLORS.muted, fontSize: "11px", lineHeight: 1.8 },
  footerLink: { color: COLORS.muted, textDecoration: "underline" },
} satisfies Record<string, CSSProperties>;

export function dailyDigestEmailSubject(digest: DailyDigestReport, subjectDate?: string) {
  return `[QuantAgent] ${subjectDate ?? toIsoDate(digest.header.reportDate)} 데일리 전략 리포트`;
}

/** `2026년 6월 29일` → `2026-06-29`. 형식이 다르면 그대로 통과시킨다. */
export function toIsoDate(reportDate: string) {
  const match = reportDate.match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
  if (!match) {
    return reportDate;
  }
  const [, year, month, day] = match;
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

/**
 * 발송용 HTML 문자열. 문서 껍데기(doctype/head)는 문자열로 두는데, React 19가
 * <title>/<meta>를 head로 hoist 하면서 정적 마크업 순서를 흔들기 때문이다.
 */
export function renderDailyDigestEmailHtml(props: DailyDigestEmailProps) {
  const subject = dailyDigestEmailSubject(props.digest);

  return `<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html lang="ko" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="x-apple-disable-message-reformatting" />
<meta name="color-scheme" content="light only" />
<meta name="supported-color-schemes" content="light only" />
<title>${escapeMarkup(subject)}</title>
</head>
<body style="margin:0;padding:0;background:${COLORS.bg};-webkit-text-size-adjust:100%;">
${renderToStaticMarkup(<DailyDigestEmail {...props} />)}
</body>
</html>
`;
}

export function DailyDigestEmail({ digest, baseUrl = "", preheader }: DailyDigestEmailProps) {
  const origin = baseUrl.replace(/\/+$/, "");
  const link = (path: string) => `${origin}${path}`;

  return (
    <>
      <div style={{ display: "none", maxHeight: 0, overflow: "hidden" }}>
        {preheader ?? digest.overallSummary[0] ?? ""}
      </div>
      <table role="presentation" width="100%" cellPadding={0} cellSpacing={0} border={0} style={{ background: COLORS.bg }}>
        <tbody>
          <tr>
            <td align="center" style={{ padding: "24px 12px" }}>
              <table
                role="presentation"
                width={600}
                cellPadding={0}
                cellSpacing={0}
                border={0}
                style={{
                  width: "600px",
                  maxWidth: "100%",
                  background: COLORS.surface,
                  border: `1px solid ${COLORS.line}`,
                  borderRadius: "16px",
                  overflow: "hidden",
                  fontFamily: EMAIL_FONT,
                }}
              >
                <tbody>
                  <HeaderSection digest={digest} />
                  <Section index="02" title="오늘의 전체 요약">
                    <SummaryList lines={digest.overallSummary} />
                  </Section>
                  <Section index="03" title="구독 전략 요약">
                    <ComparisonTable digest={digest} />
                  </Section>
                  <Section index="04" title="전략별 상세 카드">
                    <StrategyCards cards={digest.strategyCards} />
                  </Section>
                  <Section index="05" title="AI 종합 코멘트">
                    <p style={styles.paragraph}>{digest.aiOverallComment}</p>
                  </Section>
                  <Section index="06" title="시황 및 경제 기사">
                    <MarketBrief brief={digest.marketBrief} />
                  </Section>
                  <Section index="07" title="상세보기">
                    <DetailLinks link={link} />
                  </Section>
                  <FooterSection digest={digest} link={link} />
                </tbody>
              </table>
            </td>
          </tr>
        </tbody>
      </table>
    </>
  );
}

function HeaderSection({ digest }: { digest: DailyDigestReport }) {
  const { header } = digest;

  return (
    <tr>
      <td style={{ padding: "28px 28px 22px", borderBottom: `1px solid ${COLORS.line}` }}>
        <EmailBadge tone="dark">DAILY REPORT</EmailBadge>
        <h1 style={{ margin: "14px 0 6px", color: COLORS.ink, fontSize: "22px", lineHeight: 1.4, fontWeight: 800 }}>
          QuantAgent Daily Report
        </h1>
        <div style={{ color: COLORS.subdued, fontSize: "12px", fontWeight: 700 }}>{header.reportDate} 기준</div>
        <p style={{ ...styles.paragraph, paddingTop: "10px" }}>
          {header.userName}님이 구독 중인 전략 {header.strategyCount}개의 오늘 리포트입니다.
        </p>
      </td>
    </tr>
  );
}

function SummaryList({ lines }: { lines: string[] }) {
  if (!lines.length) {
    return <EmptyNote>오늘의 전체 요약을 생성하지 못했습니다.</EmptyNote>;
  }

  return (
    <table role="presentation" width="100%" cellPadding={0} cellSpacing={0} border={0}>
      <tbody>
        {lines.map((line) => (
          <tr key={line}>
            <td
              width={12}
              valign="top"
              style={{ padding: "3px 6px 3px 0", color: COLORS.subdued, fontSize: "13px", lineHeight: 1.7 }}
            >
              ·
            </td>
            <td valign="top" style={{ padding: "3px 0", color: COLORS.muted, fontSize: "13px", lineHeight: 1.7 }}>
              {line}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ComparisonTable({ digest }: { digest: DailyDigestReport }) {
  if (!digest.comparisonRows.length) {
    return <EmptyNote>비교할 구독 전략이 없습니다.</EmptyNote>;
  }

  const head: CSSProperties = {
    padding: "8px 6px",
    borderBottom: `1px solid ${COLORS.line}`,
    color: COLORS.subdued,
    fontSize: "10px",
    fontWeight: 800,
    textAlign: "left",
  };
  const cell: CSSProperties = {
    padding: "9px 6px",
    borderBottom: `1px solid ${COLORS.line}`,
    color: COLORS.ink,
    fontSize: "12px",
  };
  const numeric: CSSProperties = { ...cell, textAlign: "right" };

  return (
    <table role="presentation" width="100%" cellPadding={0} cellSpacing={0} border={0} style={{ borderCollapse: "collapse" }}>
      <thead>
        <tr>
          <th style={head}>전략명</th>
          <th style={head}>오늘 신호</th>
          <th style={{ ...head, textAlign: "right" }}>수익률</th>
          <th style={{ ...head, textAlign: "right" }}>MDD</th>
          <th style={{ ...head, textAlign: "right" }}>Sharpe</th>
          <th style={{ ...head, textAlign: "right" }}>상태</th>
        </tr>
      </thead>
      <tbody>
        {digest.comparisonRows.map((row) => (
          <tr key={row.strategyId}>
            <td style={{ ...cell, fontWeight: 700 }}>{row.name}</td>
            <td style={cell}>
              <EmailBadge tone={SIGNAL_TONES[row.todaySignal]}>{row.todaySignal}</EmailBadge>
            </td>
            <td style={numeric}>{formatPercent(row.totalReturn)}</td>
            <td style={numeric}>{formatPercent(row.maxDrawdown)}</td>
            <td style={numeric}>{row.sharpeRatio.toFixed(2)}</td>
            <td style={{ ...numeric, color: COLORS.muted }}>{row.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StrategyCards({ cards }: { cards: DailyDigestStrategyCard[] }) {
  if (!cards.length) {
    return <EmptyNote>전략별 상세 카드를 생성하지 못했습니다.</EmptyNote>;
  }

  return (
    <>
      {cards.map((card, index) => (
        <table
          role="presentation"
          width="100%"
          cellPadding={0}
          cellSpacing={0}
          border={0}
          key={card.strategyId}
          style={{ ...styles.outlinedBox, marginBottom: "12px" }}
        >
          <tbody>
            <tr>
              <td style={{ padding: "14px 16px" }}>
                <div style={{ color: COLORS.ink, fontSize: "14px", fontWeight: 800 }}>
                  전략 {index + 1}. {card.title}
                </div>

                <table role="presentation" width="100%" cellPadding={0} cellSpacing={0} border={0} style={{ marginTop: "10px" }}>
                  <tbody>
                    <tr>
                      <td width={80} valign="top" style={styles.label}>
                        오늘의 신호
                      </td>
                      <td valign="top" style={{ padding: "3px 0" }}>
                        <EmailBadge tone={SIGNAL_TONES[card.todaySignal]}>{card.todaySignal}</EmailBadge>
                      </td>
                    </tr>
                    <tr>
                      <td width={80} valign="top" style={styles.label}>
                        대상 종목
                      </td>
                      <td valign="top" style={{ padding: "3px 0", color: COLORS.ink, fontSize: "12px", fontWeight: 700 }}>
                        {card.targets.length ? card.targets.join(", ") : "해당 없음"}
                      </td>
                    </tr>
                  </tbody>
                </table>

                <div style={styles.cardLabel}>성과 요약</div>
                <table
                  role="presentation"
                  width="100%"
                  cellPadding={0}
                  cellSpacing={0}
                  border={0}
                  style={{ marginTop: "6px", background: COLORS.soft, borderRadius: "8px" }}
                >
                  <tbody>
                    <tr>
                      <td style={{ padding: "10px 12px" }}>
                        <MetricRow label="기간 수익률" value={formatPercent(card.totalReturn)} />
                        <MetricRow label="MDD" value={formatPercent(card.maxDrawdown)} />
                        <MetricRow label="Sharpe Ratio" value={card.sharpeRatio.toFixed(2)} />
                        <MetricRow label="승률" value={`${(card.winRate * 100).toFixed(1)}%`} />
                        <MetricRow label="거래 수" value={`${card.tradeCount}건`} />
                      </td>
                    </tr>
                  </tbody>
                </table>

                <div style={styles.cardLabel}>AI 해석</div>
                <p style={{ ...styles.paragraph, paddingTop: "4px" }}>{card.aiInterpretation}</p>

                <CautionBox>{card.caution}</CautionBox>
              </td>
            </tr>
          </tbody>
        </table>
      ))}
    </>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <table role="presentation" width="100%" cellPadding={0} cellSpacing={0} border={0}>
      <tbody>
        <tr>
          <td style={{ padding: "2px 0", color: COLORS.muted, fontSize: "12px" }}>{label}</td>
          <td align="right" style={{ padding: "2px 0", color: COLORS.ink, fontSize: "12px", fontWeight: 800 }}>
            {value}
          </td>
        </tr>
      </tbody>
    </table>
  );
}

function CautionBox({ children }: { children: ReactNode }) {
  return (
    <table role="presentation" width="100%" cellPadding={0} cellSpacing={0} border={0} style={{ marginTop: "12px" }}>
      <tbody>
        <tr>
          <td style={{ padding: "10px 12px", background: TONE_COLORS.warning.background, borderRadius: "8px" }}>
            <div>
              <EmailBadge tone="warning">주의사항</EmailBadge>
            </div>
            <p style={{ margin: "6px 0 0", color: "#7c5307", fontSize: "12px", lineHeight: 1.7 }}>{children}</p>
          </td>
        </tr>
      </tbody>
    </table>
  );
}

function MarketBrief({ brief }: { brief: DailyDigestReport["marketBrief"] }) {
  // AOAI web search가 꺼져 있거나 실패하면 AI API가 빈 배열 + fallback_reasons로 응답하므로,
  // 이 섹션만 안내 문구로 내려앉고 나머지 섹션 렌더는 막지 않는다.
  if (!brief.items.length) {
    return <EmptyNote>오늘의 시황 브리핑을 가져오지 못했습니다.</EmptyNote>;
  }

  return (
    <>
      {brief.headline ? (
        <p style={{ margin: "0 0 12px", color: COLORS.ink, fontSize: "13px", fontWeight: 800, lineHeight: 1.6 }}>
          {brief.headline}
        </p>
      ) : null}
      {brief.items.map((item) => (
        <MarketBriefRow item={item} key={item.title} />
      ))}
    </>
  );
}

function MarketBriefRow({ item }: { item: DailyDigestMarketBriefItem }) {
  return (
    <table role="presentation" width="100%" cellPadding={0} cellSpacing={0} border={0} style={{ marginBottom: "8px" }}>
      <tbody>
        <tr>
          <td style={{ padding: "10px 12px", ...styles.outlinedBox, borderRadius: "8px" }}>
            <div>
              <EmailBadge tone={item.tone}>{item.source}</EmailBadge>
              {item.publishedAt ? (
                <span style={{ color: COLORS.subdued, fontSize: "10px", paddingLeft: "6px" }}>{item.publishedAt}</span>
              ) : null}
            </div>
            <div style={{ color: COLORS.ink, fontSize: "13px", fontWeight: 700, lineHeight: 1.6, paddingTop: "6px" }}>
              {item.url ? (
                <a href={item.url} style={{ color: COLORS.ink, textDecoration: "none" }}>
                  {item.title}
                </a>
              ) : (
                item.title
              )}
            </div>
            <p style={{ ...styles.paragraph, paddingTop: "4px" }}>{item.summary}</p>
          </td>
        </tr>
      </tbody>
    </table>
  );
}

function DetailLinks({ link }: { link: (path: string) => string }) {
  return (
    <>
      <p style={{ ...styles.paragraph, paddingBottom: "14px" }}>
        웹 대시보드에서 전략별 백테스트 상세 결과를 확인할 수 있습니다.
      </p>
      <table role="presentation" cellPadding={0} cellSpacing={0} border={0}>
        <tbody>
          <tr>
            <td style={{ background: COLORS.ink, borderRadius: "8px" }}>
              <a
                href={link("/reports")}
                style={{
                  display: "inline-block",
                  padding: "11px 18px",
                  color: "#ffffff",
                  fontSize: "13px",
                  fontWeight: 800,
                  textDecoration: "none",
                }}
              >
                전략 리포트 보기 →
              </a>
            </td>
            <td style={{ paddingLeft: "10px" }}>
              <a
                href={link("/app")}
                style={{
                  display: "inline-block",
                  padding: "11px 4px",
                  color: COLORS.blue,
                  fontSize: "13px",
                  fontWeight: 700,
                  textDecoration: "none",
                }}
              >
                백테스트 상세 결과
              </a>
            </td>
          </tr>
        </tbody>
      </table>
    </>
  );
}

function FooterSection({ digest, link }: { digest: DailyDigestReport; link: (path: string) => string }) {
  return (
    <tr>
      <td style={{ padding: "22px 28px 26px", background: COLORS.soft }}>
        {digest.footer.map((line) => (
          <div key={line} style={styles.footerLine}>
            {line}
          </div>
        ))}
        <div
          style={{
            paddingTop: "14px",
            marginTop: "14px",
            borderTop: `1px solid ${COLORS.line}`,
            color: COLORS.subdued,
            fontSize: "11px",
          }}
        >
          <a href={link("/unsubscribe")} style={styles.footerLink}>
            수신 거부
          </a>
          <span style={{ padding: "0 6px" }}>·</span>
          <a href={link("/me/notifications")} style={styles.footerLink}>
            알림 설정
          </a>
          <span style={{ padding: "0 6px" }}>·</span>
          <span>© 2026 QuantAgent</span>
        </div>
      </td>
    </tr>
  );
}

function Section({ index, title, children }: { index: string; title: string; children: ReactNode }) {
  return (
    <tr>
      <td style={styles.sectionCell}>
        <div style={styles.sectionTitle}>
          <span style={styles.sectionIndex}>{index}</span>
          {title}
        </div>
        {children}
      </td>
    </tr>
  );
}

function EmptyNote({ children }: { children: ReactNode }) {
  return <p style={styles.empty}>{children}</p>;
}

function EmailBadge({ children, tone }: { children: ReactNode; tone: Tone | "dark" }) {
  const palette = tone === "dark" ? { color: "#ffffff", background: COLORS.dark } : TONE_COLORS[tone];

  return (
    <span
      style={{
        display: "inline-block",
        borderRadius: "4px",
        padding: "3px 7px",
        color: palette.color,
        background: palette.background,
        fontSize: "10px",
        fontWeight: 800,
        lineHeight: 1.4,
      }}
    >
      {children}
    </span>
  );
}

function formatPercent(value: number) {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

/** <title>은 React 밖에서 문자열로 조립하므로 직접 이스케이프한다. */
function escapeMarkup(value: string) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
