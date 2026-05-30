# L1 Strategy Catalog 50

QuantAgent MVP 운영용 전략 catalog. 각 entry는 7필드 스키마를 갖는다.

strategy_id: rsi_rebound
title: RSI 과매도 반등
definition: RSI(14)가 30 이하로 내려간 뒤 30을 회복하는 단기 반등 후보.
formula: RSI14 cross_above 30 after RSI14 <= 30.
recommended_thresholds: RSI<=30, cross_above 30, volume_ratio_20>=1.0. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: RSI 과매도 반등은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: RSI 과매도 반등은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for rsi_rebound.

strategy_id: breakout_volume_momentum
title: 거래량 돌파 모멘텀
definition: 52주/120일/20일 신고가와 거래량 150% 이상을 결합.
formula: close >= rolling_high_N and volume >= 1.5*avg_volume_20.
recommended_thresholds: N=20/120/252, volume_ratio_20>=1.5, close>sma20. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 거래량 돌파 모멘텀은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 거래량 돌파 모멘텀은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for breakout_volume_momentum.

strategy_id: pullback_trend
title: 상승추세 눌림목
definition: 200일선 위 상승추세에서 20일선 근처 조정 후 재상승.
formula: close>sma200 and abs(close/sma20-1)<=0.04.
recommended_thresholds: close>sma200, close near sma20. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 상승추세 눌림목은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 상승추세 눌림목은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for pullback_trend.

strategy_id: bollinger_squeeze_breakout
title: 볼린저 스퀴즈 돌파
definition: 밴드 폭 축소 후 상단 돌파 또는 하단 재진입.
formula: bb_width percentile <=25% and close >= upper_band.
recommended_thresholds: bb_width<=p25, close>=bb_upper. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 볼린저 스퀴즈 돌파은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 볼린저 스퀴즈 돌파은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for bollinger_squeeze_breakout.

strategy_id: relative_strength_leader
title: 상대강도 주도주
definition: 시장보다 1개월/3개월 상대강도가 높은 후보.
formula: return_N - benchmark_return_N > 0.
recommended_thresholds: RS20>=0, RS60>=0. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 상대강도 주도주은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 상대강도 주도주은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for relative_strength_leader.

strategy_id: value_quality
title: 저평가 퀄리티
definition: 낮은 PER/PBR과 높은 ROE를 결합하고 가격 상대강도로 확인.
formula: PER percentile<=40 and ROE>=15% and debt<=100%.
recommended_thresholds: PER low, ROE>=15%, debt<=100%. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 저평가 퀄리티은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 저평가 퀄리티은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for value_quality.

strategy_id: reasonable_growth
title: 합리적 성장주
definition: 성장성과 밸류에이션을 동시에 보는 GARP 후보.
formula: ROE>=15% and sales_growth>=10% and PER<=industry_avg.
recommended_thresholds: ROE>=15%, sales_growth>=10%. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 합리적 성장주은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 합리적 성장주은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for reasonable_growth.

strategy_id: quality_growth
title: 퀄리티 성장주
definition: 업종 평균보다 높은 수익성과 매출 성장률을 결합.
formula: ROE>industry_avg and op_margin>industry_avg and sales_growth>0.
recommended_thresholds: profitability above industry. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 퀄리티 성장주은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 퀄리티 성장주은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for quality_growth.

strategy_id: dividend_defensive
title: 배당 방어주
definition: 배당수익률과 재무 안정성에 기술 추세를 결합.
formula: dividend_yield>=4% and debt<=100% and close>sma200.
recommended_thresholds: yield>=4%, close>sma200. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 배당 방어주은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 배당 방어주은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for dividend_defensive.

strategy_id: low_vol_defensive
title: 저변동 방어주
definition: 낮은 변동성과 시장 대비 강한 수익률을 결합.
formula: volatility_20d<=market_p40 and RS20>=0.
recommended_thresholds: low vol, RS20>=0. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 저변동 방어주은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 저변동 방어주은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for low_vol_defensive.

strategy_id: earnings_momentum
title: 실적 모멘텀
definition: EPS 컨센서스 상향과 신고가 돌파를 결합.
formula: eps_revision_3m>0 and close>=high_20.
recommended_thresholds: revision proxy, high_20. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 실적 모멘텀은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 실적 모멘텀은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for earnings_momentum.

strategy_id: earnings_surprise_guidance
title: 어닝 서프라이즈 가이던스
definition: 어닝 서프라이즈와 다음 분기 가이던스 상향 후보.
formula: surprise>0 and guidance_revision>0.
recommended_thresholds: surprise, guidance. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 어닝 서프라이즈 가이던스은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 어닝 서프라이즈 가이던스은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for earnings_surprise_guidance.

strategy_id: flow_accumulation
title: 기관 외국인 수급 모멘텀
definition: 기관/외국인 순매수 흐름을 가격/거래량으로 확인.
formula: net_buy_streak>=5 and close>sma20.
recommended_thresholds: net_buy proxy, close>sma20. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 기관 외국인 수급 모멘텀은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 기관 외국인 수급 모멘텀은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for flow_accumulation.

strategy_id: short_covering_proxy
title: 숏커버링 proxy
definition: 공매도 잔고가 높고 거래량 증가 양봉 돌파가 나온 후보.
formula: short_balance_high and volume_ratio_20>=1.5 and bullish_breakout.
recommended_thresholds: volume_ratio>=1.5. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 숏커버링 proxy은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 숏커버링 proxy은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for short_covering_proxy.

strategy_id: gap_hold_momentum
title: 갭 유지 모멘텀
definition: 갭 상승 후 갭을 메우지 않고 횡보하는 후보.
formula: gap_up and gap_unfilled and RS20>=0.
recommended_thresholds: gap_up, gap_unfilled. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 갭 유지 모멘텀은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 갭 유지 모멘텀은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for gap_hold_momentum.

strategy_id: breakout_setup
title: 돌파 대기
definition: 신고가 근처에서 거래량이 줄며 횡보하는 후보.
formula: near_high and volume_dry_up and turnover_ok.
recommended_thresholds: near_high, dry_volume. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 돌파 대기은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 돌파 대기은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for breakout_setup.

strategy_id: breakout_pullback
title: 신고가 돌파 후 되돌림
definition: 120일 신고가 돌파 뒤 20일선 되돌림 후보.
formula: breakout_high_120 and pullback_to_sma20.
recommended_thresholds: high_120, sma20. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 신고가 돌파 후 되돌림은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 신고가 돌파 후 되돌림은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for breakout_pullback.

strategy_id: midterm_pullback
title: 중기 상승추세 눌림목
definition: 1개월 약세와 6개월 강세를 결합한 눌림목.
formula: RS20<0 and RS120>=0 and close>sma200.
recommended_thresholds: RS20<0, RS120>=0. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 중기 상승추세 눌림목은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 중기 상승추세 눌림목은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for midterm_pullback.

strategy_id: trend_rsi_volume_pullback
title: 추세 RSI 거래량 눌림목
definition: 200일선 위에서 RSI 40 이하와 거래량 확인.
formula: close>sma200 and rsi<=40 and volume_ratio_20>=1.
recommended_thresholds: rsi<=40, volume>=avg20. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 추세 RSI 거래량 눌림목은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 추세 RSI 거래량 눌림목은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for trend_rsi_volume_pullback.

strategy_id: oversold_quality
title: 과매도 우량주
definition: 고점 대비 큰 하락에도 실적 proxy가 유지되는 후보.
formula: drawdown_60d<=-20% and rsi<=35.
recommended_thresholds: drawdown<=-20%, rsi<=35. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 과매도 우량주은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 과매도 우량주은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for oversold_quality.

strategy_id: fcf_recovery
title: FCF 회복주
definition: FCF 수익률과 200일선 회복을 결합.
formula: fcf_yield>=5% and close>sma200.
recommended_thresholds: fcf proxy, sma200. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: FCF 회복주은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: FCF 회복주은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for fcf_recovery.

strategy_id: asset_value_catalyst
title: 자산가치 촉매
definition: PBR 1배 이하와 자사주/순현금 촉매 후보.
formula: pbr<=1 and net_cash and buyback_notice.
recommended_thresholds: pbr<=1, buyback. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 자산가치 촉매은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 자산가치 촉매은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for asset_value_catalyst.

strategy_id: margin_improvement
title: 원가하락 마진 개선
definition: 원자재 가격 하락 수혜와 50일선 추세 확인.
formula: input_cost_tailwind and op_margin_improving and close>sma50.
recommended_thresholds: margin proxy, sma50. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 원가하락 마진 개선은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 원가하락 마진 개선은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for margin_improvement.

strategy_id: margin_inventory_quality
title: 마진 재고 퀄리티
definition: 매출총이익률 개선과 낮은 재고 부담 후보.
formula: gross_margin_streak>=3 and inventory_growth<=sales_growth.
recommended_thresholds: gross margin, inventory. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 마진 재고 퀄리티은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 마진 재고 퀄리티은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for margin_inventory_quality.

strategy_id: operating_profit_pullback
title: 이익성장 조정주
definition: 4분기 영업이익 증가 후 60일 고점 대비 조정.
formula: op_profit_growth_streak>=4 and drawdown_60d<=-10%.
recommended_thresholds: profit streak, drawdown. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 이익성장 조정주은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 이익성장 조정주은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for operating_profit_pullback.

strategy_id: rate_sensitive_income
title: 금리 민감 인컴주
definition: 금리 하락기에 강했던 리츠/유틸리티/배당주 기술 신호.
formula: rate_down_proxy and close>sma50.
recommended_thresholds: income, sma50. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 금리 민감 인컴주은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 금리 민감 인컴주은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for rate_sensitive_income.

strategy_id: fx_exporter_revision
title: 환율 수혜 이익상향
definition: 원달러 상승 수혜 수출주와 이익 전망 상향.
formula: fx_benefit_proxy and revision_3m>0.
recommended_thresholds: fx proxy, revision. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 환율 수혜 이익상향은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 환율 수혜 이익상향은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for fx_exporter_revision.

strategy_id: growth_momentum
title: 성장 모멘텀
definition: 매출 성장률 상위와 50일선 위 추세 후보.
formula: sales_growth_top20 and close>sma50.
recommended_thresholds: growth, sma50. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 성장 모멘텀은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 성장 모멘텀은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for growth_momentum.

strategy_id: volatility_contraction
title: 변동성 축소 돌파
definition: 20일 변동성과 볼린저 폭 축소 후 돌파.
formula: vol20 falling and bb_width falling and close>bb_upper.
recommended_thresholds: vol contraction. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 변동성 축소 돌파은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 변동성 축소 돌파은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for volatility_contraction.

strategy_id: bb_reentry_rebound
title: 밴드 재진입 반등
definition: 볼린저 하단 이탈 후 종가 기준 밴드 안 재진입.
formula: close crosses above lower_band after below.
recommended_thresholds: lower band reentry. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 밴드 재진입 반등은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 밴드 재진입 반등은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for bb_reentry_rebound.

strategy_id: technical_rebound_10d
title: 10일 하락 기술 반등
definition: 최근 10거래일 하락, 거래량 감소, RSI 과매도.
formula: down_days_10 high and volume_down and rsi<=35.
recommended_thresholds: down trend, rsi. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 10일 하락 기술 반등은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 10일 하락 기술 반등은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for technical_rebound_10d.

strategy_id: volume_dryup_near_high
title: 신고가 근처 거래량 감소
definition: 신고가 근처 횡보와 거래량 감소 후 대기.
formula: near_high and volume_ratio_20<1.
recommended_thresholds: near high, dry up. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 신고가 근처 거래량 감소은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 신고가 근처 거래량 감소은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for volume_dryup_near_high.

strategy_id: sector_leadership
title: 섹터 주도주
definition: 1개월/3개월 상대강도가 모두 높은 섹터 대표 후보.
formula: RS20>0 and RS60>0 and sector_rank high.
recommended_thresholds: sector RS. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 섹터 주도주은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 섹터 주도주은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for sector_leadership.

strategy_id: export_revision_momentum
title: 수출주 이익상향
definition: 수출 민감 업종 중 이익 전망 상향 후보.
formula: export_proxy and earnings_revision>0.
recommended_thresholds: export, revision. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 수출주 이익상향은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 수출주 이익상향은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for export_revision_momentum.

strategy_id: consumer_margin_tailwind
title: 소비재 마진 수혜
definition: 원자재 하락으로 마진 개선이 기대되는 소비재 후보.
formula: input_cost_down and sector=consumer and close>sma50.
recommended_thresholds: consumer margin. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 소비재 마진 수혜은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 소비재 마진 수혜은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for consumer_margin_tailwind.

strategy_id: chemical_margin_tailwind
title: 화학 마진 수혜
definition: 원자재 하락과 스프레드 개선이 기대되는 화학 후보.
formula: input_cost_down and sector=chemical and close>sma50.
recommended_thresholds: chemical margin. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 화학 마진 수혜은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 화학 마진 수혜은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for chemical_margin_tailwind.

strategy_id: transport_margin_tailwind
title: 운송 마진 수혜
definition: 유가/원가 하락 수혜와 추세 회복 후보.
formula: fuel_cost_down and close>sma50.
recommended_thresholds: transport margin. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 운송 마진 수혜은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 운송 마진 수혜은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for transport_margin_tailwind.

strategy_id: sales_top20_momentum
title: 매출 성장 상위 모멘텀
definition: 3개월 매출 성장률 업종 상위 20%와 50일선 위.
formula: sales_growth_rank<=20% and close>sma50.
recommended_thresholds: top20 growth. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 매출 성장 상위 모멘텀은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 매출 성장 상위 모멘텀은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for sales_top20_momentum.

strategy_id: cashflow_quality_recovery
title: 현금흐름 회복
definition: 안정적 현금흐름과 200일선 회복 후보.
formula: cashflow_stable and close>sma200.
recommended_thresholds: cashflow, sma200. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 현금흐름 회복은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 현금흐름 회복은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for cashflow_quality_recovery.

strategy_id: roe_sales_value
title: ROE 매출 PER 균형
definition: ROE 15%, 매출 10%, PER 업종 이하 후보.
formula: roe>=15 and sales_growth>=10 and per<=industry.
recommended_thresholds: GARP. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: ROE 매출 PER 균형은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: ROE 매출 PER 균형은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for roe_sales_value.

strategy_id: new_high_volume_52w
title: 52주 신고가 거래량
definition: 52주 신고가와 20일 평균 대비 거래량 150%.
formula: close>=high_252 and volume_ratio_20>=1.5.
recommended_thresholds: 52w high. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 52주 신고가 거래량은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 52주 신고가 거래량은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for new_high_volume_52w.

strategy_id: new_high_volume_120d
title: 120일 신고가 거래량
definition: 120일 신고가와 거래량 증가 후보.
formula: close>=high_120 and volume_ratio_20>=1.3.
recommended_thresholds: 120d high. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 120일 신고가 거래량은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 120일 신고가 거래량은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for new_high_volume_120d.

strategy_id: new_high_volume_20d
title: 20일 신고가 거래량
definition: 20일 신고가와 단기 모멘텀 후보.
formula: close>=high_20 and volume_ratio_20>=1.2.
recommended_thresholds: 20d high. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 20일 신고가 거래량은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 20일 신고가 거래량은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for new_high_volume_20d.

strategy_id: sma20_reclaim
title: 20일선 회복
definition: 조정 후 20일선을 회복하는 후보.
formula: close crosses above sma20.
recommended_thresholds: sma20 reclaim. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 20일선 회복은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 20일선 회복은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for sma20_reclaim.

strategy_id: sma200_recovery
title: 200일선 회복
definition: 장기 하락 후 200일선 위로 회복한 후보.
formula: close crosses above sma200.
recommended_thresholds: sma200 recovery. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 200일선 회복은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 200일선 회복은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for sma200_recovery.

strategy_id: low_vol_high_dividend
title: 저변동 고배당
definition: 저변동성, 시장 대비 강세, 배당수익률을 결합.
formula: vol_low and RS20>0 and dividend_yield high.
recommended_thresholds: low vol dividend. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 저변동 고배당은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 저변동 고배당은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for low_vol_high_dividend.

strategy_id: high_roe_value
title: 고ROE 저PER
definition: ROE가 높고 PER이 낮은 가치 후보.
formula: roe>=15 and per_percentile<=40.
recommended_thresholds: high roe value. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 고ROE 저PER은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 고ROE 저PER은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for high_roe_value.

strategy_id: net_cash_buyback
title: 순현금 자사주
definition: 순현금과 자사주 매입 공시 후보.
formula: net_cash and buyback_notice.
recommended_thresholds: net cash buyback. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 순현금 자사주은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 순현금 자사주은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for net_cash_buyback.

strategy_id: consensus_hold_oversold
title: 컨센서스 유지 과매도
definition: 낙폭이 크지만 컨센서스가 유지되는 후보.
formula: drawdown<=-20% and revision>=0.
recommended_thresholds: consensus hold. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 컨센서스 유지 과매도은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 컨센서스 유지 과매도은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for consensus_hold_oversold.

strategy_id: institutional_accumulation
title: 기관 연속 순매수
definition: 기관 순매수 연속성과 20일선 위 조건.
formula: institution_net_buy_streak>=5 and close>sma20.
recommended_thresholds: institution flow. KOSPI200 daily 기준.
sources: QuantAgent local MVP catalog; Quantpedia/TA-Lib/public market practice review required before production.
bull_case: 기관 연속 순매수은 조건이 명확하고 가격/거래량/TA feature로 빠르게 검증 가능할 때 강점이 있다.
bear_case: 기관 연속 순매수은 재무/컨센서스/공시 데이터가 미연동이면 proxy bias와 과최적화 위험이 있다.
examples: KOSPI200 daily screening fixture for institutional_accumulation.
