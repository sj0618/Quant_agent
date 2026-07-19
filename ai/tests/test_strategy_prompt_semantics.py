"""Prompt semantics inspection script.

Not a pytest test: runs every prompt in PROMPT_CASES through the full
QuantAgent graph (mock LLM / fixture data source) and dumps what every node
produced, grouped node-by-node, as readable JSON. The final report for each
prompt is also written out as markdown.

Run directly:
    cd ai
    uv run python tests/test_strategy_prompt_semantics.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("AI_LLM_PROVIDER", "mock")
os.environ.setdefault("AI_DATABASE_DSN", "")

from ai_graph.graph import build_graph  # noqa: E402


PROMPT_CASES = [
    ("value_quality", "저PER·고ROE·부채비율 100% 이하 조건을 만족하는 가치주 중 최근 20일 수익률이 시장보다 강한 종목을 찾아줘."),
    ("breakout_volume_momentum", "최근 52주 신고가를 돌파했고 거래량이 20일 평균 대비 150% 이상 증가한 모멘텀 종목을 찾아줘."),
    ("rsi_rebound", "RSI(14)가 30 이하로 과매도된 뒤 다시 30을 상향 돌파한 반등 후보 종목을 찾아줘."),
    ("pullback_trend", "주가가 200일 이동평균선 위에 있고 20일선까지 조정받은 상승추세 눌림목 종목을 찾아줘."),
    ("earnings_momentum", "최근 3개월 EPS 컨센서스가 상향 조정되고 주가도 20일 신고가를 돌파한 실적 모멘텀 종목을 찾아줘."),
    ("dividend_defensive", "배당수익률이 4% 이상이고 최근 5년 배당 삭감이 없으며 부채비율이 낮은 배당주를 찾아줘."),
    ("quality_growth", "영업이익률과 ROE가 업종 평균보다 높고 매출 성장률도 양호한 퀄리티 성장주를 찾아줘."),
    ("bollinger_squeeze_breakout", "최근 20거래일 변동성이 낮아지고 볼린저밴드 폭이 축소된 뒤 상단을 돌파한 종목을 찾아줘."),
    ("flow_accumulation", "기관과 외국인이 최근 5거래일 연속 순매수했고 주가가 20일선 위에 있는 종목을 찾아줘."),
    ("rsi_rebound", "최근 10거래일 하락했지만 거래량은 줄고 RSI가 과매도권에 진입한 기술적 반등 후보를 찾아줘."),
    ("growth_momentum", "매출 성장률 20% 이상, 영업이익률 개선, 부채비율 100% 이하인 성장주를 찾아줘."),
    ("asset_value_catalyst", "PBR 1배 이하, 순현금 보유, 최근 자사주 매입 공시가 있는 저평가 종목을 찾아줘."),
    ("oversold_quality", "최근 60거래일 고점 대비 20% 이상 하락했지만 실적 컨센서스가 유지되는 과매도 우량주를 찾아줘."),
    ("relative_strength_leader", "시장지수보다 최근 1개월·3개월 상대강도가 모두 높은 섹터 주도주를 찾아줘."),
    ("rate_sensitive_income", "금리 하락기에 상대적으로 강했던 리츠·배당주·유틸리티 종목 중 현재 기술적 상승 신호가 있는 종목을 찾아줘."),
    ("fx_exporter_revision", "원달러 환율 상승기에 수혜를 받는 수출주 중 최근 이익 전망이 상향된 종목을 찾아줘."),
    ("margin_improvement", "원자재 가격 하락으로 마진 개선이 기대되는 소비재·화학·운송 종목을 찾아줘."),
    ("growth_momentum", "최근 3개월 매출 성장률이 업종 상위 20%이고 주가가 50일선 위에 있는 성장 모멘텀 종목을 찾아줘."),
    ("short_covering_proxy", "공매도 잔고가 높지만 최근 거래량 증가와 양봉 돌파가 나온 숏커버링 후보 종목을 찾아줘."),
    ("earnings_surprise_guidance", "최근 실적 발표에서 어닝 서프라이즈를 기록했고 다음 분기 가이던스가 상향된 종목을 찾아줘."),
    ("fcf_recovery", "현금흐름이 안정적이고 FCF 수익률이 높은 종목 중 최근 주가가 200일선 위로 회복한 종목을 찾아줘."),
    ("reasonable_growth", "ROE 15% 이상, 매출 성장률 10% 이상, PER이 업종 평균 이하인 합리적 성장주를 찾아줘."),
    ("gap_hold_momentum", "최근 5거래일 동안 갭 상승 후 갭을 메우지 않고 횡보하는 강한 수급 종목을 찾아줘."),
    ("bollinger_lower_reentry", "볼린저밴드 하단 이탈 후 종가 기준으로 밴드 안에 재진입한 단기 반등 후보를 찾아줘."),
    ("breakout_setup", "20일 이동평균 거래대금이 충분하고 최근 신고가 근처에서 거래량이 줄며 횡보하는 돌파 대기 종목을 찾아줘."),
    ("midterm_pullback", "최근 1개월 수익률은 시장보다 약했지만 6개월 수익률은 강한 중기 상승추세 눌림목 종목을 찾아줘."),
    ("margin_inventory_quality", "매출총이익률이 3개 분기 연속 개선되고 재고자산 증가율이 매출 증가율보다 낮은 종목을 찾아줘."),
    ("operating_profit_pullback", "최근 4분기 연속 영업이익이 전년 대비 증가했고 주가는 60일 고점 대비 10% 이상 조정받은 종목을 찾아줘."),
    ("low_vol_defensive", "저변동성 종목 중 최근 20일 수익률이 시장을 이기고 배당수익률도 높은 방어주를 찾아줘."),
    ("breakout_pullback", "최근 120일 신고가를 돌파한 뒤 20일선까지 되돌림이 나온 추세 지속 후보를 찾아줘."),
    ("pullback_rsi_volume", "200일선 위 상승추세를 유지하면서 RSI(14)가 40 이하로 눌리고 거래량이 20일 평균 이상인 종목을 찾아줘."),
    ("breakout_volume_momentum", "최근 52주 신고가를 돌파했고 거래량이 20일 평균 대비 150% 이상 증가한 종목을 찾아줘."),
    ("reasonable_growth", "ROE 15% 이상, 매출 성장률 10% 이상, PER이 업종 평균 이하인 합리적 성장주를 찾아줘."),
    ("relative_strength_leader", "반도체 섹터 주도주 중 상대강도 강한 종목을 찾아줘."),
    ("rsi_rebound", "반도체 섹터에서 RSI 30 이하로 과매도된 반등 후보 종목을 찾아줘."),
]

# state 키를 노드 단위로 묶어서 출력하기 위한 매핑. 여기 없는 키는 "Other"로 빠진다.
NODE_KEY_GROUPS: list[tuple[str, list[str]]] = [
    ("Supervisor", ["user_query", "trace_id", "debug_ref", "route", "internal_payload"]),
    ("Ambiguity Classifier", ["ambiguity", "status"]),
    (
        "Data",
        [
            "semantic_slots",
            "data_requirements",
            "source_usage",
            "evidence_refs",
            "freshness_status",
            "proxy_disclosure",
            "data",
            "price_rows",
            "l4_evidence",
            "macro_snapshot",
        ],
    ),
    ("Research", ["original_strategy_spec", "strategy_spec", "research_debate"]),
    ("BacktestCode", ["backtest_code"]),
    ("Backtest", ["backtest"]),
    ("Signal", ["signal"]),
    ("Risk Manager", ["risk"]),
    ("Report", ["report", "report_debate"]),
    ("Envelope", ["envelope"]),
]

OUTPUT_DIR = Path(__file__).parent / "prompt_semantics_output"
JSON_OUTPUT_PATH = OUTPUT_DIR / "node_results.json"
MARKDOWN_OUTPUT_PATH = OUTPUT_DIR / "report.md"


def group_state_by_node(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    remaining = dict(state)
    grouped: dict[str, dict[str, Any]] = {}
    for node_name, keys in NODE_KEY_GROUPS:
        grouped[node_name] = {key: remaining.pop(key) for key in keys if key in remaining}
    if remaining:
        grouped["Other"] = remaining
    return grouped


# Backtest/BacktestCode carry generated Python source per candidate and full
# per-trade execution audit logs across up to ~36 self-improvement candidates
# per prompt - dumped raw this balloons to 100+ MB and is unreadable. Truncate
# long strings everywhere, and only truncate lists under known-bulky keys
# (candidate pools / per-trade logs) - other lists (e.g. report "sections",
# "entry_conditions") are structural and consumed downstream, so they must
# keep their exact shape (dicts stay dicts, no injected marker strings).
MAX_STRING_LENGTH = 400
MAX_LIST_ITEMS = 6
TRUNCATE_LIST_KEYS = frozenset(
    {"candidates", "execution_audit", "equity_curve", "engine_summaries_by_candidate"}
)


def compact_for_display(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, str):
        if len(value) <= MAX_STRING_LENGTH:
            return value
        return f"{value[:MAX_STRING_LENGTH]}... [truncated, {len(value)} chars total]"
    if isinstance(value, dict):
        if key in TRUNCATE_LIST_KEYS and len(value) > MAX_LIST_ITEMS:
            kept = dict(list(value.items())[:MAX_LIST_ITEMS])
            return {
                **{k: compact_for_display(v, key=k) for k, v in kept.items()},
                "_truncated": f"{len(value) - MAX_LIST_ITEMS} more entries omitted",
            }
        return {k: compact_for_display(v, key=k) for k, v in value.items()}
    if isinstance(value, list):
        if key in TRUNCATE_LIST_KEYS and len(value) > MAX_LIST_ITEMS:
            return [compact_for_display(item, key=key) for item in value[:MAX_LIST_ITEMS]] + [
                f"... [truncated, {len(value) - MAX_LIST_ITEMS} more items]"
            ]
        return [compact_for_display(item, key=key) for item in value]
    return value


def run_prompt(index: int, expected_strategy_id: str, prompt: str) -> dict[str, Any]:
    trace_id = f"semantic-{index:02d}"
    try:
        state = build_graph().invoke({"user_query": prompt, "trace_id": trace_id})
        error = None
    except Exception as exc:  # noqa: BLE001 - want to keep going across all prompts
        state = {}
        error = f"{type(exc).__name__}: {exc}"

    actual_strategy_id = (state.get("strategy_spec") or {}).get("strategy_id")
    matches_expected = bool(actual_strategy_id and actual_strategy_id.startswith(expected_strategy_id))
    return {
        "index": index,
        "trace_id": trace_id,
        "prompt": prompt,
        "expected_strategy_id": expected_strategy_id,
        "actual_strategy_id": actual_strategy_id,
        "matches_expected": matches_expected,
        "status": state.get("status"),
        "error": error,
        "nodes": compact_for_display(group_state_by_node(state)) if state else {},
    }


def render_markdown_report(results: list[dict[str, Any]]) -> str:
    lines = ["# Strategy Prompt Semantics - Report Output", ""]
    for result in results:
        marker = "OK" if result["matches_expected"] else ("ERROR" if result["error"] else "MISMATCH")
        lines.append(
            f"## [{result['index']:02d}] {marker} - expected `{result['expected_strategy_id']}`"
            f" / actual `{result['actual_strategy_id']}`"
        )
        lines.append("")
        lines.append(f"**prompt**: {result['prompt']}")
        lines.append("")
        lines.append(f"**status**: `{result['status']}`")
        lines.append("")
        if result["error"]:
            lines.append(f"**error**: `{result['error']}`")
            lines.append("")
            continue

        report = result["nodes"].get("Report", {}).get("report")
        if not report:
            lines.append("_리포트 없음 (status != ready)_")
            lines.append("")
            continue

        web = report.get("web_projection", {})
        lines.append(f"### {web.get('title', '(제목 없음)')}")
        lines.append("")
        lines.append(web.get("summary", ""))
        lines.append("")
        for section in web.get("sections", []):
            lines.append(f"#### {section.get('title', section.get('id'))} (`{section.get('id')}`)")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(section.get("items"), ensure_ascii=False, indent=2, default=str))
            lines.append("```")
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for index, (expected_strategy_id, prompt) in enumerate(PROMPT_CASES, start=1):
        print(f"[{index:02d}/{len(PROMPT_CASES)}] {expected_strategy_id}: {prompt[:40]}...")
        result = run_prompt(index, expected_strategy_id, prompt)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        print()

    JSON_OUTPUT_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    MARKDOWN_OUTPUT_PATH.write_text(render_markdown_report(results), encoding="utf-8")

    matched = sum(1 for r in results if r["matches_expected"])
    errored = sum(1 for r in results if r["error"])
    print(f"총 {len(results)}개 중 {matched}개 strategy_id 일치, {errored}개 에러.")
    print(f"노드별 전체 결과(JSON): {JSON_OUTPUT_PATH}")
    print(f"최종 리포트(Markdown): {MARKDOWN_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
