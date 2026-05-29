from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from ai_graph.schemas import APIEnvelope

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_ROOT_ENV = "OMX_SCREENING_PLAN_ROOT"
LEADER_CWD_ENV = "OMX_TEAM_LEADER_CWD"
PRD_NAME = "prd-screening-pipeline-node-refinement.md"
TEST_SPEC_NAME = "test-spec-screening-pipeline-node-refinement.md"
INTERNAL_LEAK_TOKENS = (
    "AI_DATABASE_DSN",
    "DATABASE_URL",
    ".env",
    "api key",
    "raw LLM prompts",
    "raw node outputs",
    "raw internal payload",
)
FORBIDDEN_DB_REQUIREMENTS = (
    "new DB table",
    "new DB column",
    "common-server schema edit",
    "DB-team prerequisite",
)
REQUIRED_DATA_REQUIREMENT_FIELDS = {
    "family",
    "required",
    "availability",
    "owner",
    "proxy_allowed",
    "proxy_used",
    "proxy_disclosure",
    "preferred_source",
    "fallback_sources",
    "freshness_requirement",
    "evidence_ref",
}
REQUIRED_SOURCE_USAGE_FIELDS = {
    "source_type",
    "query",
    "retrieved_at",
    "source_refs",
    "confidence",
    "freshness_status",
    "fallback_used",
    "evidence_ref",
}
FAILURE_FIELDS = {
    "failure_category",
    "failure_subcause",
    "failure_stage",
    "failure_owner",
    "retryable",
    "evidence_refs",
}
FAILURE_CATEGORIES = {
    "infrastructure_failure",
    "semantic_failure",
    "data_gap",
    "clarification_failure",
    "ui_failure",
    "debug_failure",
    "unknown_failure",
}
ALLOWED_SOURCE_TYPES = {
    "internal_db",
    "krx",
    "dart",
    "aoai_web_search",
    "analyst_evidence",
    "manual_or_future_provider",
}
BOLLINGER_LOWER_REENTRY_PROMPT = "볼린저 밴드 하단을 이탈했다가 종가가 하단 밴드 위로 재진입한 KOSPI200 종목을 찾아줘"


def _candidate_plan_roots() -> list[Path]:
    roots = [REPO_ROOT / ".omx" / "plans"]
    if os.environ.get(PLAN_ROOT_ENV):
        roots.append(Path(os.environ[PLAN_ROOT_ENV]))
    if os.environ.get(LEADER_CWD_ENV):
        roots.append(Path(os.environ[LEADER_CWD_ENV]) / ".omx" / "plans")
    return roots


def plan_path(name: str) -> Path:
    for root in _candidate_plan_roots():
        path = root / name
        if path.exists():
            return path
    searched = ", ".join(str(root) for root in _candidate_plan_roots())
    pytest.skip(f"screening pipeline plan document not available: {name}; searched {searched}")


def plan_text(name: str) -> str:
    return plan_path(name).read_text(encoding="utf-8")


def assert_has_all(text: str, required_terms: set[str] | tuple[str, ...]) -> None:
    missing = [term for term in required_terms if term not in text]
    assert not missing, f"missing required PRD/test-spec terms: {missing}"


def assert_public_text_is_redacted(text: str) -> None:
    lowered = text.lower()
    leaked = [token for token in INTERNAL_LEAK_TOKENS if token.lower() in lowered]
    assert not leaked, f"public-safe text leaked internal tokens: {leaked}"


def semantic_slots_from_envelope(envelope: APIEnvelope) -> dict[str, list[str]]:
    spec = envelope.strategy_spec
    if spec is None:
        return {"indicator": [], "event": [], "price_basis": [], "action": []}
    conditions = [condition.left.lower() for condition in spec.entry_conditions]
    indicators = [indicator.lower() for indicator in spec.indicators]
    descriptions = [condition.description or "" for condition in spec.entry_conditions]
    joined = " ".join([*conditions, *indicators, *descriptions]).lower()
    return {
        "indicator": indicators,
        "event": ["lower_band_reentry"] if "reentry" in joined or "재진입" in joined else [],
        "price_basis": ["close"] if "close" in joined or "종가" in joined else [],
        "action": ["reentry"] if "reentry" in joined or "재진입" in joined else [],
    }


def evaluate_bollinger_lower_reentry(envelope: APIEnvelope) -> dict[str, Any]:
    slots = semantic_slots_from_envelope(envelope)
    indicators = set(slots["indicator"])
    observed = {
        *("bollinger" for item in indicators if "bollinger" in item or "band" in item),
        *slots["event"],
        *slots["price_basis"],
    }
    required = {"bollinger", "lower_band_reentry", "close"}
    if required.issubset(observed):
        return {"verdict": "pass", "failure_cause": None, "semantic_slots": slots}
    return {"verdict": "fail", "failure_cause": "semantic_drift", "semantic_slots": slots}
