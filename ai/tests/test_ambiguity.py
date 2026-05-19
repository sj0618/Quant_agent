import pytest
from pydantic import ValidationError

from ai_graph.nodes.ambiguity import AmbiguityResult, ambiguity_node, classify_ambiguity


def test_concrete_krx_strategy_is_confirmed():
    result = classify_ambiguity("KRX 반도체 후보 상위 20개에서 RSI 30 이하 매수, 중립 위험")

    assert result.status == "confirmed"
    assert result.is_ambiguous is False
    assert result.missing_fields == []
    assert result.trace_id
    assert result.debug_ref.startswith("ambiguity:")


def test_missing_fields_generate_questions_and_assumptions():
    result = classify_ambiguity("좋은 종목을 찾아줘")

    assert result.status == "provisional"
    assert result.is_ambiguous is True
    assert "market" in result.missing_fields
    assert result.clarification_questions
    assert result.assumptions


def test_unsupported_asset_class_is_rejected():
    result = classify_ambiguity("crypto 선물 모멘텀 전략")

    assert result.status == "rejected"
    assert "unsupported_asset_class" in result.ambiguity_flags


def test_ambiguity_node_preserves_trace_id():
    output = ambiguity_node({"trace_id": "trace-1", "user_query": "KRX 반도체 RSI 매수 중립 위험 상위 후보"})

    assert output["trace_id"] == "trace-1"
    assert output["ambiguity"]["debug_ref"] == "ambiguity:trace-1"


def test_ambiguity_result_rejects_internal_payload_leak():
    with pytest.raises(ValidationError):
        AmbiguityResult(
            trace_id="trace",
            debug_ref="ambiguity:trace",
            status="confirmed",
            is_ambiguous=False,
            fit_confidence=0.9,
            normalized_query="KRX RSI",
            internal_payload={"raw": True},
        )
