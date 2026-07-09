from datetime import date
from decimal import Decimal
import unittest

from quant_agent.data.sources.kis import normalize_kis_daily_price
from quant_agent.data.sources.krx import normalize_krx_market_day


class SourceNormalizerTests(unittest.TestCase):
    def test_normalize_krx_market_day(self):
        payload = {
            "OutBlock_1": [
                {
                    "BAS_DD": "20260515",
                    "ISU_CD": "005930",
                    "ISU_NM": "삼성전자",
                    "TDD_OPNPRC": "70,000",
                    "TDD_HGPRC": "71,000",
                    "TDD_LWPRC": "69,500",
                    "TDD_CLSPRC": "70,500",
                    "ACC_TRDVOL": "1234567",
                    "MKT_NM": "KOSPI",
                    "LIST_SHRS": "5969782550",
                }
            ]
        }
        bars = normalize_krx_market_day(payload)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].symbol, "005930")
        self.assertEqual(bars[0].trade_date, date(2026, 5, 15))
        self.assertEqual(bars[0].close, Decimal("70500"))
        self.assertEqual(bars[0].raw["MKT_NM"], "KOSPI")

    def test_normalize_kis_daily_price(self):
        payload = {
            "output2": [
                {
                    "stck_bsop_date": "20260515",
                    "stck_oprc": "70000",
                    "stck_hgpr": "71000",
                    "stck_lwpr": "69500",
                    "stck_clpr": "70500",
                    "acml_vol": "1234567",
                    "mod_yn": "Y",
                    "revl_issu_reas": "액면분할",
                }
            ]
        }
        bars = normalize_kis_daily_price(payload, symbol="005930")
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].symbol, "005930")
        self.assertEqual(bars[0].trade_date, date(2026, 5, 15))
        self.assertEqual(bars[0].volume, Decimal("1234567"))
        self.assertEqual(bars[0].raw["mod_yn"], "Y")
        self.assertEqual(bars[0].raw["revl_issu_reas"], "액면분할")


if __name__ == "__main__":
    unittest.main()
