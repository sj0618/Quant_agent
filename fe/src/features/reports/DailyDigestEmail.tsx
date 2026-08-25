import type { CSSProperties, ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type {
  DailyDigestMarketBriefItem,
  DailyDigestReport,
  DailyDigestStrategyCard,
  SignalType,
  Tone,
} from "../../types/quantagent";
import { renderEmphasis, stripEmphasis } from "../../utils/emphasis";

// 발송용 이메일 본문. Gmail/Outlook/Naver가 <style> 블록, flex, grid, CSS 변수를 지우기 때문에
// 앱 컴포넌트와 달리 className 대신 table 레이아웃 + inline style만 쓰고, styles/tokens.ts 값도
// CSS 변수가 아니라 hex 리터럴로 복제한다.
//
// 섹션 순서: Header → 01 오늘의 전체 요약(AI 종합 코멘트 포함) → 02 시황 및 경제 기사
//          → 03 구독 전략 요약 → 04 전략별 상세 카드 → 05 상세보기 → Footer.
// 요약과 시황이 앞에 오는 이유는 메일을 열자마자 "오늘 뭘 봐야 하는지"가 먼저 보여야 하기
// 때문이고, 전략 단위 숫자는 그 뒤에 온다.
//
// 폰트는 앱보다 크게 잡는다. 메일 클라이언트는 본문을 축소해 보여주는 경우가 많고, 모바일 앱은
// 14px 미만 본문에 자동 확대를 걸어 레이아웃을 틀어놓는다.

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
  paragraph: { margin: 0, color: COLORS.muted, fontSize: "15px", lineHeight: 1.8 },
  sectionCell: { padding: "26px 30px", borderBottom: `1px solid ${COLORS.line}` },
  sectionTitle: { color: COLORS.ink, fontSize: "16px", fontWeight: 800, paddingBottom: "14px" },
  sectionIndex: { color: COLORS.subdued, paddingRight: "7px" },
  label: { color: COLORS.subdued, fontSize: "13px", fontWeight: 700, padding: "4px 0" },
  cardLabel: { color: COLORS.ink, fontSize: "14px", fontWeight: 800, paddingTop: "18px" },
  outlinedBox: { border: `1px solid ${COLORS.line}`, borderRadius: "10px" },
  empty: { margin: 0, color: COLORS.subdued, fontSize: "14px", lineHeight: 1.8 },
  footerLine: { color: COLORS.muted, fontSize: "13px", lineHeight: 1.9 },
  footerLink: { color: COLORS.muted, textDecoration: "underline" },
  strong: { color: COLORS.ink, fontWeight: 800 },
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
        {stripEmphasis(preheader ?? digest.overallSummary[0] ?? "")}
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
                  <Section index="01" title="오늘의 전체 요약">
                    <SummaryList lines={digest.overallSummary} />
                    <OverallComment comment={digest.aiOverallComment} />
                  </Section>
                  <Section index="02" title="오늘의 시황 및 경제 기사">
                    <MarketBrief brief={digest.marketBrief} />
                  </Section>
                  <Section index="03" title="구독 전략 요약">
                    <ComparisonTable digest={digest} />
                  </Section>
                  <Section index="04" title="전략별 상세 카드">
                    <StrategyCards cards={digest.strategyCards} />
                  </Section>
                  <Section index="05" title="상세보기">
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
      <td style={{ padding: "32px 30px 26px", borderBottom: `1px solid ${COLORS.line}` }}>
        <EmailBadge tone="dark">DAILY REPORT</EmailBadge>
        <h1 style={{ margin: "16px 0 8px", color: COLORS.ink, fontSize: "26px", lineHeight: 1.4, fontWeight: 800 }}>
          QuantAgent Daily Report
        </h1>
        <div style={{ color: COLORS.subdued, fontSize: "14px", fontWeight: 700 }}>{header.reportDate} 기준</div>
        <p style={{ ...styles.paragraph, paddingTop: "12px" }}>
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
              width={14}
              valign="top"
              style={{ padding: "4px 8px 4px 0", color: COLORS.subdued, fontSize: "15px", lineHeight: 1.8 }}
            >
              ·
            </td>
            <td valign="top" style={{ padding: "4px 0", color: COLORS.muted, fontSize: "15px", lineHeight: 1.8 }}>
              {renderEmphasis(line, styles.strong)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function OverallComment({ comment }: { comment: string }) {
  if (!comment) {
    return null;
  }

  return (
    <table role="presentation" width="100%" cellPadding={0} cellSpacing={0} border={0} style={{ marginTop: "18px" }}>
      <tbody>
        <tr>
          <td style={{ padding: "16px 18px", background: COLORS.soft, borderRadius: "10px" }}>
            <div>
              <EmailBadge tone="dark">AI 종합 코멘트</EmailBadge>
            </div>
            <p style={{ ...styles.paragraph, paddingTop: "10px" }}>{renderEmphasis(comment, styles.strong)}</p>
          </td>
        </tr>
      </tbody>
    </table>
  );
}

function ComparisonTable({ digest }: { digest: DailyDigestReport }) {
  if (!digest.comparisonRows.length) {
    return <EmptyNote>비교할 구독 전략이 없습니다.</EmptyNote>;
  }

  const head: CSSProperties = {
    padding: "10px 6px",
    borderBottom: `1px solid ${COLORS.line}`,
    color: COLORS.subdued,
    fontSize: "12px",
    fontWeight: 800,
    textAlign: "left",
  };
  const cell: CSSProperties = {
    padding: "12px 6px",
    borderBottom: `1px solid ${COLORS.line}`,
    color: COLORS.ink,
    fontSize: "14px",
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
          style={{ ...styles.outlinedBox, marginBottom: "14px" }}
        >
          <tbody>
            <tr>
              <td style={{ padding: "18px 20px" }}>
                <div style={{ color: COLORS.ink, fontSize: "17px", fontWeight: 800, lineHeight: 1.5 }}>
                  전략 {index + 1}. {card.title}
                </div>

                <table role="presentation" width="100%" cellPadding={0} cellSpacing={0} border={0} style={{ marginTop: "12px" }}>
                  <tbody>
                    <tr>
                      <td width={84} valign="top" style={styles.label}>
                        오늘의 신호
                      </td>
                      <td valign="top" style={{ padding: "4px 0" }}>
                        <EmailBadge tone={SIGNAL_TONES[card.todaySignal]}>{card.todaySignal}</EmailBadge>
                      </td>
                    </tr>
                    <tr>
                      <td width={84} valign="top" style={styles.label}>
                        대상 종목
                      </td>
                      <td valign="top" style={{ padding: "4px 0", color: COLORS.ink, fontSize: "14px", fontWeight: 700 }}>
                        {card.targets.length ? card.targets.join(", ") : "해당 없음"}
                      </td>
                    </tr>
                  </tbody>
                </table>

                <div style={styles.cardLabel}>성과 요약</div>
                <MetricsRow card={card} />

                {/* 주의사항은 따로 박스로 빼지 않는다. 별도 섹션이면 읽고 넘기기 쉬워서,
                    AI 해석 안에서 이어 읽도록 두고 중요한 부분만 굵게 처리한다. */}
                <div style={styles.cardLabel}>AI 해석</div>
                <p style={{ ...styles.paragraph, paddingTop: "6px" }}>
                  {renderEmphasis(card.aiInterpretation, styles.strong)}
                </p>
                {card.caution ? (
                  <p style={{ ...styles.paragraph, paddingTop: "10px" }}>
                    {renderEmphasis(card.caution, styles.strong)}
                  </p>
                ) : null}
              </td>
            </tr>
          </tbody>
        </table>
      ))}
    </>
  );
}

/** 지표는 라벨 행 + 값 행의 2행 가로 배치. 세로로 쌓으면 카드가 길어져 스크롤만 늘어난다. */
function MetricsRow({ card }: { card: DailyDigestStrategyCard }) {
  const metrics = [
    { label: "기간 수익률", value: formatPercent(card.totalReturn) },
    { label: "MDD", value: formatPercent(card.maxDrawdown) },
    { label: "Sharpe", value: card.sharpeRatio.toFixed(2) },
    { label: "승률", value: `${(card.winRate * 100).toFixed(1)}%` },
    { label: "거래 수", value: `${card.tradeCount}건` },
  ];
  const columnWidth = `${(100 / metrics.length).toFixed(2)}%`;

  return (
    <table
      role="presentation"
      width="100%"
      cellPadding={0}
      cellSpacing={0}
      border={0}
      style={{ marginTop: "8px", background: COLORS.soft, borderRadius: "10px" }}
    >
      <tbody>
        <tr>
          {metrics.map((metric) => (
            <td
              key={metric.label}
              width={columnWidth}
              align="center"
              style={{ padding: "14px 4px 0", color: COLORS.subdued, fontSize: "12px", fontWeight: 700 }}
            >
              {metric.label}
            </td>
          ))}
        </tr>
        <tr>
          {metrics.map((metric) => (
            <td
              key={metric.label}
              align="center"
              style={{ padding: "4px 4px 16px", color: COLORS.ink, fontSize: "16px", fontWeight: 800 }}
            >
              {metric.value}
            </td>
          ))}
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
        <p style={{ margin: "0 0 14px", color: COLORS.ink, fontSize: "15px", fontWeight: 800, lineHeight: 1.6 }}>
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
    <table role="presentation" width="100%" cellPadding={0} cellSpacing={0} border={0} style={{ marginBottom: "10px" }}>
      <tbody>
        <tr>
          <td style={{ padding: "14px 16px", ...styles.outlinedBox }}>
            <div>
              <EmailBadge tone={item.tone}>{item.source}</EmailBadge>
              {item.publishedAt ? (
                <span style={{ color: COLORS.subdued, fontSize: "12px", paddingLeft: "8px" }}>{item.publishedAt}</span>
              ) : null}
            </div>
            <div style={{ color: COLORS.ink, fontSize: "15px", fontWeight: 700, lineHeight: 1.6, paddingTop: "8px" }}>
              {item.url ? (
                <a href={item.url} style={{ color: COLORS.ink, textDecoration: "none" }}>
                  {item.title}
                </a>
              ) : (
                item.title
              )}
            </div>
            <p style={{ ...styles.paragraph, fontSize: "14px", paddingTop: "6px" }}>{item.summary}</p>
          </td>
        </tr>
      </tbody>
    </table>
  );
}

function DetailLinks({ link }: { link: (path: string) => string }) {
  return (
    <>
      <p style={{ ...styles.paragraph, paddingBottom: "16px" }}>
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
                  padding: "13px 22px",
                  color: "#ffffff",
                  fontSize: "15px",
                  fontWeight: 800,
                  textDecoration: "none",
                }}
              >
                전략 리포트 보기 →
              </a>
            </td>
            <td style={{ paddingLeft: "12px" }}>
              <a
                href={link("/app")}
                style={{
                  display: "inline-block",
                  padding: "13px 4px",
                  color: COLORS.blue,
                  fontSize: "15px",
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
      <td style={{ padding: "26px 30px 30px", background: COLORS.soft }}>
        {digest.footer.map((line) => (
          <div key={line} style={styles.footerLine}>
            {line}
          </div>
        ))}
        <div
          style={{
            paddingTop: "16px",
            marginTop: "16px",
            borderTop: `1px solid ${COLORS.line}`,
            color: COLORS.subdued,
            fontSize: "13px",
          }}
        >
          <a href={link("/unsubscribe")} style={styles.footerLink}>
            수신 거부
          </a>
          <span style={{ padding: "0 7px" }}>·</span>
          <a href={link("/me/notifications")} style={styles.footerLink}>
            알림 설정
          </a>
          <span style={{ padding: "0 7px" }}>·</span>
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
        borderRadius: "5px",
        padding: "4px 9px",
        color: palette.color,
        background: palette.background,
        fontSize: "12px",
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
