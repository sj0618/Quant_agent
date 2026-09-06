from __future__ import annotations

import re
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_graph.schemas import AmbiguityCode

AmbiguityStatus = Literal["confirmed", "provisional", "rejected"]

REQUIRED_FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "market": ("krx", "kospi", "kosdaq", "korea", "한국", "국내", "삼성", "sk하이닉스"),
    "entry_rule": ("rsi", "이동평균", "ma", "macd", "돌파", "breakout", "매수", "진입"),
    "risk_profile": ("보수", "중립", "공격", "손절", "risk", "위험"),
}

CLARIFICATION_QUESTIONS: dict[str, str] = {
    "market": "대상 시장은 KRX/KOSPI/KOSDAQ 중 어디인가요?",
    "entry_rule": "진입 조건은 RSI, 이동평균, MACD, 돌파 중 무엇을 사용할까요?",
    "risk_profile": "위험 성향과 손절 기준을 보수/중립/공격 중 어디에 둘까요?",
}

DEFAULT_ASSUMPTIONS: dict[str, str] = {
    "market": "시장 미지정 시 KRX 현물 주식으로 가정합니다.",
    "entry_rule": "진입 조건 미지정 시 RSI 과매도 반등 전략으로 가정합니다.",
    "risk_profile": "위험 성향 미지정 시 중립 위험 프로필로 가정합니다.",
}

MIN_CONFIRMED_CONFIDENCE = 0.72
MISSING_FIELD_PENALTY = 0.16


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
    rejected = is_unsupported_asset_class(normalized_query)
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


def classify_query(query: str) -> AmbiguityCode:
    """The two refusals decided by keyword before - or instead of - a model.

    It deliberately answers two questions and not the others: is this small talk, and
    is this an asset class the warehouse can price. Everything it used to decide by
    keyword - whether a term was "known", whether enough conditions were named,
    whether two goals conflicted - is a judgment call that belongs to
    resolve_strategy_intent, which can search and then commit. Matching phrases here
    only ever produced questions for inputs a person would have had no trouble acting
    on.

    Callers: the graph when no model decision is available, the rule-draft and
    clarification paths (api.py, research_contract.py), and - asset-class half only -
    the deterministic mock model.
    """

    if is_small_talk(query):
        return AmbiguityCode.NO_STRATEGY_INTENT
    return AmbiguityCode.INFEASIBLE if is_unsupported_asset_class(query) else AmbiguityCode.READY


# Derivatives, FX and crypto, phrased as the trading terms rather than the bare nouns:
# 선물 is also "gift" and 옵션 is also "setting" ("부모님께 선물할 배당주", "리밸런싱
# 옵션을 월간으로"), so a bare substring refused ordinary cash-equity requests.
_UNSUPPORTED_ASSET_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"가상\s*(?:화폐|자산)",
        r"암호\s*화폐",
        r"crypto",
        r"크립토",
        r"비트코인",
        r"이더리움",
        r"코인\s*(?:선물|거래|투자|마진)",
        r"(?:지수|코스피\s*\d*|코스닥\s*\d*|주가|달러|미니|야간|통화|금리|원유)\s*선물",
        r"선물\s*(?:거래|매도|매수|옵션|시장|포지션|롱|숏|전략|투자|스프레드|만기|헤지)",
        r"선옵",
        r"(?:콜|풋)\s*옵션",
        r"옵션\s*(?:매도|매수|거래|전략|양매도|프리미엄|만기|투자|시장|헤지)",
        r"양매[도수]",
        r"\bfx\b",
        r"fx\s*마진",
        r"외환\s*(?:거래|투자|마진|전략|선물)",
    )
)


def is_unsupported_asset_class(query: str) -> bool:
    lowered = " ".join(query.split()).lower()
    return any(pattern.search(lowered) for pattern in _UNSUPPORTED_ASSET_PATTERNS)


# Greetings, thanks and idle questions - a backtest is not an answer to any of them.
# Matched as substrings, so only stems that do not begin an ordinary noun belong here.
_SMALL_TALK_TERMS = (
    "안녕",
    "ㅎㅇ",
    "반가",
    "고마",
    "감사",
    "ㄳ",
    "수고",
    "잘 지내",
    "날씨",
    "몇 시",
    "누구야",
    "누구세요",
    "뭐 해",
    "뭐해",
    "심심",
    "주말",
    "좋은 하루",
    "굿모닝",
)
# Greetings that are also the first syllables of a listed name (하이닉스, 하이브):
# whole words only.
_SMALL_TALK_WORDS = frozenset({"하이", "하이하이", "하이요", "헬로", "안뇽"})
# Anything the warehouse can act on, plus the verbs that make a message a request.
# Present only to keep the check above from firing on a real request that happens to
# be polite or to contain a greeting stem ("감사보고서", "수고비").
_MARKET_TERMS = (
    "주식",
    "주가",
    "관련주",
    "배당주",
    "성장주",
    "가치주",
    "저평가주",
    "우량주",
    "테마주",
    "대형주",
    "소형주",
    "급등주",
    "종목",
    "기업",
    "회사",
    "매수",
    "매도",
    "전략",
    "투자",
    "수익",
    "차트",
    "코스피",
    "코스닥",
    "백테스트",
    "포트폴리오",
    "배당",
    "실적",
    "지수",
    "단타",
    "스윙",
    "사줘",
    "사고",
    "팔아",
    "골라",
    "찾아",
    "추천",
    "분석",
    "검토",
    "검증",
    "만들어",
    "설정",
    "알아서",
    "stock",
    "buy",
    "sell",
    "strategy",
)
_SMALL_TALK_LENGTH_LIMIT = 20


def is_small_talk(query: str) -> bool:
    """Whether this message is not asking for a strategy at all.

    Deliberately shaped as positive evidence of chit-chat rather than as an allowlist
    of strategy words. An allowlist decides by what it fails to recognise, so
    "화학 관련주 사줘" - a perfectly clear request naming no listed keyword - came back
    as a greeting. Every uncertain input must fall through to the analysis; the cost of
    running one is a wasted job, the cost of refusing one is the user's answer. That is
    also why the length cap stays: a long message with a greeting inside is far more
    often a request than a greeting.

    Only consulted for the obvious cases, and before the model is called so a greeting
    does not pay for a web search. Live runs let resolve_strategy_intent decide; the
    mock model does not repeat this check because the graph has already applied it.
    """

    normalized = " ".join(query.split()).lower()
    if not normalized or len(normalized) > _SMALL_TALK_LENGTH_LIMIT:
        return False
    if any(term in normalized for term in _MARKET_TERMS):
        return False
    if any(term in normalized for term in _SMALL_TALK_TERMS):
        return True
    return any(token.strip("!?.,~^") in _SMALL_TALK_WORDS for token in normalized.split())
