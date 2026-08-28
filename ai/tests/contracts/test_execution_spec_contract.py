"""CORE-CONTRACT-01: the frozen public execution contract.

These are contract tests, not unit tests. Each one pins a promise the server makes to a
browser that will send a spec back, so a change that breaks one here is a change that
breaks a deployed client.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import TypeAdapter, ValidationError

from ai_graph.research_contract import (
    CanonicalRuleV1,
    RuleConditionV1,
    ScopeRefusalV1,
    UnsupportedScopeV1,
)
from ai_graph.schemas import (
    EXECUTION_SPEC_SCHEMA_VERSION,
    ParseClarificationV1,
    ParseOutcomeV1,
    ParseValidatedV1,
    StrategyExecutionSpecV1,
    build_execution_spec,
    compute_spec_hash,
    execution_idempotency_key,
    find_secret_leaks,
    job_document_schema_version,
)

OUTCOME = TypeAdapter(ParseOutcomeV1)


def _rule() -> CanonicalRuleV1:
    return CanonicalRuleV1(
        entry_conditions=[
            RuleConditionV1(metric="rsi", comparator="lte", value=30.0, role="entry")
        ],
        exit_conditions=[
            RuleConditionV1(metric="rsi", comparator="gte", value=70.0, role="exit")
        ],
    )


def _spec(**overrides) -> StrategyExecutionSpecV1:
    kwargs = {
        "rule": _rule(),
        "period_start": "2024-01-02",
        "period_end": "2024-12-30",
        "universe_policy_id": "pit-top200",
        "cost_policy_id": "krx-default",
        "oos_policy_id": "walkforward-1m",
        "benchmark_symbol": "KOSPI",
    }
    kwargs.update(overrides)
    return build_execution_spec(**kwargs)


def test_spec_hash_is_stable_across_key_order_and_whitespace() -> None:
    """Two encodings of the same content must hash the same.

    A client that reserializes the spec - which every JSON round trip does - must not
    produce a different identity for the same strategy.
    """

    spec = _spec()
    reordered = dict(reversed(list(spec.model_dump(mode="json").items())))
    assert compute_spec_hash(reordered) == spec.spec_hash


def test_a_tampered_spec_hash_is_rejected() -> None:
    """The server recomputes rather than trusting what the client sent."""

    payload = _spec().model_dump(mode="json")
    payload["spec_hash"] = "0" * 64
    with pytest.raises(ValidationError):
        StrategyExecutionSpecV1.model_validate(payload)


def test_tampering_with_content_invalidates_the_hash() -> None:
    payload = _spec().model_dump(mode="json")
    payload["benchmark_symbol"] = "KOSDAQ"
    with pytest.raises(ValidationError):
        StrategyExecutionSpecV1.model_validate(payload)


def test_changing_any_input_changes_the_hash() -> None:
    assert _spec().spec_hash != _spec(cost_policy_id="zero-cost").spec_hash


def test_unknown_fields_are_refused() -> None:
    payload = _spec().model_dump(mode="json")
    payload["leverage"] = 3
    with pytest.raises(ValidationError):
        StrategyExecutionSpecV1.model_validate(payload)


def test_a_spec_without_both_condition_roles_is_not_executable() -> None:
    half = CanonicalRuleV1(
        entry_conditions=[RuleConditionV1(metric="rsi", comparator="lte", value=30.0, role="entry")]
    )
    with pytest.raises(ValidationError):
        build_execution_spec(
            rule=half,
            period_start="2024-01-02",
            period_end="2024-12-30",
            universe_policy_id="pit-top200",
            cost_policy_id="krx-default",
            oos_policy_id="walkforward-1m",
            benchmark_symbol="KOSPI",
        )


def test_an_inverted_period_is_refused() -> None:
    with pytest.raises(ValidationError):
        build_execution_spec(
            rule=_rule(),
            period_start="2024-12-30",
            period_end="2024-01-02",
            universe_policy_id="pit-top200",
            cost_policy_id="krx-default",
            oos_policy_id="walkforward-1m",
            benchmark_symbol="KOSPI",
        )


def test_every_parse_outcome_branch_discriminates_on_kind() -> None:
    validated = ParseValidatedV1(
        spec=_spec(),
        spec_token="t" * 32,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    clarification = ParseClarificationV1(
        editable_summary="기간이 명시되지 않았습니다.",
        clarifications=[{"label": "최근 1년", "reason": "기간이 필요합니다."}],
    )
    refusal = ScopeRefusalV1(
        reason_code="personalized_investment_request",
        explanation="개인 맞춤 투자 판단은 제공하지 않습니다.",
        general_example="RSI 30 이하 진입 규칙",
        guidance="일반 규칙으로 다시 작성해 주세요.",
    )
    unsupported = UnsupportedScopeV1(
        reason_code="unsupported_asset_family",
        explanation="해당 자산군은 지원하지 않습니다.",
        general_example="KRX 상장 보통주",
        guidance="지원 자산군으로 다시 시도해 주세요.",
    )

    for outcome, kind in (
        (validated, "validated"),
        (clarification, "clarification"),
        (refusal, "scope_refusal"),
        (unsupported, "unsupported_scope"),
    ):
        restored = OUTCOME.validate_python(outcome.model_dump(mode="json"))
        assert restored.kind == kind
        assert type(restored) is type(outcome)


def test_only_the_validated_branch_carries_a_spec() -> None:
    """Job creation reads `spec` off the outcome; no other branch may supply one."""

    for model in (ParseClarificationV1, ScopeRefusalV1, UnsupportedScopeV1):
        assert "spec" not in model.model_fields


def test_a_clarification_offers_between_one_and_three_choices() -> None:
    choice = {"label": "최근 1년", "reason": "기간이 필요합니다."}
    with pytest.raises(ValidationError):
        ParseClarificationV1(editable_summary="요약", clarifications=[])
    with pytest.raises(ValidationError):
        ParseClarificationV1(editable_summary="요약", clarifications=[choice] * 4)


def test_no_public_outcome_serializes_a_forbidden_key() -> None:
    validated = ParseValidatedV1(
        spec=_spec(),
        spec_token="t" * 32,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    assert find_secret_leaks(validated.model_dump(mode="json")) == []


def test_find_secret_leaks_names_the_path_it_found() -> None:
    """A guard nobody can debug gets deleted, so it reports where rather than whether."""

    leaks = find_secret_leaks({"outer": {"dsn": "postgres://x"}, "list": [{"authorization": "b"}]})
    assert leaks == ["$.outer.dsn", "$.list[0].authorization"]


def test_idempotency_is_independent_of_spec_content() -> None:
    """Running the same strategy twice on purpose must not be deduped as a replay."""

    first, second = _spec(), _spec()
    assert first.spec_hash == second.spec_hash
    assert execution_idempotency_key("u1", "req-a") != execution_idempotency_key("u1", "req-b")


def test_the_same_client_key_from_different_users_is_a_different_request() -> None:
    assert execution_idempotency_key("u1", "req-a") != execution_idempotency_key("u2", "req-a")


def test_an_idempotency_key_requires_both_parts() -> None:
    with pytest.raises(ValueError):
        execution_idempotency_key("", "req-a")
    with pytest.raises(ValueError):
        execution_idempotency_key("u1", "  ")


def test_dual_read_treats_an_unversioned_document_as_v1() -> None:
    """Rows written before the field exists must stay readable, not raise."""

    assert job_document_schema_version({}) == "v1"
    assert job_document_schema_version({"schema_version": "something-else"}) == "v1"
    assert (
        job_document_schema_version({"schema_version": EXECUTION_SPEC_SCHEMA_VERSION})
        == EXECUTION_SPEC_SCHEMA_VERSION
    )
