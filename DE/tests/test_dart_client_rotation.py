from __future__ import annotations

import unittest

from quant_agent.data.config import DartConfig, RetryConfig
from quant_agent.data.sources.dart import OpenDartClient


class FakeOpenDartClient(OpenDartClient):
    def __init__(self, config: DartConfig, payloads: list[dict[str, object]]) -> None:
        super().__init__(config)
        self._payloads = iter(payloads)
        self.keys_used: list[str] = []

    def _fetch_financial_payload_once(
        self,
        *,
        api_key: str,
        corp_code: str,
        business_year: int,
        report_code: str,
        fs_div: str,
    ) -> dict[str, object]:
        self.keys_used.append(api_key)
        return next(self._payloads)


class DartClientRotationTests(unittest.TestCase):
    def test_fetch_financial_statement_rotates_after_quota_error(self) -> None:
        config = DartConfig(
            base_url="https://opendart.example.invalid",
            api_keys=("key-1", "key-2", "key-3"),
            request_timeout_seconds=1,
            retry=RetryConfig(attempts=1, backoff_seconds=0.0),
        )
        client = FakeOpenDartClient(
            config,
            [
                {"status": "020", "message": "사용한도를 초과하였습니다."},
                {
                    "status": "000",
                    "list": [{"account_id": "ifrs-full_Revenue", "account_nm": "매출액", "thstrm_amount": "100"}],
                },
                {
                    "status": "000",
                    "list": [{"account_id": "ifrs-full_Revenue", "account_nm": "매출액", "thstrm_amount": "200"}],
                },
            ],
        )

        first = client.fetch_financial_statement(
            corp_code="00126380",
            business_year=2025,
            report_code="11011",
            fs_div="CFS",
        )
        second = client.fetch_financial_statement(
            corp_code="00126380",
            business_year=2025,
            report_code="11011",
            fs_div="CFS",
        )

        self.assertEqual(client.keys_used, ["key-1", "key-2", "key-3"])
        self.assertEqual(first.request["corp_code"], "00126380")
        self.assertEqual(first.request["reprt_code"], "11011")
        self.assertEqual(first.payload["status"], "000")
        self.assertEqual(second.payload["list"][0]["thstrm_amount"], "200")


if __name__ == "__main__":
    unittest.main()
