from __future__ import annotations

from datetime import UTC, date, datetime

from ai_graph.immutable_snapshot import (
    build_immutable_snapshot,
    build_snapshot_bundle,
    compute_bundle_hash,
    compute_snapshot_hash,
    validate_snapshot_bundle,
)

AS_OF = date(2026, 8, 20)
CAPTURED_AT = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)


def _bundle():
    return build_snapshot_bundle(
        as_of=AS_OF,
        source="postgres",
        lineage_refs=["core.symbol_listing_history", "mart.common_stock_universe_asof"],
        captured_at=CAPTURED_AT,
        pit_universe={"members": ["005930", "000660"], "policy": "pit-v1"},
        delisting={"events": [], "policy": "official-event-then-final-close-v1"},
        indicator_input={"families": ["ohlcv_ta"], "lookback_days": 126},
    )


def test_pit_delisting_and_indicator_inputs_are_one_valid_immutable_bundle() -> None:
    bundle = _bundle()

    assert validate_snapshot_bundle(bundle) == ()
    assert bundle.as_of == AS_OF
    assert bundle.pit_universe.kind == "pit_universe"
    assert bundle.delisting.kind == "delisting"
    assert bundle.indicator_input.kind == "indicator_input"
    assert bundle.bundle_hash == compute_bundle_hash(bundle)
    assert all(snapshot.content_hash == compute_snapshot_hash(snapshot) for snapshot in (
        bundle.pit_universe,
        bundle.delisting,
        bundle.indicator_input,
    ))


def test_snapshot_hash_changes_when_any_input_changes() -> None:
    bundle = _bundle()
    changed = bundle.pit_universe.model_copy(
        update={"payload": {"members": ["005930", "000660", "035420"], "policy": "pit-v1"}}
    )

    assert changed.content_hash != compute_snapshot_hash(changed)
    assert validate_snapshot_bundle(bundle.model_copy(update={"pit_universe": changed}))


def test_same_input_hash_reproduces_universe_and_delisting_outputs() -> None:
    first = _bundle()
    second = build_snapshot_bundle(
        as_of=AS_OF,
        source="postgres",
        lineage_refs=["core.symbol_listing_history", "mart.common_stock_universe_asof"],
        captured_at=datetime(2026, 8, 22, 0, 0, tzinfo=UTC),
        pit_universe={"members": ["005930", "000660"], "policy": "pit-v1"},
        delisting={"events": [], "policy": "official-event-then-final-close-v1"},
        indicator_input={"families": ["ohlcv_ta"], "lookback_days": 126},
    )

    assert first.bundle_hash == second.bundle_hash
    assert first.pit_universe.content_hash == second.pit_universe.content_hash
    assert first.delisting.content_hash == second.delisting.content_hash
    assert first.indicator_input.content_hash == second.indicator_input.content_hash


def test_bundle_rejects_mixed_as_of_dates() -> None:
    bundle = _bundle()
    changed = build_immutable_snapshot(
        kind="delisting",
        as_of=date(2026, 8, 19),
        source=bundle.delisting.source,
        payload=bundle.delisting.payload,
        lineage_refs=bundle.delisting.lineage_refs,
        captured_at=bundle.delisting.captured_at,
    )

    errors = validate_snapshot_bundle(bundle.model_copy(update={"delisting": changed}))

    assert errors
    assert any("share the bundle as_of" in error for error in errors)
