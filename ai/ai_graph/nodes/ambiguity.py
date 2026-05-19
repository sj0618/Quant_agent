from __future__ import annotations

from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AmbiguityStatus = Literal["confirmed", "provisional", "rejected"]

REQUIRED_FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "market": ("krx", "kospi", "kosdaq", "korea", "한국", "국내", "삼성", "sk하이닉스"),
    "universe": ("top", "상위", "섹터", "반도체", "후보", "kospi200", "코스피200"),
    "entry_rule": ("rsi", "이동평균", "ma", "macd", "돌파", "breakout", "매수", "진입"),
    "risk_profile": ("보수", "중립", "공격", "손절", "risk", "위험"),
}

CLARIFICATION_QUESTIONS: dict[str, str] = {
    "market": "대상 시장은 KRX/KOSPI/KOSDAQ 중 어디인가요?",
    "universe": "후보군은 전체 종목, 섹터, 또는 상위 N개 중 무엇인가요?",
    "entry_rule": "진입 조건은 RSI, 이동평균, MACD, 돌파 중 무엇을 사용할까요?",
    "risk_profile": "위험 성향과 손절 기준을 보수/중립/공격 중 어디에 둘까요?",
}

DEFAULT_ASSUMPTIONS: dict[str, str] = {
    "market": "시장 미지정 시 KRX 현물 주식으로 가정합니다.",
    "universe": "후보군 미지정 시 리서치 후보 상위 30개로 가정합니다.",
    "entry_rule": "진입 조건 미지정 시 RSI 과매도 반등 전략으로 가정합니다.",
    "risk_profile": "위험 성향 미지정 시 중립 위험 프로필로 가정합니다.",
}

MIN_CONFIRMED_CONFIDENCE = 0.72
MISSING_FIELD_PENALTY = 0.16
REJECTION_TERMS = ("가상화폐", "crypto", "선물", "옵션", "fx", "외환")


class AmbiguityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    debug_ref: str
    status: AmbiguityStatus
    is_ambiguous: bool
    fit_confidence: float = Field(ge=0.0, le=1.0)
    normalized_query: str
    missing_fields: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("trace_id", "debug_ref", "normalized_query")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized


def classify_ambiguity(
    user_query: str, *, trace_id: str | None = None
) -> AmbiguityResult:
    normalized_query = " ".join(user_query.strip().split())
    if not normalized_query:
        raise ValueError("user_query must not be empty")

    lowered = normalized_query.lower()
    trace = trace_id or _trace_id(normalized_query)
    missing_fields = [
        field_name
        for field_name, keywords in REQUIRED_FIELD_KEYWORDS.items()
        if not any(keyword in lowered for keyword in keywords)
    ]
    rejected = any(term in lowered for term in REJECTION_TERMS)
    confidence = max(0.0, 0.95 - (len(missing_fields) * MISSING_FIELD_PENALTY))
    status: AmbiguityStatus
    if rejected:
        status = "rejected"
        confidence = min(confidence, 0.25)
    elif confidence >= MIN_CONFIRMED_CONFIDENCE and not missing_fields:
        status = "confirmed"
    else:
        status = "provisional"

    questions = [CLARIFICATION_QUESTIONS[field] for field in missing_fields]
    assumptions = [DEFAULT_ASSUMPTIONS[field] for field in missing_fields]
    flags = [f"missing_{field}" for field in missing_fields]
    if rejected:
        flags.append("unsupported_asset_class")
        questions.append("MVP 범위는 KRX 현물 주식입니다. 국내 주식 전략으로 바꿀까요?")

    return AmbiguityResult(
        trace_id=trace,
        debug_ref=f"ambiguity:{trace}",
        status=status,
        is_ambiguous=status != "confirmed",
        fit_confidence=round(confidence, 2),
        normalized_query=normalized_query,
        missing_fields=missing_fields,
        ambiguity_flags=flags,
        clarification_questions=questions,
        assumptions=assumptions,
    )


def ambiguity_node(state: dict[str, Any]) -> dict[str, Any]:
    query = str(state.get("user_query") or state.get("query") or "")
    result = classify_ambiguity(query, trace_id=state.get("trace_id"))
    return {
        "ambiguity": result.model_dump(),
        "trace_id": result.trace_id,
        "debug_ref": result.debug_ref,
    }


def _trace_id(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]
