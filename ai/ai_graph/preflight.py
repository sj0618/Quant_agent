"""Deterministic public-scope checks that run before analysis work starts.

This module intentionally has no graph, provider, data-source, job-store, audit, or
runtime-configuration dependency.  The API and graph entrypoints can therefore use it
before they create state that could retain a prohibited personalized request.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

SCOPE_REFUSAL_REASON = "personalized_investment_request"
UNSUPPORTED_SCOPE_REASON = "unsupported_asset_family"


@dataclass(frozen=True)
class ResearchRequestPreflight:
    """A secret-free, public-safe decision for one research request."""

    allowed: bool
    reason_code: str | None = None
    adjudicable: bool = False

    @property
    def kind(self) -> str:
        if self.reason_code == UNSUPPORTED_SCOPE_REASON:
            return "unsupported_scope"
        return "scope_refusal"

    @property
    def public_message(self) -> str:
        if self.allowed:
            return "일반적인 조건식으로 검토할 수 있는 요청입니다."
        if self.reason_code == UNSUPPORTED_SCOPE_REASON:
            return "현재 V1에서는 한국 주식 EOD 기반의 일반 조건식만 검토할 수 있습니다."
        return "개인 상황이나 매매 행동에 대한 요청은 분석하지 않습니다."

    @property
    def public_example(self) -> str:
        return "예: KOSPI/KOSDAQ에서 RSI와 거래량 조건이 동시에 충족된 종목을 검토해 주세요."

    @property
    def public_guidance(self) -> str:
        if self.reason_code == UNSUPPORTED_SCOPE_REASON:
            return "KRX 상장 종목의 지표·거래량·재무 조건식으로 다시 입력해 주세요."
        return "보유·계좌·수량·시점·매수·매도 정보 없이 일반적인 조건식으로 다시 입력해 주세요."


_PERSONAL_CONTEXT_TERMS = (
    "내보유",
    "내계좌",
    "내포트폴리오",
    "나의보유",
    "나의계좌",
    "제보유",
    "제계좌",
    "나에게맞",
    "내게맞",
    "위험성향",
    "투자성향",
    "myholding",
    "myaccount",
    "myportfolio",
    "suitableforme",
    "formyriskprofile",
)

_ACTION_IMPERATIVE_TERMS = (
    "사줘",
    "사야",
    "사라",
    "매수해",
    "매수해야",
    "팔아",
    "팔아야",
    "팔아줘",
    "매도해",
    "매도해야",
    "보유해",
    "추천종목",
    "종목추천",
    "매수추천",
    "매도추천",
    "무엇을사",
    "뭘사",
    "돈되는",
    "좋은종목추천",
    "whatshouldibuy",
    "whatshouldisell",
    "shouldibuy",
    "shouldisell",
    "buyforme",
    "sellforme",
    "recommendstock",
    "stockrecommendation",
)

_AMBIGUOUS_RECOMMENDATION_TERMS = (
    "추천해",
    "추천좀",
    "추천부탁",
    "골라줘",
    "골라주세",
)

_PERSONAL_ACTION_TERMS = (
    "지금얼마를",
    "몇주사",
    "몇주팔",
    "목표가에사",
    "목표가에팔",
    "언제사",
    "언제팔",
    "howmanyshares",
    "whenishouldbuy",
    "whenishouldsell",
)

# These are unambiguous requests outside the V1 Korea-equity EOD scope.  Do not use
# broad words such as "옵션" or "선물" here: they also appear in ordinary Korean UI
# prose and would reject a valid general rule by accident.
_UNSUPPORTED_ASSET_TERMS = (
    "콜옵션",
    "풋옵션",
    "옵션전략",
    "옵션양매도",
    "양매도",
    "선물거래",
    "선물전략",
    "선물매수",
    "선물매도",
    "비트코인",
    "이더리움",
    "암호화폐",
    "가상자산",
    "미국주식",
    "해외주식",
    "nasdaq",
    "nyse",
)


def classify_research_request(query: str) -> ResearchRequestPreflight:
    """Fail closed for personalized or action-oriented investment requests.

    The compact form makes Korean whitespace/punctuation obfuscation deterministic.
    It deliberately does not reject neutral entry/exit rules such as ``RSI 30 이하
    매수``: an action verb is a research-rule parameter only until it becomes an
    imperative/advisory request or is combined with personal context.
    """

    compact = _compact_query(query)
    if not compact:
        return ResearchRequestPreflight(allowed=True)
    if any(term in compact for term in _PERSONAL_CONTEXT_TERMS):
        return ResearchRequestPreflight(False, SCOPE_REFUSAL_REASON)
    if any(term in compact for term in _ACTION_IMPERATIVE_TERMS):
        return ResearchRequestPreflight(False, SCOPE_REFUSAL_REASON)
    if any(term in compact for term in _PERSONAL_ACTION_TERMS):
        return ResearchRequestPreflight(False, SCOPE_REFUSAL_REASON)
    if any(term in compact for term in _UNSUPPORTED_ASSET_TERMS):
        return ResearchRequestPreflight(False, UNSUPPORTED_SCOPE_REASON)
    if any(term in compact for term in _AMBIGUOUS_RECOMMENDATION_TERMS):
        return ResearchRequestPreflight(False, SCOPE_REFUSAL_REASON, adjudicable=True)
    return ResearchRequestPreflight(allowed=True)


def _compact_query(query: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(query)).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)
