from __future__ import annotations

from pathlib import Path

from ai_graph.graph import run_analysis
from ai_graph.schemas import EnvelopeStatus

from screening_pipeline_test_support import (
    BOLLINGER_LOWER_REENTRY_PROMPT,
    evaluate_bollinger_lower_reentry,
)


def test_bollinger_lower_reentry_qa_detects_rsi_only_semantic_drift() -> None:
    envelope = run_analysis(BOLLINGER_LOWER_REENTRY_PROMPT, trace_id="screen-bollinger-lower")

    verdict = evaluate_bollinger_lower_reentry(envelope)

    assert envelope.status == EnvelopeStatus.READY
    assert verdict["verdict"] == "fail"
    assert verdict["failure_cause"] == "semantic_drift"
    assert "rsi" in verdict["semantic_slots"]["indicator"]
    assert "bollinger" not in " ".join(verdict["semantic_slots"]["indicator"])


def test_qa_evaluator_does_not_import_profile_ordering_as_oracle() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden_profile = "_strategy" + "_profile"
    forbidden_builder = "build_strategy" + "_spec("

    assert forbidden_profile not in source
    assert forbidden_builder not in source
