from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import threading
import unittest

from quant_agent.data.config import KisConfig, RetryConfig
from quant_agent.data.sources.kis import KisOhlcvClient


class KisObservabilityTests(unittest.TestCase):
    def test_daily_price_records_attempt_level_status_retry_and_latency(self):
        if importlib.util.find_spec("requests") is None:
            self.skipTest("requests package is not installed in this Python environment")
        events = []
        server = _start_server()
        client = KisOhlcvClient(_kis_config(), request_observer=events.append)
        client.config = KisConfig(**{**client.config.__dict__, "base_url": f"http://127.0.0.1:{server.server_port}"})
        try:
            payload = client.fetch_daily_price_payload(
                symbol="005930",
                start_date=date(2026, 5, 1),
                end_date=date(2026, 5, 2),
                adjusted=True,
            )
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(payload.payload["rt_cd"], "0")
        self.assertEqual(KisTestHandler.call_count, 2)
        self.assertEqual(len(events), 2)
        self.assertFalse(events[0].success)
        self.assertEqual(events[0].status_code, 500)
        self.assertEqual(events[0].retry_count, 0)
        self.assertTrue(events[1].success)
        self.assertEqual(events[1].status_code, 200)
        self.assertEqual(events[1].retry_count, 1)
        self.assertGreaterEqual(events[1].elapsed_ms, 0)
        self.assertNotIn("appsecret", events[1].request)
        self.assertNotIn("authorization", events[1].request)


class KisTestHandler(BaseHTTPRequestHandler):
    call_count = 0

    def do_GET(self):  # noqa: N802 - http.server hook name
        type(self).call_count += 1
        if type(self).call_count == 1:
            self.send_response(500)
            payload = {"rt_cd": "1"}
        else:
            self.send_response(200)
            payload = {"rt_cd": "0", "output2": []}
        body = json.dumps(payload).encode("utf-8")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002, ANN001 - http.server signature
        return


def _start_server() -> ThreadingHTTPServer:
    KisTestHandler.call_count = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), KisTestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _kis_config() -> KisConfig:
    return KisConfig(
        app_key="app",
        app_secret="secret",
        access_token="token",
        base_url="https://example.invalid",
        daily_price_path="/daily",
        token_path="/token",
        adjusted_price_flag="0",
        original_price_flag="1",
        request_timeout_seconds=1,
        retry=RetryConfig(attempts=2, backoff_seconds=0),
    )


if __name__ == "__main__":
    unittest.main()
