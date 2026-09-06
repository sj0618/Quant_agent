"""데모(시연 영상)용 리포트 이메일 실제 전송.

기존 백엔드 이메일 경로(Brevo/Resend + outbox + worker + 발신도메인 인증)는 시연에서
갖추기 무겁다. 이 모듈은 그 게이트를 우회해 **표준 SMTP로 즉시 실제 발송**한다.
전략명·고성과 지표·누적수익률 차트를 담은 HTML 본문 + 1페이지 PDF 리포트를 첨부한다.

크레덴셜은 Claude가 대신 입력하지 않는다 — 모두 환경변수에서만 읽는다:
  DEMO_SMTP_HOST         (필수)  예: smtp.gmail.com
  DEMO_SMTP_PORT         (기본 587; 465면 SSL)
  DEMO_SMTP_USER         (필수)  로그인 계정
  DEMO_SMTP_PASSWORD     (필수)  앱 비밀번호
  DEMO_SMTP_FROM         (기본 = DEMO_SMTP_USER)
  DEMO_SMTP_FROM_NAME    (기본 "QuantAgent")
  DEMO_SMTP_STARTTLS     (기본 "1"; 465 포트면 자동 SSL)
  DEMO_MAIL_TO           (요청에 recipient 없을 때 기본 수신자)
"""

from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from io import BytesIO
from typing import Any


class DemoEmailConfigError(RuntimeError):
    """SMTP 설정이 없어 실제 전송을 시작할 수 없을 때."""


@dataclass(frozen=True)
class _SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    sender: str
    sender_name: str
    use_starttls: bool
    default_to: str | None


def _smtp_config() -> _SmtpConfig:
    host = os.getenv("DEMO_SMTP_HOST", "").strip()
    user = os.getenv("DEMO_SMTP_USER", "").strip()
    password = os.getenv("DEMO_SMTP_PASSWORD", "")
    missing = [
        name
        for name, value in (
            ("DEMO_SMTP_HOST", host),
            ("DEMO_SMTP_USER", user),
            ("DEMO_SMTP_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        raise DemoEmailConfigError(
            "실제 이메일 전송을 위한 SMTP 환경변수가 없습니다: "
            + ", ".join(missing)
            + ". 예) DEMO_SMTP_HOST=smtp.gmail.com DEMO_SMTP_USER=you@gmail.com "
            "DEMO_SMTP_PASSWORD=<앱비밀번호> (필요시 DEMO_MAIL_TO 로 기본 수신자 지정)."
        )
    port = int(os.getenv("DEMO_SMTP_PORT", "587") or "587")
    sender = os.getenv("DEMO_SMTP_FROM", "").strip() or user
    starttls = os.getenv("DEMO_SMTP_STARTTLS", "1").strip().lower() not in {"0", "false", "no", "off"}
    return _SmtpConfig(
        host=host,
        port=port,
        user=user,
        password=password,
        sender=sender,
        sender_name=os.getenv("DEMO_SMTP_FROM_NAME", "QuantAgent").strip() or "QuantAgent",
        use_starttls=starttls,
        default_to=(os.getenv("DEMO_MAIL_TO", "").strip() or None),
    )


# --------------------------------------------------------------------------- #
# envelope에서 표시용 데이터 추출 (타입 객체/딕셔너리 모두 방어적으로 처리)
# --------------------------------------------------------------------------- #
def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {}


def _extract(envelope: Any) -> dict[str, Any]:
    env = _as_dict(envelope)
    payload = _as_dict(env.get("user_payload"))
    perf_public = _as_dict(payload.get("performance"))
    perf = _as_dict(perf_public.get("performance"))
    metrics = _as_dict(perf.get("metrics"))
    spec = _as_dict(env.get("strategy_spec"))
    explanation = _as_dict(perf.get("strategy_explanation"))
    benchmark = _as_dict(perf.get("benchmark"))
    title = (
        explanation.get("title")
        or spec.get("name")
        or payload.get("headline")
        or "AI 전략 리포트"
    )
    return {
        "title": title,
        "summary": explanation.get("summary") or payload.get("message") or "",
        "metrics": metrics,
        "equity_curve": perf.get("equity_curve") or [],
        "benchmark_curve": benchmark.get("cumulative_curve") or [],
        "benchmark_label": benchmark.get("label") or "벤치마크",
        "benchmark_total_return": benchmark.get("total_return"),
        "reliability": _as_dict(perf.get("reliability")),
        "trace_id": env.get("trace_id") or "",
        "holdings": [
            {"name": a.get("name"), "ticker": a.get("ticker"), "close": a.get("close")}
            for a in (payload.get("ticker_actions") or [])
        ],
    }


def _pct(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def _num(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


# --------------------------------------------------------------------------- #
# 차트 (matplotlib, Agg 백엔드 — 화면 불필요). 한글 폰트는 있으면 사용.
# --------------------------------------------------------------------------- #
def _configure_korean_font() -> bool:
    try:
        import matplotlib
        from matplotlib import font_manager
    except Exception:  # noqa: BLE001
        return False
    candidates = [
        "AppleSDGothicNeo",
        "Apple SD Gothic Neo",
        "AppleGothic",
        "Malgun Gothic",
        "NanumGothic",
        "Noto Sans CJK KR",
        "Noto Sans KR",
        "NanumBarunGothic",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return True
    matplotlib.rcParams["axes.unicode_minus"] = False
    return False


def _points(curve: list[dict[str, Any]]) -> tuple[list[str], list[float]]:
    xs: list[str] = []
    ys: list[float] = []
    for point in curve:
        p = _as_dict(point)
        try:
            ys.append(float(p["cumulative_return"]) * 100.0)
            xs.append(str(p.get("date", "")))
        except (KeyError, TypeError, ValueError):
            continue
    return xs, ys


def _equity_png(data: dict[str, Any], korean: bool) -> bytes | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001 - matplotlib 없으면 차트 없이 진행
        return None

    sx, sy = _points(data["equity_curve"])
    bx, by = _points(data["benchmark_curve"])
    if not sy:
        return None

    strat_label = "전략" if korean else "Strategy"
    bench_label = data["benchmark_label"] if korean else "Benchmark"
    ylabel = "누적수익률 (%)" if korean else "Cumulative return (%)"

    fig, ax = plt.subplots(figsize=(7.2, 3.4), dpi=150)
    ax.plot(range(len(sy)), sy, color="#2563eb", linewidth=2.4, label=strat_label)
    if by:
        ax.plot(range(len(by)), by, color="#9ca3af", linewidth=1.6, linestyle="--", label=bench_label)
    ax.axhline(0, color="#e5e7eb", linewidth=1)
    ax.set_ylabel(ylabel)
    ax.grid(True, color="#f1f5f9", linewidth=1)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    tick_idx = list(range(0, len(sx), max(1, len(sx) // 6)))
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([sx[i][:7] for i in tick_idx], fontsize=8)
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout()

    buffer = BytesIO()
    fig.savefig(buffer, format="png")
    plt.close(fig)
    return buffer.getvalue()


def _report_pdf(data: dict[str, Any], korean: bool) -> bytes | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return None

    m = data["metrics"]
    if korean:
        heading = data["title"]
        rows = [
            ("누적수익률", _pct(m.get("total_return"))),
            ("샤프 지수", _num(m.get("sharpe_ratio"))),
            ("최대낙폭(MDD)", _pct(m.get("max_drawdown"))),
            ("승률", _pct(m.get("win_rate"), 0)),
            ("표본외 샤프", _num(m.get("out_sample_sharpe"))),
            (f"{data['benchmark_label']} 수익률", _pct(data.get("benchmark_total_return"))),
        ]
        note = "과거 시뮬레이션 결과이며 미래 수익을 보장하지 않습니다."
    else:
        heading = "AI Strategy Backtest Report"
        rows = [
            ("Total Return", _pct(m.get("total_return"))),
            ("Sharpe", _num(m.get("sharpe_ratio"))),
            ("Max Drawdown", _pct(m.get("max_drawdown"))),
            ("Win Rate", _pct(m.get("win_rate"), 0)),
            ("Out-of-sample Sharpe", _num(m.get("out_sample_sharpe"))),
            ("Benchmark Return", _pct(data.get("benchmark_total_return"))),
        ]
        note = "Historical simulation. Past performance does not guarantee future results."

    fig = plt.figure(figsize=(8.27, 11.69), dpi=150)  # A4 portrait
    fig.subplots_adjust(left=0.08, right=0.92, top=0.94, bottom=0.06)

    fig.text(0.08, 0.95, "QuantAgent", fontsize=13, color="#2563eb", fontweight="bold")
    fig.text(0.08, 0.915, heading, fontsize=17, fontweight="bold", wrap=True)
    if data["summary"]:
        fig.text(0.08, 0.865, data["summary"], fontsize=9.5, color="#374151", wrap=True)

    # 지표 표
    table_ax = fig.add_axes((0.08, 0.66, 0.84, 0.16))
    table_ax.axis("off")
    table = table_ax.table(
        cellText=[[label, value] for label, value in rows],
        colLabels=(["지표", "값"] if korean else ["Metric", "Value"]),
        cellLoc="left",
        colWidths=[0.6, 0.4],
        loc="upper left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 1.6)

    # 누적수익률 차트
    chart_ax = fig.add_axes((0.08, 0.30, 0.84, 0.30))
    sx, sy = _points(data["equity_curve"])
    bx, by = _points(data["benchmark_curve"])
    if sy:
        chart_ax.plot(range(len(sy)), sy, color="#2563eb", linewidth=2.4,
                      label=("전략" if korean else "Strategy"))
        if by:
            chart_ax.plot(range(len(by)), by, color="#9ca3af", linewidth=1.6, linestyle="--",
                          label=(data["benchmark_label"] if korean else "Benchmark"))
        chart_ax.axhline(0, color="#e5e7eb", linewidth=1)
        chart_ax.set_ylabel("누적수익률 (%)" if korean else "Cumulative return (%)")
        chart_ax.grid(True, color="#f1f5f9", linewidth=1)
        chart_ax.spines["top"].set_visible(False)
        chart_ax.spines["right"].set_visible(False)
        tick_idx = list(range(0, len(sx), max(1, len(sx) // 6)))
        chart_ax.set_xticks(tick_idx)
        chart_ax.set_xticklabels([sx[i][:7] for i in tick_idx], fontsize=8)
        chart_ax.legend(loc="upper left", frameon=False, fontsize=9)

    fig.text(0.08, 0.05, note, fontsize=8, color="#9ca3af")

    buffer = BytesIO()
    fig.savefig(buffer, format="pdf")
    plt.close(fig)
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# HTML 본문
# --------------------------------------------------------------------------- #
def _metric_card(label: str, value: str, accent: str = "#111827") -> str:
    return (
        '<td style="padding:10px 14px;border:1px solid #e5e7eb;border-radius:10px;'
        'background:#f9fafb;text-align:center">'
        f'<div style="font-size:12px;color:#6b7280">{label}</div>'
        f'<div style="font-size:22px;font-weight:700;color:{accent};margin-top:4px">{value}</div>'
        "</td>"
    )


def render_html(data: dict[str, Any], chart_cid: str | None) -> str:
    m = data["metrics"]
    holdings = "".join(
        f'<li style="margin:2px 0">{h["name"]} <span style="color:#9ca3af">({h["ticker"]})</span></li>'
        for h in data["holdings"][:5]
        if h.get("name")
    )
    chart_html = (
        f'<img src="cid:{chart_cid}" alt="누적수익률" '
        'style="width:100%;max-width:620px;border:1px solid #e5e7eb;border-radius:12px;margin:8px 0"/>'
        if chart_cid
        else ""
    )
    return f"""\
<div style="font-family:'Apple SD Gothic Neo',-apple-system,'Segoe UI',sans-serif;max-width:660px;margin:0 auto;color:#111827">
  <div style="background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;padding:22px 24px;border-radius:16px 16px 0 0">
    <div style="font-size:13px;opacity:.85;letter-spacing:.04em">QUANTAGENT · 전략 백테스트 리포트</div>
    <div style="font-size:22px;font-weight:800;margin-top:6px">{data['title']}</div>
  </div>
  <div style="border:1px solid #e5e7eb;border-top:none;border-radius:0 0 16px 16px;padding:22px 24px">
    <p style="font-size:14px;line-height:1.7;color:#374151;margin:0 0 16px">{data['summary']}</p>
    <table style="width:100%;border-collapse:separate;border-spacing:8px 0"><tr>
      {_metric_card("누적수익률", _pct(m.get("total_return")), "#16a34a")}
      {_metric_card("샤프 지수", _num(m.get("sharpe_ratio")), "#2563eb")}
      {_metric_card("최대낙폭", _pct(m.get("max_drawdown")), "#111827")}
      {_metric_card("승률", _pct(m.get("win_rate"), 0), "#111827")}
    </tr></table>
    {chart_html}
    <div style="font-size:13px;color:#374151;margin-top:8px">
      <strong>오늘의 추천 종목</strong>
      <ul style="margin:6px 0 0;padding-left:18px">{holdings}</ul>
    </div>
    <p style="font-size:11px;color:#9ca3af;margin-top:18px;line-height:1.6">
      본 리포트는 과거 시뮬레이션 결과이며 미래 수익을 보장하지 않습니다.
      거래비용·세금·슬리피지 가정에 따라 실현 수익률은 달라질 수 있습니다.<br/>
      trace: {data['trace_id']}
    </p>
  </div>
</div>"""


def _plain_text(data: dict[str, Any]) -> str:
    m = data["metrics"]
    return (
        f"{data['title']}\n\n{data['summary']}\n\n"
        f"누적수익률 {_pct(m.get('total_return'))} · 샤프 {_num(m.get('sharpe_ratio'))} · "
        f"최대낙폭 {_pct(m.get('max_drawdown'))} · 승률 {_pct(m.get('win_rate'), 0)}\n\n"
        "본 리포트는 과거 시뮬레이션 결과이며 미래 수익을 보장하지 않습니다."
    )


def build_message(envelope: Any, recipient: str, sender: str, sender_name: str) -> EmailMessage:
    data = _extract(envelope)
    korean = _configure_korean_font()

    msg = EmailMessage()
    msg["Subject"] = f"[QuantAgent] {data['title']} — 백테스트 리포트"
    msg["From"] = f"{sender_name} <{sender}>"
    msg["To"] = recipient
    msg.set_content(_plain_text(data))

    chart_png = _equity_png(data, korean)
    chart_cid_token = None
    if chart_png:
        chart_cid_token = make_msgid(domain="quantagent.local")
    msg.add_alternative(
        render_html(data, chart_cid_token.strip("<>") if chart_cid_token else None),
        subtype="html",
    )
    if chart_png:
        html_part = msg.get_payload()[-1]
        html_part.add_related(chart_png, maintype="image", subtype="png", cid=chart_cid_token)

    pdf_bytes = _report_pdf(data, korean)
    if pdf_bytes:
        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename="QuantAgent_리포트.pdf",
        )
    return msg


def send_demo_report(envelope: Any, recipient: str | None = None) -> dict[str, Any]:
    """리포트 이메일을 SMTP로 실제 전송한다. 성공 시 상태 딕셔너리 반환."""

    config = _smtp_config()
    to_addr = (recipient or config.default_to or "").strip()
    if not to_addr:
        raise DemoEmailConfigError(
            "수신자 이메일이 없습니다. 요청에 recipient 를 넣거나 DEMO_MAIL_TO 를 설정하세요."
        )

    msg = build_message(envelope, to_addr, config.sender, config.sender_name)

    context = ssl.create_default_context()
    if config.port == 465:
        with smtplib.SMTP_SSL(config.host, config.port, context=context, timeout=30) as server:
            server.login(config.user, config.password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(config.host, config.port, timeout=30) as server:
            server.ehlo()
            if config.use_starttls:
                server.starttls(context=context)
                server.ehlo()
            server.login(config.user, config.password)
            server.send_message(msg)

    return {
        "status": "sent",
        "recipient": to_addr,
        "message_id": msg["Message-Id"] or msg.get("Message-ID") or "",
        "has_pdf": True,
    }


def _demo() -> None:
    """전송 없이 렌더링만 점검 (SMTP 불필요)."""

    from ai_graph.demo_mock import build_demo_mock_envelope

    env = build_demo_mock_envelope("거래량 기반 퀀트 전략", "trace-demo")
    data = _extract(env)
    assert data["title"].startswith("거래량 급증"), data["title"]
    assert data["metrics"]["total_return"] == 1.63
    korean = _configure_korean_font()
    html = render_html(data, "chartcid")
    assert "누적수익률" in html and "cid:chartcid" in html
    msg = build_message(env, "to@example.com", "from@example.com", "QuantAgent")
    assert msg["To"] == "to@example.com"
    payloads = msg.get_payload()
    has_pdf = any(
        part.get_content_type() == "application/pdf" for part in msg.walk()
    )
    print(f"demo_email self-check OK: korean_font={korean} parts={len(payloads)} pdf_attached={has_pdf}")


if __name__ == "__main__":
    _demo()
