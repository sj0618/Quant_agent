from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ai_graph.research_contract import (
    CanonicalRuleV1,
    DraftTokenValidationError,
    InMemoryDraftNonceRegistry,
    ResearchCandidateV1,
    ResearchDataProvenanceV1,
    ResearchDevPreviewV1,
    ResearchReadyV1,
    RuleConditionV1,
    RuleDraftSigner,
    build_rule_draft,
    unavailable_result_for_unverified_job,
)


def _signer() -> RuleDraftSigner:
    return RuleDraftSigner("test-rule-draft-secret", key_version="test-v1")


def _complete_rule() -> CanonicalRuleV1:
    return CanonicalRuleV1(
        entry_conditions=[RuleConditionV1(metric="rsi", comparator="lte", value=30, role="entry")],
        exit_conditions=[RuleConditionV1(metric="rsi", comparator="gte", value=70, role="exit")],
    )


def test_deterministic_parse_returns_an_editable_signed_rule_without_raw_input() -> None:
    query = "RSI가 30 이하이고 RSI가 70 이상인 일반 조건식을 검토해 주세요."

    draft = build_rule_draft(query=query, user_id="user-1", signer=_signer())

    assert draft.kind == "rule_draft"
    assert draft.is_executable is True
    assert draft.canonical_rule == _complete_rule()
    assert draft.clarifications == []
    assert draft.authoring_method == "deterministic"
    assert query not in draft.model_dump_json()
    assert "매수" not in draft.editable_summary
    assert "매도" not in draft.editable_summary


def test_incomplete_rule_has_at_most_three_explained_choices_and_stays_non_executable() -> None:
    query = "RSI가 30 이하인 KRX 종목을 검토해 주세요."

    draft = build_rule_draft(query=query, user_id="user-1", signer=_signer())

    assert draft.is_executable is False
    assert draft.canonical_rule is not None
    assert len(draft.clarifications) == 1
    assert all(choice.label and choice.reason for choice in draft.clarifications)
    assert query not in draft.model_dump_json()


def test_signed_draft_rejects_tampering_wrong_user_and_expiry() -> None:
    signer = _signer()
    issued_at = datetime(2026, 8, 20, tzinfo=UTC)
    draft = build_rule_draft(
        query="RSI 30 이하, RSI 70 이상",
        user_id="user-1",
        signer=signer,
        now=issued_at,
    )
    assert draft.canonical_rule is not None

    nonce = signer.verify(
        token=draft.draft_token,
        rule=draft.canonical_rule,
        user_id="user-1",
        now=issued_at + timedelta(seconds=1),
    )
    assert nonce

    with pytest.raises(DraftTokenValidationError, match="draft_user_mismatch"):
        signer.verify(
            token=draft.draft_token,
            rule=draft.canonical_rule,
            user_id="user-2",
            now=issued_at + timedelta(seconds=1),
        )
    with pytest.raises(DraftTokenValidationError, match="draft_rule_mismatch"):
        signer.verify(
            token=draft.draft_token,
            rule=CanonicalRuleV1(
                entry_conditions=[
                    RuleConditionV1(metric="rsi", comparator="lte", value=25, role="entry")
                ],
                exit_conditions=draft.canonical_rule.exit_conditions,
            ),
            user_id="user-1",
            now=issued_at + timedelta(seconds=1),
        )
    with pytest.raises(DraftTokenValidationError, match="draft_expired"):
        signer.verify(
            token=draft.draft_token,
            rule=draft.canonical_rule,
            user_id="user-1",
            now=issued_at + timedelta(minutes=11),
        )


def test_draft_nonce_registry_only_allows_one_execution_per_user_nonce() -> None:
    registry = InMemoryDraftNonceRegistry()

    assert registry.consume(user_id="user-1", nonce="draft-1") is True
    assert registry.consume(user_id="user-1", nonce="draft-1") is False
    assert registry.consume(user_id="user-2", nonce="draft-1") is True


def test_ready_result_requires_postgres_eod_provenance_and_matching_candidates() -> None:
    provenance = ResearchDataProvenanceV1(
        source="postgres",
        as_of="2026-08-19",
        retrieved_at=datetime(2026, 8, 20, tzinfo=UTC),
        freshness="eod_current",
        universe_count=100,
        candidate_count=1,
    )
    ready = ResearchReadyV1(
        result_id="result-1",
        rule_version="research-rule-draft.v1",
        authoring_method="deterministic",
        provenance=provenance,
        candidates=[
            ResearchCandidateV1(
                ticker="005930",
                name="삼성전자",
                as_of="2026-08-19",
                matched_conditions=["RSI 30 이하"],
            )
        ],
    )

    assert ready.status == "ready"
    with pytest.raises(ValidationError):
        ResearchDataProvenanceV1(
            source="fixture",
            as_of="2026-08-19",
            retrieved_at=datetime(2026, 8, 20, tzinfo=UTC),
            freshness="eod_current",
            universe_count=100,
            candidate_count=0,
        )


def test_unverified_jobs_only_project_to_a_safe_unavailable_result() -> None:
    result = unavailable_result_for_unverified_job(job_id="job-1")

    assert result.status == "unavailable"
    assert result.result_id == "research:job-1"
    assert "fixture" not in result.model_dump_json()


def test_dev_preview_is_explicitly_limited_to_fixture_rendering() -> None:
    result = ResearchDevPreviewV1(
        result_id="fixture-preview",
        rule_version="research-rule-draft.v1",
        authoring_method="deterministic",
        reason_code="development_fixture_only",
        explanation="renderer verification only",
    )

    assert result.status == "dev_preview"
    assert result.reason_code == "development_fixture_only"


def test_research_failure_reason_over_field_limit_stays_a_no_run_draft(monkeypatch) -> None:
    # Regression: the no-run clarification path truncated the researcher error to 300
    # characters while ``UnsupportedStrategyConditionV1.reason`` only allows 240, so any
    # longer message raised a ValidationError *while building the message that reports
    # the failure*.  That surfaced to users as an opaque "AI 파이프라인 계약 검증에
    # 실패했습니다" instead of the intended clarification.
    from ai_graph import research_contract
    from ai_graph.nodes.strategy_research import StrategyResearchError

    def _raise_long(**_kwargs: object) -> None:
        raise StrategyResearchError("전략 연구 실패: " + "가" * 300)

    monkeypatch.setattr(research_contract, "_build_researched_draft", _raise_long)

    draft = build_rule_draft(query="fgdgd", user_id="user-1", signer=_signer(), use_llm=True)

    assert draft.clarification_required
    assert not draft.is_executable
    assert draft.unsupported_conditions
    assert all(len(item.reason) <= 240 for item in draft.unsupported_conditions)
