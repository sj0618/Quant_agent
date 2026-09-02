from __future__ import annotations

from datetime import date

import pytest

from ai_graph.data_sources import PipelineDataUnavailableError
from ai_graph.graph import run_analysis
from ai_graph.source_manifest import (
    build_pipeline_extract_snapshot,
    build_source_manifest,
    compute_extract_hash,
    compute_lineage_hash,
    compute_pipeline_extract_hash,
    is_release_profile,
    validate_release_metadata,
    validate_source_manifest,
)


def _extract_snapshot(*, close: int = 100) -> dict[str, object]:
    return build_pipeline_extract_snapshot(
        price_rows=[{"ticker": "005930", "date": "2026-08-20", "close": close}],
        screening_candidates=[{"ticker": "005930"}],
        l4_evidence=[{"report_id": "report-1", "ticker": "005930"}],
        macro_snapshot={"usd_krw": 1350.0},
        data_availability={"source": "postgres", "price_ta": True},
    )


def _release_metadata(manifest) -> dict[str, object]:
    return {
        "source": manifest.source,
        "source_manifest": manifest.model_dump(mode="json"),
        "source_snapshot_as_of": manifest.as_of.isoformat(),
        "source_snapshot_freshness": manifest.freshness,
        "source_snapshot_version": manifest.source_version,
    }


def test_source_manifest_contains_required_fields_and_matching_lineage_hash() -> None:
    manifest = build_source_manifest(
        source="postgres",
        as_of=date(2026, 8, 20),
        freshness="eod_current",
        lineage_refs=["mart.common_stock_universe_asof", "feature.kis_adjusted_ohlcv_daily"],
        source_version="krx-pit-v1",
        extract_snapshot=_extract_snapshot(),
    )

    assert set(manifest.model_dump()) >= {
        "source",
        "as_of",
        "freshness",
        "extract_hash",
        "snapshot_id",
        "lineage_hash",
    }
    assert len(manifest.lineage_hash) == 64
    assert manifest.lineage_hash == compute_lineage_hash(manifest)
    assert validate_source_manifest(manifest, release_profile=True) == ()


def test_incremental_pipeline_extract_hash_matches_materialized_snapshot() -> None:
    """The memory-saving release path must bind exactly the same payload."""

    arguments = {
        "price_rows": [
            {"ticker": "000001", "date": "2026-08-20", "close": 100},
            {"ticker": "000002", "date": "2026-08-20", "close": 120},
        ],
        "screening_candidates": [{"ticker": "000002", "score": 0.8}],
        "l4_evidence": [{"ticker": "000002", "report_id": "report-1"}],
        "macro_snapshot": {"usd_krw": 1350.0},
        "data_availability": {"price_ta": True, "source": "postgres"},
        "required_tickers": ("000002", "2"),
    }

    snapshot = build_pipeline_extract_snapshot(**arguments)

    assert compute_pipeline_extract_hash(**arguments) == compute_extract_hash(snapshot)


def test_missing_manifest_fields_are_rejected_for_release() -> None:
    errors = validate_release_metadata({"source": "postgres"})

    assert errors == ("source manifest is missing",)


def test_fixture_and_stale_manifest_are_not_release_eligible() -> None:
    fixture_manifest = build_source_manifest(
        source="fixture",
        as_of=date(2026, 8, 20),
        freshness="unknown",
        lineage_refs=["local-fixture"],
        source_version="test-fixture",
        extract_snapshot=_extract_snapshot(),
    )
    stale_manifest = build_source_manifest(
        source="postgres",
        as_of=date(2026, 8, 20),
        freshness="stale",
        lineage_refs=["feature.kis_adjusted_ohlcv_daily"],
        extract_snapshot=_extract_snapshot(),
    )

    assert "release source manifest requires postgres source" in validate_source_manifest(
        fixture_manifest, release_profile=True
    )
    assert "release source manifest freshness must be current" in validate_source_manifest(
        stale_manifest, release_profile=True
    )


def test_server_deployment_profile_enables_the_same_release_provenance_gate() -> None:
    assert is_release_profile({"APP_ENV": "production"}) is True
    assert is_release_profile({"APP_ENV": "prod"}) is False
    assert is_release_profile({"AI_RELEASE_PROFILE": "release"}) is True


def test_lineage_hash_mismatch_is_rejected() -> None:
    manifest = build_source_manifest(
        source="postgres",
        as_of=date(2026, 8, 20),
        freshness="fresh",
        lineage_refs=["feature.kis_adjusted_ohlcv_daily"],
        extract_snapshot=_extract_snapshot(),
    )
    changed = manifest.model_copy(update={"source": "postgres-replaced"})

    assert validate_source_manifest(changed) == (
        "source manifest lineage_hash does not match canonical fields",
        "source manifest snapshot_id does not match canonical fields",
    )


def test_release_rejects_a_valid_new_manifest_for_other_loaded_data() -> None:
    loaded_extract = _extract_snapshot(close=100)
    different_extract = _extract_snapshot(close=999)
    manifest_for_other_data = build_source_manifest(
        source="postgres",
        as_of=date(2026, 8, 20),
        freshness="eod_current",
        lineage_refs=["feature.kis_adjusted_ohlcv_daily"],
        source_version="krx-pit-v1",
        extract_snapshot=different_extract,
    )

    errors = validate_release_metadata(
        _release_metadata(manifest_for_other_data), extract_snapshot=loaded_extract
    )

    assert manifest_for_other_data.lineage_hash == compute_lineage_hash(manifest_for_other_data)
    assert "source manifest extract_hash does not match loaded data" in errors
    assert "source manifest snapshot_id does not match loaded data" in errors


def test_precomputed_extract_hash_uses_current_snapshot_not_historical_delistings() -> None:
    """PIT members that delisted before ``as_of`` remain backtest rows, not freshness failures."""

    extract = build_pipeline_extract_snapshot(
        price_rows=[
            {"ticker": "000001", "date": "2024-01-02", "close": 100},
            {"ticker": "000002", "date": "2026-08-20", "close": 120},
        ],
        screening_candidates=[],
        l4_evidence=[],
        macro_snapshot=None,
        data_availability={"source": "postgres", "price_ta": True},
        required_tickers=("000002",),
    )
    manifest = build_source_manifest(
        source="postgres",
        as_of=date(2026, 8, 20),
        freshness="eod_current",
        lineage_refs=["mart.common_stock_universe_asof", "feature.kis_adjusted_ohlcv_daily"],
        source_version="krx-pit-v2",
        extract_snapshot=extract,
    )
    metadata = _release_metadata(manifest) | {
        "current_snapshot_tickers": ["000002"],
        "current_snapshot_price_rows": [{"ticker": "000002", "date": "2026-08-20"}],
    }

    assert validate_release_metadata(
        metadata,
        loaded_extract_hash=manifest.extract_hash,
    ) == ()


def test_release_profile_fails_before_fixture_analysis_can_return_a_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_name in ("AI_DATABASE_DSN", "QUANT_DB_DSN", "DATABASE_URL"):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("AI_RELEASE_PROFILE", "release")
    monkeypatch.setenv("AI_LLM_PROVIDER", "mock")

    with pytest.raises(PipelineDataUnavailableError, match="release source manifest is invalid"):
        run_analysis("RSI가 30 이하인 KOSPI200 종목", trace_id="trace-release-manifest")
