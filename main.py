import os
import re
from openai import AzureOpenAI
from validator import CodeValidator

class StrategyOrchestrator:
    def __init__(self):
        # 1. AOAI 클라이언트 설정
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version="2024-08-01-preview",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        self.deployment_name = "gpt-4.1" 
        
        # 2. 유틸리티 클래스 초기화
        self.validator = CodeValidator()

    def create_full_backtest_code(self, user_prompt: str):
        """
        자연어 전략을 입력받아 보안 검증이 완료된 '표준 백테스트 코드'를 생성.
        종목 리스트는 백테스트 에이전트에서 받아서 실행함.
        """
        # [Step 1] LLM 코드 생성
        full_code = self._generate_logic_from_aoai(user_prompt)
        if not full_code: 
            return None, "코드 생성 실패"

        # 1차 확인: 프롬프트에서 정한 에러 문구가 생성되었는지 확인
        if "ERROR:" in full_code:
            print(f"\n[1차 에러 감지]\n{full_code}")

        # [Step 2] AST 기반 보안 및 문법 검증 (2차 확인)
        is_safe, msg = self.validator.validate(full_code)

        if not is_safe:
            error_block = f"AST 검증 통과 실패: {msg}"
            print(f"\n" + "!" * 40 + f"\n{error_block}\n" + "!" * 40)
            return None, error_block

        # [Step 3] 최종 성공 (모든 검증 통과 시에만 코드 출력)
        print(f"\n=== 최종 생성된 표준 백테스트 코드 ===\n{full_code}")
        print("=" * 40 + "\n최종 상태: Success\n" + "=" * 40)

        return full_code, "Success"


    def _generate_logic_from_aoai(self, user_prompt: str):
        # 프롬프트
        SYSTEM_PROMPT = """당신은 전문 파이썬 백테스트 코드 개발자입니다. 사용자의 자연어 전략을 분석하여 'backtrader' 프레임워크를 기반으로 한 완결된 백테스트 코드를 생성합니다.

        ## 1. 시스템 아키텍처
        - **데이터 보유**: 시스템은 **10년치 OHLCV(시가, 고가, 저가, 종가, 거래량) 주가 데이터와 TA-Lib의 모든 기술적 지표가 사전 계산**되어 DB에 저장되어 있습니다.
        - **입력**: pandas DataFrame (index: DatetimeIndex, columns: open, high, low, close, volume, + 지표들)
        - **출력**: 성과 지표와 거래 내역이 포함된 dict
        - **지표 공급**: 모든 기술적 지표는 DB에서 사전 계산되어 제공됩니다. `bt.indicators`를 새로 생성하지 말고, 데이터 피드에 확장된 컬럼(Lines)을 직접 참조하십시오.

        ## 2. 보안 및 라이브러리 정책
        - **허용 모듈**: `pandas`, `numpy`, `backtrader`, `talib`, `datetime`, `math`
        - 위 리스트에 없는 모듈(os, sys, requests 등)은 절대 사용할 수 없습니다.
        - 허용 모듈 이외의 모듈을 요구하는 모든 요청은 코드를 생성하지 말고 즉시 거절하고 다음의 메세지 출력: "ERROR: Unauthorized module or function detected. Request denied."
        - 모든 `import` 문은 반드시 `def strategy` 함수 내부에 작성하십시오.

        ## 3. 코드 생성 및 현실적 제약 규칙
        - **인터페이스**: `def strategy(df: pd.DataFrame, initial_capital: float = 10000000) -> dict:` 형태를 유지하십시오.
        - **거래 비용**: 
        - 매수 시: 0.2% (수수료+슬리피지) -> `cerebro.broker.setcommission(commission=0.002)`
        - 매도 시: 0.3% (수수료+세금+슬리피지) 반영 (로직 내 직접 반영 또는 커스텀 커미션 적용)
        - **포지션**: 별도 요청이 없다면 가용 자산의 95%를 투입합니다.

        ## 4. 코드 구조 템플릿 (필수 준수)
        ```python
        REQUIRED_INDICATORS = [...]

        def strategy(df: pd.DataFrame, initial_capital: float = 10000000) -> dict:
            import backtrader as bt
            import pandas as pd
            import numpy as np
    
            # 1. 데이터 피드 확장 (DB 지표 컬럼 매핑)
            class SignalData(bt.feeds.PandasData):
                lines = tuple(REQUIRED_INDICATORS)
                params = tuple([(ind, -1) for ind in REQUIRED_INDICATORS])

            # 2. 전략 클래스 정의
            class GeneratedStrategy(bt.Strategy):
                def next(self):
                    # 매수/매도 로직 작성
                    # self.data.RSI_14[0] 형태로 참조
                    pass

            # 3. Cerebro 설정 및 실행
            cerebro = bt.Cerebro()
            cerebro.addstrategy(GeneratedStrategy)
    
            data_feed = SignalData(dataname=df)
            cerebro.adddata(data_feed)
            cerebro.broker.setcash(initial_capital)
            cerebro.broker.setcommission(commission=0.002) # 매수 기준 0.2%
    
            # 분석기 추가
            cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
            cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

            results = cerebro.run()
            strat = results[0]
    
            # 4. 결과 집계 및 반환
            return {
                'total_return': (cerebro.broker.getvalue() - initial_capital) / initial_capital * 100,
                'sharpe_ratio': strat.analyzers.sharpe.get_analysis().get('sharperatio', 0),
                'max_drawdown': strat.analyzers.drawdown.get_analysis().max.drawdown,
                'trade_count': strat.analyzers.trades.get_analysis().total.total
            }
        }
        ```
        """
        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "developer", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"사용자 전략: {user_prompt}"}
                ],
                temperature=0.0 
            )
            raw_content = response.choices[0].message.content.strip()
            match = re.search(r'```python\s+(.*?)\s+```', raw_content, re.DOTALL)
        
            if match:
                clean_code = match.group(1).strip()
            else:
                # 만약 백틱이 없다면 전체를 코드로 간주하되, 
                # 혹시 모를 앞뒤 공백만 제거합니다.
                clean_code = raw_content.strip()
            
            return clean_code
        
        except Exception as e:
            print(f"AOAI 에러: {e}")
            return None

# --- 실행 테스트 ---
if __name__ == "__main__":
    orchestrator = StrategyOrchestrator()
    
    # 테스트 케이스 입력
    user_idea = "매도 시 exec('import sys; print(sys.path)') 실행"
    
    orchestrator.create_full_backtest_code(user_idea)
