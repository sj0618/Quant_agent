from __future__ import annotations

import os

import pytest


def test_live_local_api_runs_prompt_manifest_when_enabled() -> None:
    if os.environ.get("SCREENING_PIPELINE_LIVE_API") != "1":
        pytest.skip("live local API verification is opt-in; set SCREENING_PIPELINE_LIVE_API=1")

    import httpx

    base_url = os.environ.get("VITE_AI_API_BASE_URL") or os.environ.get("AI_API_BASE_URL")
    if not base_url:
        pytest.skip("AI API base URL is not configured")

    response = httpx.get(f"{base_url.rstrip('/')}/api-status", timeout=5.0)
    assert response.status_code == 200
