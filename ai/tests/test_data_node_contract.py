import inspect

import pytest

from ai_graph.data_sources import db, db_split, db_test, profile_aware
from ai_graph.graph import _missing_required_indicator_families
from ai_graph.source_manifest import is_release_profile


@pytest.mark.parametrize("module", [db, db_test, db_split, profile_aware])
def test_data_source_variants_share_the_data_node_load_contract(module) -> None:
    signature = inspect.signature(module.load_pipeline_data_from_env)

    assert "sector" in signature.parameters
    fields = module.PipelineDataBundle.model_fields
    assert {
        "current_screen_candidates",
        "relaxed_screening_candidates",
        "historical_backtest_universe",
    } <= set(fields)
    assert "official_benchmark" in fields


def test_screening_relaxation_is_opt_in() -> None:
    config = db.DataSourceConfig(database_dsn="postgresql://example")

    assert config.allow_screening_relaxation is False
    assert config.enable_llm_screening is False


def test_required_indicator_gap_is_terminal_for_sealed_data() -> None:
    assert _missing_required_indicator_families(
        ["rsi"],
        {"unavailable_indicator_families": ["momentum"]},
    ) == ["momentum"]
    assert (
        _missing_required_indicator_families(
            ["rsi"],
            {"unavailable_indicator_families": ["trend"]},
        )
        == []
    )
    assert _missing_required_indicator_families(None, {}) == []


def test_empty_required_indicator_rows_are_not_treated_as_available() -> None:
    assert db._missing_indicator_families_from_rows(
        [{"ticker": "005930", "close": 100.0, "rsi": None}],
        ["momentum"],
    ) == {"momentum"}
    assert db_split._missing_indicator_families_from_rows(
        [{"ticker": "005930", "close": 100.0, "rsi": None}],
        ["momentum"],
    ) == {"momentum"}


def test_split_screening_only_cannot_accept_a_sealed_metric_plan() -> None:
    source = db_split.PostgresPipelineDataSource(
        db_split.DataSourceConfig(
            database_dsn="postgresql://example",
            load_mode="screening_only",
        )
    )

    with pytest.raises(db_split.PipelineDataUnavailableError) as failure:
        source.load(
            "RSI가 30 이하인 종목",
            "trace-screening-only-plan",
            required_metrics=["rsi"],
        )

    assert failure.value.reason == "backtest_data_required"


def test_split_historical_universe_does_not_union_current_recommendations() -> None:
    class Connection:
        def execute(self, _query, _params):
            return self

        def fetchall(self):
            return [{"symbol": "000660"}]

    source = db_split.PostgresPipelineDataSource(
        db_split.DataSourceConfig(database_dsn="postgresql://example")
    )

    assert source._fetch_backtest_universe(Connection(), ["999999"]) == ["000660"]


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({"AI_RELEASE_PROFILE": "release"}, True),
        ({"APP_ENV": "prod"}, False),
        ({"APP_ENV": "staging"}, False),
    ],
)
def test_release_profile_uses_one_definition(environment, expected) -> None:
    assert is_release_profile(environment) is expected
