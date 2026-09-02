from __future__ import annotations

import json

import httpx
import pytest

import ai_graph.staging_pipeline_gate as staging_pipeline_gate
from ai_graph.staging_pipeline_gate import (
    StagingGateConfig,
    StagingGateError,
    run_gate,
)


def _config() -> StagingGateConfig:
    return StagingGateConfig(
        api_base_url="https://staging.example.test/ai-api",
        backend_api_base_url="https://staging.example.test/api/v1",
        fe_origin="https://staging.example.test",
        expected_revision="a" * 40,
        account_token="account-secret",
        evidence_token="operator-secret",
        session_cookie="qa_session=staging-session",
        csrf_token="staging-csrf",
    )


def _ready_job(job_id: str) -> dict[str, object]:
    return {
        "job_id": job_id,
        "status": "completed",
        "result": {
            "status": "ready",
            "failure_cause": None,
            "freshness_evidence": {
                "source": "postgres",
                "as_of": "2026-08-28",
                "no_recommendation": False,
            },
            "user_payload": {
                "performance": {
                    "availability": "available",
                    "performance": {
                        "selected_candidate_id": "candidate-rsi-14-30-70",
                        "metrics": {
                            "total_return": 0.127,
                            "max_drawdown": -0.083,
                            "sharpe_ratio": 1.21,
                            "candidates_evaluated": 2,
                        },
                    },
                    "method_manifest": {
                        "start_date": "2023-01-02",
                        "end_date": "2026-08-28",
                        "observations": 500,
                        "trades": 12,
                        "cost_tax_slippage_liquidity": "kr-equity-v1",
                        "historical_simulation_warning": "과거 시뮬레이션은 미래 수익을 보장하지 않습니다.",
                    },
                    "limitations": ["과거 성과는 미래 수익을 보장하지 않습니다."],
                },
                "report": {
                    "web_projection": {
                        "title": "RSI 전략 검증 보고서",
                        "summary": "비용을 반영한 과거 검증 결과입니다.",
                        "sections": [
                            {"id": "performance", "items": {"availability": "available"}},
                            {"id": "risk", "items": []},
                        ],
                    }
                },
            },
        },
    }


def _draft() -> dict[str, object]:
    return {
        "kind": "rule_draft",
        "is_executable": True,
        "clarification_required": False,
        "unsupported_conditions": [],
        "parse_token": "p" * 32,
        "spec_version": "strategy-execution-spec.v1",
        "spec_hash": "c" * 64,
        "strategy_execution_spec": {
            "market": "KRX",
            "timeframe": "daily",
            "entry_conditions": [{"metric": "rsi", "comparator": "lte", "value": 30, "lookback": 14, "role": "entry"}],
            "exit_conditions": [{"metric": "rsi", "comparator": "gte", "value": 70, "lookback": 14, "role": "exit"}],
        },
    }


def _client(*, successful_aoai_calls: int = 1, invalid_parse: bool = False) -> tuple[httpx.Client, list[dict[str, object]]]:
    created = 0
    confirmed_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal created
        if request.url.path == "/ai-api/api-status":
            return httpx.Response(200, json={"deployment_revision": "a" * 40, "job_store": {"active_mode": "persistent", "fallback": False, "dsn_configured": True}})
        if request.url.path == "/ai-api/readiness":
            return httpx.Response(200, json={"status": "ready", "checks": [{"name": name, "ready": True} for name in ("durable_job_store", "migration_revision", "live_provider_configuration")]})
        if request.method == "POST" and request.url.path == "/ai-api/api/strategies/parse":
            assert request.headers["authorization"] == "Bearer account-secret"
            draft = _draft()
            if invalid_parse:
                draft["clarification_required"] = True
            return httpx.Response(200, json=draft)
        if request.method == "POST" and request.url.path == "/ai-api/analysis-jobs":
            confirmed_payloads.append(json.loads(request.content))
            created += 1
            return httpx.Response(201, json={"job_id": f"job-{created}"})
        if request.method == "GET" and request.url.path.startswith("/ai-api/analysis-jobs/"):
            return httpx.Response(200, json=_ready_job(request.url.path.rsplit("/", 1)[-1]))
        if request.method == "POST" and request.url.path == "/api/v1/runs":
            assert request.headers["cookie"] == "qa_session=staging-session"
            assert request.headers["x-csrf-token"] == "staging-csrf"
            return httpx.Response(201, json={"id": f"run-{created}"})
        if request.method == "POST" and request.url.path.startswith("/api/v1/runs/run-"):
            return httpx.Response(200, json={"status": "completed"})
        if request.method == "GET" and request.url.path.startswith("/ai-api/_operator/"):
            job_id = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"job_id": job_id, "execution_spec_version": "strategy-execution-spec.v1", "execution_spec_hash": "c" * 64, "analysis_result_id": f"result-{job_id}", "manifest_hash": "b" * 64, "source": "postgres", "as_of": "2026-08-28", "observations": 500, "candidate_count": 2, "successful_aoai_calls": successful_aoai_calls, "immutable_trigger_present": True})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler)), confirmed_payloads


def test_gate_runs_three_real_contract_shapes_and_keeps_tokens_out_of_evidence() -> None:
    client, confirmed = _client()

    evidence = run_gate(_config(), client=client, clock=lambda: 1.0, sleep=lambda _seconds: None)

    assert len(evidence) == 3
    assert [item.execution_spec_version for item in evidence] == ["strategy-execution-spec.v1"] * 3
    assert all(item.successful_aoai_calls == 1 for item in evidence)
    assert all(item.elapsed_seconds == 0.0 for item in evidence)
    assert len(confirmed) == 3
    assert all("query" not in item for item in confirmed)
    assert all(item["spec_version"] == "strategy-execution-spec.v1" for item in confirmed)
    assert "account-secret" not in repr(_config())


def test_gate_rejects_a_parse_that_requires_user_clarification_before_a_job_is_created() -> None:
    client, confirmed = _client(invalid_parse=True)

    with pytest.raises(StagingGateError, match="clarification"):
        run_gate(_config(), client=client, clock=lambda: 1.0, sleep=lambda _seconds: None)

    assert confirmed == []


def test_gate_requires_a_real_successful_aoai_call() -> None:
    client, _confirmed = _client(successful_aoai_calls=0)

    with pytest.raises(StagingGateError, match="successful AOAI calls"):
        run_gate(_config(), client=client, clock=lambda: 1.0, sleep=lambda _seconds: None)


def test_gate_reports_parse_validation_field_without_echoing_strategy_text() -> None:
    response = httpx.Response(
        422,
        json={
            "detail": [
                {
                    "loc": ["body", "natural_language"],
                    "msg": "field required",
                    "input": "secret strategy text",
                }
            ]
        },
    )

    with pytest.raises(StagingGateError) as error:
        staging_pipeline_gate._json_response(response, "strategy parse")

    assert "request_validation:natural_language" in str(error.value)
    assert "secret strategy text" not in str(error.value)


@pytest.mark.parametrize("url_key", ["AI_STAGING_AI_API_BASE_URL", "AI_STAGING_BACKEND_API_BASE_URL"])
def test_gate_rejects_the_public_host_before_any_job_is_created(url_key: str) -> None:
    env = {
        "AI_STAGING_AI_API_BASE_URL": "https://staging.example.test/ai-api",
        "AI_STAGING_BACKEND_API_BASE_URL": "https://staging.example.test/api/v1",
        "AI_STAGING_FE_ORIGIN": "https://staging.example.test",
        "AI_STAGING_EXPECTED_REVISION": "a" * 40,
        "AI_STAGING_ACCOUNT_TOKEN": "account-secret",
        "AI_STAGING_EVIDENCE_PROBE_TOKEN": "operator-secret",
        "AI_STAGING_SESSION_COOKIE": "qa_session=staging-session",
        "AI_STAGING_CSRF_TOKEN": "staging-csrf",
    }
    env[url_key] = "https://qt-agent.kro.kr/ai-api"

    with pytest.raises(StagingGateError, match="public production host"):
        StagingGateConfig.from_env(env)


def test_main_json_keeps_the_required_evidence_but_not_fake_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _config()
    client, _confirmed = _client()
    monkeypatch.setattr(staging_pipeline_gate.StagingGateConfig, "from_env", classmethod(lambda _cls: config))
    monkeypatch.setattr(staging_pipeline_gate, "run_gate", lambda _config: run_gate(config, client=client, clock=lambda: 1.0, sleep=lambda _seconds: None))

    assert staging_pipeline_gate.main() == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["run_count"] == 3
    assert payload["runs"][0]["successful_aoai_calls"] == 1
    for secret in ("account-secret", "operator-secret", "staging-session", "staging-csrf"):
        assert secret not in output
