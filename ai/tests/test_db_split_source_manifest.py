from __future__ import annotations

from datetime import date

from ai_graph.data_sources import db_split
from ai_graph.source_manifest import (
    build_pipeline_extract_snapshot,
    build_source_manifest,
    validate_release_metadata,
)


def _release_metadata(manifest, *, as_of: date, freshness: str) -> dict[str, object]:
    return {
        "source": "postgres",
        "source_manifest": manifest.model_dump(mode="json"),
        "source_snapshot_as_of": as_of.isoformat(),
        "source_snapshot_freshness": freshness,
        "source_snapshot_version": "split-pipeline-v1",
    }


def _sample_extract() -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, object],
    dict[str, object],
]:
    return (
        [{"ticker": "005930", "date": "2026-08-20", "close": 100.0}],
        [{"ticker": "005930", "score": 1.0}],
        [{"report_id": "report-1", "ticker": "005930"}],
        {"usd_krw": 1350.0},
        {"source": "postgres", "price_ta": True},
    )


def test_db_split_current_extract_is_release_eligible() -> None:
    price_rows, candidates, l4_evidence, macro_snapshot, data_availability = _sample_extract()
    manifest, as_of, freshness = db_split._build_backtest_source_manifest(
        price_rows=price_rows,
        screening_candidates=candidates,
        l4_evidence=l4_evidence,
        macro_snapshot=macro_snapshot,
        data_availability=data_availability,
        indicator_families=(),
        required_tickers=("005930",),
        latest_available_session=date(2026, 8, 20),
    )
    extract_snapshot = build_pipeline_extract_snapshot(
        price_rows=price_rows,
        screening_candidates=candidates,
        l4_evidence=l4_evidence,
        macro_snapshot=macro_snapshot,
        data_availability=data_availability,
        required_tickers=("005930",),
    )

    assert freshness == "eod_current"
    assert (
        validate_release_metadata(
            _release_metadata(manifest, as_of=as_of, freshness=freshness),
            extract_snapshot=extract_snapshot,
        )
        == ()
    )


def test_db_split_noncurrent_extract_is_not_release_eligible() -> None:
    price_rows, candidates, l4_evidence, macro_snapshot, data_availability = _sample_extract()
    price_rows = [
        {"ticker": "000001", "date": "2026-08-19", "close": 100.0},
        {"ticker": "000002", "date": "2026-08-20", "close": 100.0},
    ]
    candidates = [{"ticker": "000001", "score": 1.0}, {"ticker": "000002", "score": 1.0}]
    manifest, as_of, freshness = db_split._build_backtest_source_manifest(
        price_rows=price_rows,
        screening_candidates=candidates,
        l4_evidence=l4_evidence,
        macro_snapshot=macro_snapshot,
        data_availability=data_availability,
        indicator_families=(),
        required_tickers=("000001", "000002"),
        latest_available_session=date(2026, 8, 21),
    )

    assert freshness == "stale"
    extract_snapshot = build_pipeline_extract_snapshot(
        price_rows=price_rows,
        screening_candidates=candidates,
        l4_evidence=l4_evidence,
        macro_snapshot=macro_snapshot,
        data_availability=data_availability,
        required_tickers=("000001", "000002"),
    )
    assert "release source manifest freshness must be current" in validate_release_metadata(
        _release_metadata(manifest, as_of=as_of, freshness=freshness),
        extract_snapshot=extract_snapshot,
    )
    falsely_current = build_source_manifest(
        source="postgres",
        as_of=date(2026, 8, 20),
        freshness="eod_current",
        lineage_refs=[db_split.KIS_ADJUSTED_OHLCV_TABLE, db_split.UNIVERSE_VIEW],
        source_version="split-pipeline-v1",
        extract_snapshot=extract_snapshot,
    )

    assert (
        "release extract snapshot does not cover every required ticker through manifest as_of"
        in (
            validate_release_metadata(
                _release_metadata(
                    falsely_current, as_of=date(2026, 8, 20), freshness="eod_current"
                ),
                extract_snapshot=extract_snapshot,
            )
        )
    )


def test_db_split_multi_ticker_partial_current_coverage_is_rejected_for_release() -> None:
    _, candidates, l4_evidence, macro_snapshot, data_availability = _sample_extract()
    price_rows = [
        {"ticker": "000001", "date": "2026-08-19", "close": 100.0},
        {"ticker": "000002", "date": "2026-08-20", "close": 100.0},
    ]
    manifest, as_of, freshness = db_split._build_backtest_source_manifest(
        price_rows=price_rows,
        screening_candidates=candidates,
        l4_evidence=l4_evidence,
        macro_snapshot=macro_snapshot,
        data_availability=data_availability,
        indicator_families=(),
        required_tickers=("000001", "000002"),
        latest_available_session=date(2026, 8, 20),
    )

    assert freshness == "stale"
    assert "release source manifest freshness must be current" in validate_release_metadata(
        _release_metadata(manifest, as_of=as_of, freshness=freshness),
        extract_snapshot=build_pipeline_extract_snapshot(
            price_rows=price_rows,
            screening_candidates=candidates,
            l4_evidence=l4_evidence,
            macro_snapshot=macro_snapshot,
            data_availability=data_availability,
            required_tickers=("000001", "000002"),
        ),
    )
