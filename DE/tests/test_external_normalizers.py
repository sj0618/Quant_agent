from datetime import date
from decimal import Decimal
from io import BytesIO
import unittest
from zipfile import ZipFile

from quant_agent.data.models import RawSourcePayload
from quant_agent.data.sources.bok import normalize_bok_observations
from quant_agent.data.sources.dart import normalize_corp_code_zip, normalize_financial_statement
from quant_agent.data.sources.seibro import LexiconSentimentScorer, normalize_seibro_reports


class ExternalNormalizerTests(unittest.TestCase):
    def test_normalize_bok_observations(self):
        raw = RawSourcePayload(
            source="BOK",
            endpoint_key="StatisticSearch",
            request_date=date(2026, 5, 17),
            request={"stat_code": "722Y001", "cycle": "D", "item_code1": "0101000"},
            payload={"StatisticSearch": {"row": [{"STAT_CODE": "722Y001", "ITEM_CODE1": "0101000", "TIME": "20260515", "DATA_VALUE": "3.50"}]}},
        )
        rows = normalize_bok_observations(raw, published_at_policy="none")
        self.assertEqual(rows[0]["series_id"], "722Y001:0101000")
        self.assertEqual(rows[0]["effective_date"], date(2026, 5, 15))
        self.assertEqual(rows[0]["value"], Decimal("3.50"))

    def test_normalize_dart_corp_codes_and_financials(self):
        xml = b"<result><list><corp_code>00126380</corp_code><corp_name>Samsung</corp_name><stock_code>005930</stock_code><modify_date>20260515</modify_date></list></result>"
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr("CORPCODE.xml", xml)
        corp_rows = normalize_corp_code_zip(buffer.getvalue())
        self.assertEqual(corp_rows[0]["stock_code"], "005930")

        raw = RawSourcePayload(
            source="DART",
            endpoint_key="fnlttSinglAcntAll",
            request_date=date(2026, 5, 17),
            request={"corp_code": "00126380", "bsns_year": "2025", "reprt_code": "11011", "fs_div": "CFS"},
            payload={"status": "000", "list": [{"account_id": "ifrs-full_Revenue", "account_nm": "매출액", "thstrm_amount": "1,000"}]},
        )
        financial_rows = normalize_financial_statement(raw, symbol="005930")
        self.assertEqual(financial_rows[0]["period_end"], date(2025, 12, 31))
        self.assertEqual(financial_rows[0]["accounts"]["ifrs-full_Revenue"]["amount"], Decimal("1000"))

    def test_normalize_dart_financials_prefers_total_rows_by_statement(self):
        raw = RawSourcePayload(
            source="DART",
            endpoint_key="fnlttSinglAcntAll",
            request_date=date(2026, 7, 24),
            request={"corp_code": "00126380", "bsns_year": "2026", "reprt_code": "11013", "fs_div": "CFS"},
            payload={
                "status": "000",
                "list": [
                    {
                        "account_id": "ifrs-full_Equity",
                        "sj_div": "SCE",
                        "account_nm": "자본",
                        "account_detail": "연결재무제표 [member]",
                        "thstrm_amount": "0",
                    },
                    {
                        "account_id": "ifrs-full_Equity",
                        "sj_div": "BS",
                        "account_nm": "자본총계",
                        "account_detail": "-",
                        "thstrm_amount": "1234",
                    },
                    {
                        "account_id": "ifrs-full_ProfitLoss",
                        "sj_div": "SCE",
                        "account_nm": "당기순이익",
                        "account_detail": "자본 [member]|지배기업의 소유주에게 귀속되는 자본 [member]|이익잉여금 [member]",
                        "thstrm_amount": "0",
                    },
                    {
                        "account_id": "ifrs-full_ProfitLoss",
                        "sj_div": "CIS",
                        "account_nm": "당기순이익",
                        "account_detail": "-",
                        "thstrm_amount": "5678",
                    },
                    {
                        "account_id": "ifrs-full_ProfitLoss",
                        "sj_div": "IS",
                        "account_nm": "당기순이익",
                        "account_detail": "-",
                        "thstrm_amount": "91011",
                    },
                ],
            },
        )

        financial_rows = normalize_financial_statement(raw, symbol="005930")
        accounts = financial_rows[0]["accounts"]

        self.assertEqual(accounts["ifrs-full_Equity"]["amount"], Decimal("1234"))
        self.assertEqual(accounts["ifrs-full_Equity"]["raw"]["sj_div"], "BS")
        self.assertEqual(accounts["ifrs-full_ProfitLoss"]["amount"], Decimal("91011"))
        self.assertEqual(accounts["ifrs-full_ProfitLoss"]["raw"]["sj_div"], "IS")

    def test_normalize_dart_financials_skips_expanded_rows_when_next_preferred_total_exists(self):
        raw = RawSourcePayload(
            source="DART",
            endpoint_key="fnlttSinglAcntAll",
            request_date=date(2026, 7, 24),
            request={"corp_code": "00126380", "bsns_year": "2026", "reprt_code": "11013", "fs_div": "CFS"},
            payload={
                "status": "000",
                "list": [
                    {
                        "account_id": "ifrs-full_ProfitLoss",
                        "sj_div": "IS",
                        "account_nm": "당기순이익",
                        "account_detail": "연결재무제표 [member]",
                        "thstrm_amount": "111",
                    },
                    {
                        "account_id": "ifrs-full_ProfitLoss",
                        "sj_div": "CIS",
                        "account_nm": "당기순이익",
                        "account_detail": "-",
                        "thstrm_amount": "222",
                    },
                ],
            },
        )

        financial_rows = normalize_financial_statement(raw, symbol="005930")
        account = financial_rows[0]["accounts"]["ifrs-full_ProfitLoss"]

        self.assertEqual(account["amount"], Decimal("222"))
        self.assertEqual(account["raw"]["sj_div"], "CIS")

    def test_normalize_seibro_reports_and_sentiment(self):
        reports = normalize_seibro_reports(
            {
                "rows": [
                    {
                        "stock_code": "005930",
                        "corp_name": "삼성전자",
                        "report_date": "2026-05-15",
                        "summary": "실적 개선과 성장 전망으로 매수 의견",
                        "opinion": "Buy",
                        "target_price": "90000",
                    }
                ]
            }
        )
        self.assertEqual(reports[0].symbol, "005930")
        self.assertGreater(LexiconSentimentScorer().score(reports[0].summary), 0)


if __name__ == "__main__":
    unittest.main()
