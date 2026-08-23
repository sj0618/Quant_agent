from __future__ import annotations

from datetime import date

import pytest

from ai_graph.data_sources import PipelineDataUnavailableError
from ai_graph.graph import run_analysis
from ai_graph.source_manifest import (
    build_source_manifest,
    compute_lineage_hash,
    validate_release_metadata,
    validate_source_manifest,
)


def test_source_manifest_contains_required_fields_and_matching_lineage_hash() -> None:
    manifest = build_source_manifest(
        source="postgres",
        as_of=date(2026, 8, 20),
        freshness="fresh",
        lineage_refs=["mart.common_stock_universe_asof", "feature.kis_adjusted_ohlcv_daily"],
        source_version="krx-pit-v1",
    )

    assert set(manifest.model_dump()) >= {"source", "as_of", "freshness", "lineage_hash"}
    assert len(manifest.lineage_hash) == 64
    assert manifest.lineage_hash == compute_lineage_hash(manifest)
    assert validate_source_manifest(manifest, release_profile=True) == ()


def test_missing_manifest_fields_are_rejected_for_release() -> None:
    errors = validate_release_metadata({"source": "postgres"})

    assert errors
    assert any("source manifest is missing" in error for error in errors)


def test_fixture_manifest_is_not_release_eligible() -> None:
    manifest = build_source_manifest(
        source="fixture",
        as_of=date(2026, 8, 20),
        freshness="unknown",
        lineage_refs=["local-fixture"],
        source_version="test-fixture",
    )

    errors = validate_source_manifest(manifest, release_profile=True)

    assert "fixture or unknown source is forbidden in release profile" in errors
    assert "release source manifest freshness must be known" in errors


def test_lineage_hash_mismatch_is_rejected() -> None:
    manifest = build_source_manifest(
        source="postgres",
        as_of=date(2026, 8, 20),
        freshness="fresh",
        lineage_refs=["feature.kis_adjusted_ohlcv_daily"],
    )
    changed = manifest.model_copy(update={"source": "postgres-replaced"})

    errors = validate_source_manifest(changed)

    assert errors == ("source manifest lineage_hash does not match canonical fields",)


def test_release_profile_fails_before_fixture_analysis_can_return_a_result(monkeypatch) -> None:
    for env_name in ("AI_DATABASE_DSN", "QUANT_DB_DSN", "DATABASE_URL"):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("AI_RELEASE_PROFILE", "release")

    with pytest.raises(PipelineDataUnavailableError, match="release source manifest is invalid"):
        run_analysis("RSI가 30 이하인 KOSPI200 종목", trace_id="trace-release-manifest")
