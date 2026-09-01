"""PostgreSQL-owned policy for reproducible exploratory strategy research."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_graph.data_sources.db import resolve_database_dsn_from_env
from ai_graph.strategy_blueprint_catalog import (
    CATALOG_VERSION,
    StrategyBlueprintTemplate,
    select_strategy_blueprints,
    strategy_blueprint_catalog,
    strategy_blueprint_catalog_fingerprint,
)
from ai_graph.strategy_blueprint_rules import InvestmentHorizon, RiskStyle

EXPLORATION_POLICY_SCHEMA_VERSION = "exploration-policy.v2"


class ExplorationPolicyUnavailableError(ValueError):
    """The active policy cannot safely authorize an exploratory run."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ExplorationCostModelV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    commission_pct: float = Field(ge=0.0)
    tax_pct: float = Field(ge=0.0)
    slippage_pct: float = Field(ge=0.0)


class ExplorationValidationV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: Literal["rolling_walk_forward"] = "rolling_walk_forward"
    train_months: int = Field(ge=1)
    validation_months: int = Field(ge=1)
    evaluation_months: int = Field(ge=1)
    roll_months: int = Field(ge=1)
    minimum_evaluation_sessions: int = Field(ge=1)


class ExplorationPolicyV2(BaseModel):
    """Immutable policy payload stored in ``app.ai_exploration_policy``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[EXPLORATION_POLICY_SCHEMA_VERSION] = EXPLORATION_POLICY_SCHEMA_VERSION
    policy_version: str = Field(min_length=1, max_length=100)
    publication_status: Literal["published"] = "published"
    market: Literal["KRX"] = "KRX"
    timeframe: Literal["daily"] = "daily"
    long_only: Literal[True] = True
    history_years: int = Field(ge=1, le=20)
    candidate_count: int = Field(ge=2, le=10)
    risk_style: RiskStyle
    investment_horizon: InvestmentHorizon
    max_positions: int = Field(ge=1, le=1000)
    rebalance_interval_days: int = Field(ge=5, le=63)
    stop_loss_pct: float = Field(gt=0.0, le=1.0)
    take_profit_pct: float = Field(gt=0.0, le=10.0)
    trailing_stop_pct: float = Field(gt=0.0, le=0.75)
    benchmark: Literal["official_krx_total_return"] = "official_krx_total_return"
    cost_model: ExplorationCostModelV2
    validation: ExplorationValidationV2
    catalog_version: str = Field(min_length=1)
    catalog_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ActiveExplorationPolicyV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy: ExplorationPolicyV2
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_at: datetime

    @model_validator(mode="after")
    def hash_matches_payload(self) -> "ActiveExplorationPolicyV2":
        if self.policy_hash != canonical_exploration_policy_hash(self.policy):
            raise ValueError("exploration policy hash does not match its payload")
        return self


def canonical_exploration_policy_hash(policy: ExplorationPolicyV2) -> str:
    encoded = json.dumps(
        policy.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_active_exploration_policy(
    record: ActiveExplorationPolicyV2,
) -> ActiveExplorationPolicyV2:
    policy = record.policy
    if policy.catalog_version != CATALOG_VERSION:
        raise ExplorationPolicyUnavailableError("exploration_catalog_version_stale")
    if policy.catalog_hash != strategy_blueprint_catalog_fingerprint():
        raise ExplorationPolicyUnavailableError("exploration_catalog_hash_stale")
    return record


def select_exploration_templates(
    query: str,
    record: ActiveExplorationPolicyV2,
) -> list[StrategyBlueprintTemplate]:
    validate_active_exploration_policy(record)
    policy = record.policy
    selected = select_strategy_blueprints(
        query,
        risk_style=policy.risk_style,
        horizon=policy.investment_horizon,
        limit=policy.candidate_count,
    )
    if len(selected) != policy.candidate_count:
        raise ExplorationPolicyUnavailableError("exploration_candidate_count_unavailable")
    return selected


def validate_exploration_spec_against_policy(
    raw_spec: BaseModel | Mapping[str, Any],
    record: ActiveExplorationPolicyV2,
) -> None:
    """Validate a sealed V2 spec without importing either duplicated boundary model."""

    validate_active_exploration_policy(record)
    spec = raw_spec.model_dump(mode="json") if isinstance(raw_spec, BaseModel) else dict(raw_spec)
    policy = record.policy
    expected = {
        "policy_version": policy.policy_version,
        "policy_hash": record.policy_hash,
        "catalog_version": policy.catalog_version,
        "catalog_hash": policy.catalog_hash,
    }
    for key, value in expected.items():
        if spec.get(key) != value:
            raise ExplorationPolicyUnavailableError(f"exploration_{key}_stale")
    candidates = spec.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise ExplorationPolicyUnavailableError("exploration_candidates_invalid")
    if len(candidates) != policy.candidate_count:
        raise ExplorationPolicyUnavailableError("exploration_candidate_count_stale")
    catalog = {item.catalog_id: item for item in strategy_blueprint_catalog()}
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise ExplorationPolicyUnavailableError("exploration_candidates_invalid")
        catalog_id = str(candidate.get("catalog_id") or "")
        signature = str(candidate.get("execution_signature") or "")
        template = catalog.get(catalog_id)
        if not catalog_id or catalog_id in seen or template is None:
            raise ExplorationPolicyUnavailableError("exploration_candidate_catalog_stale")
        if signature != template.execution_signature:
            raise ExplorationPolicyUnavailableError("exploration_candidate_signature_stale")
        seen.add(catalog_id)


def load_active_exploration_policy(
    connection: Any,
    *,
    market: str = "KRX",
    for_update: bool = False,
) -> ActiveExplorationPolicyV2:
    lock = "FOR UPDATE OF active_policy" if for_update else ""
    row = connection.execute(
        f"""
        SELECT policy.policy_jsonb, policy.policy_hash, policy.effective_at
        FROM app.ai_active_exploration_policy AS active_policy
        JOIN app.ai_exploration_policy AS policy
          ON policy.policy_version = active_policy.policy_version
        WHERE active_policy.market = %s
        {lock}
        """,
        (market,),
    ).fetchone()
    if row is None:
        raise ExplorationPolicyUnavailableError("exploration_policy_unavailable")
    try:
        record = ActiveExplorationPolicyV2(
            policy=ExplorationPolicyV2.model_validate(row["policy_jsonb"]),
            policy_hash=str(row["policy_hash"]),
            effective_at=row["effective_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ExplorationPolicyUnavailableError("exploration_policy_invalid") from exc
    return validate_active_exploration_policy(record)


def load_exploration_policy(connection: Any, policy_version: str) -> ActiveExplorationPolicyV2:
    row = connection.execute(
        """
        SELECT policy_jsonb, policy_hash, effective_at
        FROM app.ai_exploration_policy
        WHERE policy_version = %s
        """,
        (policy_version,),
    ).fetchone()
    if row is None:
        raise ExplorationPolicyUnavailableError("exploration_policy_unavailable")
    try:
        record = ActiveExplorationPolicyV2(
            policy=ExplorationPolicyV2.model_validate(row["policy_jsonb"]),
            policy_hash=str(row["policy_hash"]),
            effective_at=row["effective_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ExplorationPolicyUnavailableError("exploration_policy_invalid") from exc
    return validate_active_exploration_policy(record)


def load_active_exploration_policy_from_env(
    env: Mapping[str, str] | None = None,
    *,
    connector: Callable[..., Any] | None = None,
) -> ActiveExplorationPolicyV2:
    dsn, _ = resolve_database_dsn_from_env(env)
    if not dsn:
        raise ExplorationPolicyUnavailableError("exploration_policy_database_unavailable")
    if connector is None:
        import psycopg
        from psycopg.rows import dict_row

        connector = psycopg.connect
        connect_kwargs = {"connect_timeout": 3, "row_factory": dict_row}
    else:
        connect_kwargs = {}
    try:
        with connector(dsn, **connect_kwargs) as connection:
            return load_active_exploration_policy(connection)
    except ExplorationPolicyUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001 - expose only a stable policy availability code.
        raise ExplorationPolicyUnavailableError("exploration_policy_database_unavailable") from exc


def load_exploration_policy_from_env(
    policy_version: str,
    env: Mapping[str, str] | None = None,
    *,
    connector: Callable[..., Any] | None = None,
) -> ActiveExplorationPolicyV2:
    dsn, _ = resolve_database_dsn_from_env(env)
    if not dsn:
        raise ExplorationPolicyUnavailableError("exploration_policy_database_unavailable")
    if connector is None:
        import psycopg
        from psycopg.rows import dict_row

        connector = psycopg.connect
        connect_kwargs = {"connect_timeout": 3, "row_factory": dict_row}
    else:
        connect_kwargs = {}
    try:
        with connector(dsn, **connect_kwargs) as connection:
            return load_exploration_policy(connection, policy_version)
    except ExplorationPolicyUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001 - expose only a stable policy availability code.
        raise ExplorationPolicyUnavailableError("exploration_policy_database_unavailable") from exc
