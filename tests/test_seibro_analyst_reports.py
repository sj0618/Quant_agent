from datetime import date
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import unittest

from quant_agent.data.config import RetryConfig, SeibroConfig
from quant_agent.data.external import month_chunks
from quant_agent.data.sources.seibro import (
    SeibroAnalystReportClient,
    extract_ticker,
    normalize_analyst_report_summaries,
    strip_ticker_suffix,
)


class SeibroAnalystReportTests(unittest.TestCase):
    def test_extract_ticker_from_company_name(self):
        self.assertEqual(extract_ticker("대한항공(003490)"), "003490")
        self.assertEqual(strip_ticker_suffix("대한항공(003490)"), "대한항공")
        self.assertIsNone(extract_ticker("대한항공"))

    def test_month_chunks_supports_one_month_boundaries(self):
        self.assertEqual(
            month_chunks(date(2026, 4, 20), date(2026, 5, 20), 1),
            [(date(2026, 4, 20), date(2026, 5, 19)), (date(2026, 5, 20), date(2026, 5, 20))],
        )

    def test_fetch_and_normalize_with_local_http_server(self):
        seen_bodies: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers["Content-Length"])
                seen_bodies.append(self.rfile.read(length).decode("utf-8"))
                payload = """<?xml version="1.0" encoding="UTF-8" ?>
<vector result="1">
  <data vectorkey="0" type="Document">
    <result>
      <STD_DT value="20260520"/>
      <SHOTN_ISIN value="003490"/>
      <REP_SECN value="대한항공(003490)"/>
      <ENTR_SUMM_CONTENT value="실적 개선$$목표가 상향"/>
      <INVST_OPINION_GRD_CONTENT value="BUY"/>
      <TARGET_PRICE value="30000"/>
      <CPRI value="24000"/>
      <WROT_ORG_NM value="테스트증권"/>
      <WRITER_NM value="홍길동"/>
    </result>
  </data>
</vector>"""
                encoded = payload.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/xml; charset=UTF-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format, *args):  # noqa: A003
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = _seibro_config(f"http://127.0.0.1:{server.server_port}")
            client = SeibroAnalystReportClient(config)
            payload = client.fetch_summary_page(
                start_date=date(2026, 5, 1),
                end_date=date(2026, 5, 20),
                start_row=1,
                end_row=30,
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)

        self.assertIn('action="entrAnalysisSummaryReportPList"', seen_bodies[0])
        self.assertIn('<STD_DT1 value="20260501"/>', seen_bodies[0])
        reports = normalize_analyst_report_summaries(payload)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].ticker, "003490")
        self.assertEqual(reports[0].company_name, "대한항공")
        self.assertEqual(reports[0].summary, "실적 개선\n목표가 상향")


def _seibro_config(base_url: str) -> SeibroConfig:
    return SeibroConfig(
        base_url=base_url,
        web_base_url=base_url,
        analyst_report_page_path="/page",
        analyst_report_api_path="/api",
        analyst_report_action="entrAnalysisSummaryReportPList",
        analyst_report_task="ksd.safe.bip.cnts.Company.process.EntrAnalysisPTask",
        analyst_report_page_size=30,
        analyst_report_chunk_months=1,
        request_sleep_min_seconds=0,
        request_sleep_max_seconds=0,
        api_key=None,
        collection_approved=True,
        request_timeout_seconds=5,
        retry=RetryConfig(attempts=1, backoff_seconds=0),
    )


if __name__ == "__main__":
    unittest.main()
