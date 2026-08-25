import os

import pytest

from ai_graph.llm.base import LLMJsonRequest
from ai_graph.llm.factory import create_llm_client


@pytest.mark.skipif(
    os.environ.get("AI_AOAI_LIVE_TEST") != "1"
    or not os.environ.get("AI_AOAI_RESPONSES_URL")
    or not os.environ.get("AI_AOAI_API_KEY")
    or not os.environ.get("AI_AOAI_MODEL"),
    reason="set AI_AOAI_LIVE_TEST=1 and AOAI env values to run live AOAI smoke test",
)
def test_live_aoai_responses_client_smoke() -> None:
    env = {**os.environ, "AI_LLM_PROVIDER": "aoai"}
    client = create_llm_client(env)

    result = client.generate_json(
        LLMJsonRequest(
            schema_name="live-smoke.v1",
            system_prompt="Return only JSON.",
            user_prompt='Return exactly this JSON object: {"ok": true}',
        )
    )

    assert result["ok"] is True
