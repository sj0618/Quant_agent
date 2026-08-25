from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

DATABASE_ENV_NAMES = ("AI_DATABASE_DSN", "QUANT_DB_DSN", "DATABASE_URL")
PROVIDER_CREDENTIAL_ENV_NAMES = (
    "AI_AOAI_RESPONSES_URL",
    "AI_AOAI_API_KEY",
    "AI_AOAI_MODEL",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "OPENAI_API_KEY",
)


def _database_boundary_reached(*_args: Any, **_kwargs: Any) -> None:
    raise AssertionError("database boundary reached in offline test")


def _provider_boundary_reached(*_args: Any, **_kwargs: Any) -> None:
    raise AssertionError("provider boundary reached in offline test")


@dataclass(frozen=True)
class OfflineTestEnvironment:
    graph_module: ModuleType
    api_module: ModuleType
    data_source_module: ModuleType
    aoai_module: ModuleType
    offline_loader: Callable[[str, str], Any]
    database_env_names: tuple[str, ...]
    provider_credential_names: frozenset[str]
    cache_dir: Path


@pytest.fixture
def offline_test_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> OfflineTestEnvironment:
    """Opt these tests into fixture data, mock LLMs, and no-op auditing.

    The graph and API modules are intentionally imported before this fixture by the
    consuming tests. Rebinding the graph's import-bound loader is therefore part of the
    contract, not an incidental cleanup of the process environment.
    """

    for name in DATABASE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name in PROVIDER_CREDENTIAL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    # Each fixture invocation owns an empty temporary cache.  A shared system cache can
    # retain a historic dependency-failure evaluation and make a healthy test process
    # fail before it evaluates any current code.
    cache_dir = tmp_path / "backtest-cache"
    monkeypatch.setenv("AI_DATA_SOURCE_VARIANT", "db")
    monkeypatch.setenv("AI_LLM_PROVIDER", "mock")
    monkeypatch.setenv("AI_AUDIT_SINK", "noop")
    monkeypatch.setenv("AI_BACKTEST_CACHE_DIR", str(cache_dir))

    import ai_graph.api as api_module
    import ai_graph.data_sources.db as data_source_module
    import ai_graph.graph as graph_module
    import ai_graph.llm.aoai as aoai_module

    def offline_loader(query: str, trace_id: str) -> Any:
        return data_source_module.load_pipeline_data_from_env(query, trace_id)

    monkeypatch.setattr(graph_module, "load_pipeline_data_from_env", offline_loader)
    monkeypatch.setattr(
        data_source_module.PostgresPipelineDataSource,
        "load",
        _database_boundary_reached,
    )
    monkeypatch.setattr(
        aoai_module.AOAIResponsesClient,
        "generate_json",
        _provider_boundary_reached,
    )

    previous_debug_records = dict(graph_module.DEBUG_STORE._records)
    graph_module.DEBUG_STORE._records.clear()
    try:
        yield OfflineTestEnvironment(
            graph_module=graph_module,
            api_module=api_module,
            data_source_module=data_source_module,
            aoai_module=aoai_module,
            offline_loader=offline_loader,
            database_env_names=DATABASE_ENV_NAMES,
            provider_credential_names=frozenset(PROVIDER_CREDENTIAL_ENV_NAMES),
            cache_dir=cache_dir,
        )
    finally:
        graph_module.DEBUG_STORE._records.clear()
        graph_module.DEBUG_STORE._records.update(previous_debug_records)
