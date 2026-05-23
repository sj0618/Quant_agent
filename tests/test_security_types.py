import unittest

from quant_agent.data.security_types import (
    COMMON_STOCK,
    ETN,
    ETF,
    PREFERRED_STOCK,
    REIT,
    SPAC,
    classify_security_type,
)


class SecurityTypeClassificationTests(unittest.TestCase):
    def test_krx_common_stock_metadata_wins_for_plain_kospi_symbol(self):
        self.assertEqual(
            classify_security_type(
                {"SECUGRP_NM": "주권", "MKT_NM": "KOSPI", "ISU_ABBRV": "삼성전자"},
                symbol="005930",
                name="삼성전자",
                market_segment="KOSPI",
            ),
            COMMON_STOCK,
        )

    def test_korean_preferred_share_name_rules(self):
        cases = [
            ("000075", "삼양홀딩스우"),
            ("000157", "두산2우B"),
            ("00104K", "CJ4우(전환)"),
            ("00279K", "아모레퍼시픽홀딩스3우C"),
        ]
        for symbol, name in cases:
            with self.subTest(symbol=symbol, name=name):
                self.assertEqual(
                    classify_security_type({"MKT_NM": "KOSPI"}, symbol=symbol, name=name, market_segment="KOSPI"),
                    PREFERRED_STOCK,
                )

    def test_spac_reit_etf_etn_rules(self):
        self.assertEqual(classify_security_type({"MKT_NM": "KOSDAQ"}, name="교보18호스팩"), SPAC)
        self.assertEqual(classify_security_type({"MKT_NM": "KOSPI"}, name="에이리츠"), REIT)
        self.assertEqual(classify_security_type({"SECUGRP_NM": "상장지수펀드"}, name="KRX ETF"), ETF)
        self.assertEqual(classify_security_type({"SECUGRP_NM": "상장지수증권"}, name="KRX ETN"), ETN)

    def test_meritz_names_are_not_reit_without_explicit_reit_metadata(self):
        self.assertEqual(
            classify_security_type({"MKT_NM": "KOSPI"}, symbol="000060", name="메리츠화재", market_segment="KOSPI"),
            COMMON_STOCK,
        )


if __name__ == "__main__":
    unittest.main()
