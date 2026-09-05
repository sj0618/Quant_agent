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


def test_live_explicit_rule_without_a_test_window_enters_research_before_signing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A user-set entry/exit rule still needs a researched sample window if omitted."""

    from ai_graph import research_contract

    calls: list[dict[str, object]] = []

    def stop_after_capture(**kwargs: object) -> None:
        calls.append(kwargs)
        raise RuntimeError("researched period selected")

    monkeypatch.setattr(research_contract, "_live_parser_enabled", lambda: True)
    monkeypatch.setattr(research_contract, "_build_researched_draft", stop_after_capture)

    with pytest.raises(RuntimeError, match="researched period selected"):
        build_rule_draft(
            query="RSI 30 이하일 때 매수하고 RSI 70 이상일 때 매도",
            user_id="user-1",
            signer=_signer(),
            use_llm=True,
        )

    assert calls and calls[0]["query"] == "RSI 30 이하일 때 매수하고 RSI 70 이상일 때 매도"


def test_explicit_backtest_window_keeps_an_explicit_rule_out_of_extra_research(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_graph import research_contract

    monkeypatch.setattr(research_contract, "_live_parser_enabled", lambda: True)
    monkeypatch.setattr(
        research_contract,
        "_build_researched_draft",
        lambda **_kwargs: pytest.fail("explicit sample window must not be replaced"),
    )

    draft = build_rule_draft(
        query="RSI 30 이하일 때 매수하고 RSI 70 이상일 때 매도, 최근 2년 백테스트",
        user_id="user-1",
        signer=_signer(),
        use_llm=True,
    )

    assert draft.is_executable


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


def _provider_failure_draft(monkeypatch):
    from ai_graph import research_contract
    from ai_graph.nodes.strategy_research import StrategyResearchError

    def _raise_provider_failure(**_kwargs: object) -> None:
        raise StrategyResearchError(
            "strategy research provider is temporarily unavailable",
            cause_code="research_provider_failure",
        )

    monkeypatch.setattr(research_contract, "_build_researched_draft", _raise_provider_failure)
    return build_rule_draft(
        query="유명한 퀀트전략으로 검증해줘",
        user_id="user-1",
        signer=_signer(),
        use_llm=True,
    )


def test_a_research_provider_outage_asks_for_a_retry_not_a_rewrite(monkeypatch) -> None:
    """A transient AOAI failure told the user their strategy could not be backtested
    here and offered three unrelated ways to rewrite it."""

    from ai_graph.research_contract import RESEARCH_PROVIDER_RETRY_MESSAGE

    draft = _provider_failure_draft(monkeypatch)

    assert draft.retry_only is True
    assert draft.clarification_required is True
    assert draft.is_executable is False
    assert draft.explanation == RESEARCH_PROVIDER_RETRY_MESSAGE
    # The strategy was never found unsupported; only the provider failed.
    assert draft.unsupported_conditions == []
    assert [choice.label for choice in draft.clarifications] == ["다시 시도"]


def test_raw_query_jobs_propagate_provider_outages_to_their_typed_failure_handler(monkeypatch) -> None:
    from ai_graph import research_contract
    from ai_graph.nodes.strategy_research import StrategyResearchError

    def _raise_provider_failure(**_kwargs: object) -> None:
        raise StrategyResearchError(
            "strategy research provider is temporarily unavailable",
            cause_code="research_provider_failure",
        )

    monkeypatch.setattr(research_contract, "_build_researched_draft", _raise_provider_failure)

    with pytest.raises(StrategyResearchError, match="temporarily unavailable"):
        build_rule_draft(
            query="유명한 퀀트전략으로 검증해줘",
            user_id="user-1",
            signer=_signer(),
            use_llm=True,
            propagate_provider_failure=True,
        )


def test_a_provider_outage_envelope_offers_one_retry_option(monkeypatch) -> None:
    from ai_graph.api import _clarification_envelope
    from ai_graph.research_contract import RESEARCH_PROVIDER_RETRY_MESSAGE
    from ai_graph.schemas import EnvelopeStatus

    draft = _provider_failure_draft(monkeypatch)

    envelope = _clarification_envelope(
        draft, query="유명한 퀀트전략으로 검증해줘", trace_id="trace-provider"
    )

    assert envelope.status is EnvelopeStatus.NEED_CLARIFICATION
    assert envelope.retryable is True
    assert envelope.user_payload.message == RESEARCH_PROVIDER_RETRY_MESSAGE
    assert [option.label for option in envelope.user_payload.options] == ["다시 시도"]
    assert "사용 가능한 지표로 조건 수정" not in envelope.model_dump_json()


def test_a_capability_gap_keeps_its_own_wording_and_choices(monkeypatch) -> None:
    from ai_graph import research_contract
    from ai_graph.api import _clarification_envelope
    from ai_graph.nodes.strategy_research import StrategyResearchError

    def _raise_capability_gap(**_kwargs: object) -> None:
        raise StrategyResearchError("cointegration_score is not a supported metric")

    monkeypatch.setattr(research_contract, "_build_researched_draft", _raise_capability_gap)
    draft = build_rule_draft(
        query="공적분 페어 트레이딩으로 검증해줘",
        user_id="user-1",
        signer=_signer(),
        use_llm=True,
    )

    envelope = _clarification_envelope(
        draft, query="공적분 페어 트레이딩으로 검증해줘", trace_id="trace-gap"
    )

    assert draft.retry_only is False
    assert draft.explanation == "전략 의미는 조사했지만 현재 서버가 같은 규칙으로 백테스트할 수 없습니다."
    assert draft.unsupported_conditions
    assert "사용 가능한 지표로 조건 수정" in envelope.model_dump_json()
