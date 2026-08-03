import json
import threading
import time

import httpx
import pytest

from ai_graph.jobs import classify_failure
from ai_graph.llm.aoai import AOAIResponsesClient
from ai_graph.llm.base import LLMClientError, LLMJsonRequest
from ai_graph.llm.concurrency_gate import (
    DEFAULT_MAX_WAIT_SECONDS,
    AOAIConcurrencyGate,
    AOAIGateBusyError,
    _max_wait_seconds_from_env,
)


def make_request() -> LLMJsonRequest:
    return LLMJsonRequest(
        schema_name="unit-test.v1",
        system_prompt="Return JSON only.",
        user_prompt="Return candidates.",
        task_type="unit_test",
    )


def completed_payload() -> dict:
    return {
        "id": "resp-1",
        "model": "test-model",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps({"ok": True})}],
            }
        ],
    }


def test_gate_never_admits_more_than_its_capacity() -> None:
    gate = AOAIConcurrencyGate(initial_capacity=2, min_capacity=1, max_capacity=2)
    peak = 0
    concurrent = 0
    counter_lock = threading.Lock()
    start = threading.Event()

    def worker() -> None:
        nonlocal peak, concurrent
        start.wait()
        with gate.acquire_slot(max_wait_seconds=5):
            with counter_lock:
                concurrent += 1
                peak = max(peak, concurrent)
            time.sleep(0.05)
            with counter_lock:
                concurrent -= 1

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    start.set()
    for thread in threads:
        thread.join(timeout=10)

    assert peak == 2
    assert gate.in_flight() == 0


def test_gate_gives_up_rather_than_queueing_forever() -> None:
    gate = AOAIConcurrencyGate(initial_capacity=1, min_capacity=1, max_capacity=1)

    with gate.acquire_slot(max_wait_seconds=5):
        started = time.monotonic()
        with pytest.raises(AOAIGateBusyError), gate.acquire_slot(max_wait_seconds=0.05):
            pass
        # The wait is bounded by the budget rather than by the holder finishing.
        assert time.monotonic() - started < 2


def test_gate_shrinks_when_the_provider_reports_a_nearly_spent_window() -> None:
    gate = AOAIConcurrencyGate(initial_capacity=4, min_capacity=1, max_capacity=8)

    gate.observe_rate_limit_headers(
        {"x-ratelimit-remaining-requests": "3", "x-ratelimit-limit-requests": "100"}
    )

    assert gate.current_capacity() == 3


def test_gate_shrinks_on_a_bare_exhausted_counter_without_a_limit_header() -> None:
    gate = AOAIConcurrencyGate(initial_capacity=3, min_capacity=1, max_capacity=8)

    gate.observe_rate_limit_headers({"x-ratelimit-remaining-requests": "0"})

    assert gate.current_capacity() == 2


def test_gate_ignores_a_large_remaining_count_it_cannot_put_in_context() -> None:
    gate = AOAIConcurrencyGate(initial_capacity=3, min_capacity=1, max_capacity=8)

    # No limit header, so there is no ratio to judge: a big absolute number must not be
    # mistaken for scarcity on a deployment that simply reports large counters.
    gate.observe_rate_limit_headers({"x-ratelimit-remaining-requests": "5000"})

    assert gate.current_capacity() == 3


def test_gate_never_shrinks_below_its_floor() -> None:
    gate = AOAIConcurrencyGate(initial_capacity=2, min_capacity=1, max_capacity=8)

    for _ in range(10):
        gate.observe_rate_limited_response()

    assert gate.current_capacity() == 1


def test_gate_grows_back_only_after_a_run_of_healthy_responses() -> None:
    gate = AOAIConcurrencyGate(
        initial_capacity=1,
        min_capacity=1,
        max_capacity=4,
        healthy_observations_to_grow=3,
    )

    gate.observe_rate_limit_headers({})
    gate.observe_rate_limit_headers({})
    assert gate.current_capacity() == 1

    gate.observe_rate_limit_headers({})
    assert gate.current_capacity() == 2


def test_a_single_rate_limit_resets_progress_toward_growing() -> None:
    gate = AOAIConcurrencyGate(
        initial_capacity=2,
        min_capacity=1,
        max_capacity=4,
        healthy_observations_to_grow=3,
    )

    gate.observe_rate_limit_headers({})
    gate.observe_rate_limit_headers({})
    gate.observe_rate_limited_response()
    gate.observe_rate_limit_headers({})
    gate.observe_rate_limit_headers({})

    # Shrunk to 1 by the rate limit, and the two healthy calls since are one short of the
    # three needed, so it has not climbed back yet.
    assert gate.current_capacity() == 1


def test_gate_serialises_provider_calls_made_from_separate_threads() -> None:
    gate = AOAIConcurrencyGate(initial_capacity=1, min_capacity=1, max_capacity=1)
    first_in_handler = threading.Event()
    release_first = threading.Event()
    handler_entries: list[str] = []
    entries_lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        with entries_lock:
            handler_entries.append("enter")
            is_first = len(handler_entries) == 1
        if is_first:
            first_in_handler.set()
            release_first.wait(timeout=5)
        return httpx.Response(200, json=completed_payload())

    def make_client() -> AOAIResponsesClient:
        return AOAIResponsesClient(
            responses_url="https://example.test/openai/responses",
            api_key="test-api-key",
            model="test-model",
            retry_backoff_seconds=0.0,
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            concurrency_gate=gate,
        )

    def call() -> None:
        make_client().generate_json(make_request())

    first = threading.Thread(target=call)
    first.start()
    assert first_in_handler.wait(timeout=5)

    second = threading.Thread(target=call)
    second.start()
    # The second request is parked on the gate, so it must not have reached the transport
    # while the first is still holding the only slot.
    time.sleep(0.2)
    with entries_lock:
        assert handler_entries == ["enter"]

    release_first.set()
    first.join(timeout=5)
    second.join(timeout=5)
    with entries_lock:
        assert handler_entries == ["enter", "enter"]


def test_a_saturated_gate_fails_the_call_without_sending_a_request() -> None:
    # The client does not pass a per-call budget, so the wait it inherits is the gate's
    # own - which is why this one has to be short for the test to finish.
    gate = AOAIConcurrencyGate(
        initial_capacity=1, min_capacity=1, max_capacity=1, max_wait_seconds=0.05
    )

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("request was sent despite no available slot")

    client = AOAIResponsesClient(
        responses_url="https://example.test/openai/responses",
        api_key="test-api-key",
        model="test-model",
        retry_backoff_seconds=0.0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        concurrency_gate=gate,
    )

    with gate.acquire_slot(max_wait_seconds=5), pytest.raises(AOAIGateBusyError):
        client._stream_with_retries(make_request())

    assert client.physical_http_post_count == 0


def test_a_rate_limited_response_lowers_capacity_for_later_calls() -> None:
    gate = AOAIConcurrencyGate(initial_capacity=3, min_capacity=1, max_capacity=8)
    responses = [
        httpx.Response(429, headers={"retry-after": "0"}, json={"error": "slow down"}),
        httpx.Response(200, json=completed_payload()),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    client = AOAIResponsesClient(
        responses_url="https://example.test/openai/responses",
        api_key="test-api-key",
        model="test-model",
        retry_backoff_seconds=0.0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        concurrency_gate=gate,
    )

    client.generate_json(make_request())

    assert client.physical_http_post_count == 2
    assert gate.current_capacity() == 2


def test_gate_busy_is_reported_as_capacity_rather_than_an_unknown_failure() -> None:
    diagnostic = classify_failure(AOAIGateBusyError("no capacity"), stage="analyzing")

    assert diagnostic.category == "infrastructure_failure"
    assert diagnostic.subcause == "aoai_capacity_exhausted"
    assert diagnostic.retryable is True


def test_gate_busy_is_an_llm_client_error_so_existing_handlers_still_catch_it() -> None:
    assert issubclass(AOAIGateBusyError, LLMClientError)


@pytest.mark.parametrize("raw", ["", "not-a-number", "0", "-5"])
def test_unusable_wait_budgets_fall_back_to_the_default(raw: str) -> None:
    assert _max_wait_seconds_from_env({"AI_AOAI_GATE_MAX_WAIT_SECONDS": raw}) == (
        DEFAULT_MAX_WAIT_SECONDS
    )


def test_a_configured_wait_budget_is_honoured() -> None:
    assert _max_wait_seconds_from_env({"AI_AOAI_GATE_MAX_WAIT_SECONDS": "45"}) == 45.0
