from ai_graph.graph import run_analysis


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


def test_screening_prompt_batch_maps_to_related_strategy_and_nonzero_report(monkeypatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "mock")
    monkeypatch.setenv("AI_DATABASE_DSN", "")

    for index, (expected_strategy_id, prompt) in enumerate(PROMPT_CASES, start=1):
        envelope = run_analysis(prompt, trace_id=f"semantic-{index:02d}")

        assert envelope.status == "ready"
        assert envelope.strategy_spec is not None
        assert envelope.strategy_spec.strategy_id.startswith(expected_strategy_id)

        performance = envelope.user_payload.performance
        assert performance is not None
        selected_metrics = performance.metrics
        assert selected_metrics.total_return != 0
        assert performance.selected_candidate_id

        report = envelope.user_payload.report
        assert report is not None
        section_ids = {section["id"] for section in report.web_projection.sections}
        assert {"strategy", "entry_conditions", "assumptions", "backtest"} <= section_ids
