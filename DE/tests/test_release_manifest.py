from datetime import date

import pytest

from quant_agent.data.release_manifest import (
    audit_release_manifest_samples,
    build_release_manifest,
    compute_lineage_hash,
    validate_release_manifest,
)


def _manifest(**overrides):
    manifest = build_release_manifest(
        source="KRX",
        as_of=date(2026, 8, 21),
        freshness="ingested-through:2026-08-21",
        lineage_refs=("raw.ohlcv_response", "core.ohlcv_daily"),
        source_version="krx-ohlcv.v1",
        fallback_count=0,
    ).to_dict()
    manifest.update(overrides)
    return manifest


def test_release_manifest_cross_review_preserves_required_provenance_and_zero_fallback() -> None:
    manifest = _manifest()

    assert {"source", "as_of", "freshness", "lineage_hash"} <= manifest.keys()
    assert manifest["fallback_count"] == 0
    assert manifest["lineage_hash"] == compute_lineage_hash(manifest)
    assert validate_release_manifest(manifest) == ()


def test_release_manifest_audit_reports_complete_fields_and_matching_hashes() -> None:
    report = audit_release_manifest_samples([_manifest(), _manifest()])

    assert report.valid is True
    assert report.required_field_missing_count == 0
    assert report.hash_mismatch_count == 0
    assert report.fallback_violation_count == 0
    assert report.required_fields_present_rate == 1.0
    assert report.hash_match_rate == 1.0
    assert report.fallback_zero_rate == 1.0


def test_release_manifest_rejects_missing_freshness_nonzero_fallback_and_hash_drift() -> None:
    missing_freshness = _manifest(freshness="")
    fallback = _manifest(fallback_count=1)
    changed = _manifest(source_version="tampered")

    assert any("freshness" in error for error in validate_release_manifest(missing_freshness))
    assert any("fallback_count" in error for error in validate_release_manifest(fallback))
    assert any("lineage_hash" in error for error in validate_release_manifest(changed))

    report = audit_release_manifest_samples([missing_freshness, fallback, changed])
    assert report.valid is False
    assert report.fallback_violation_count == 1
    assert report.hash_mismatch_count == 2


def test_release_manifest_rejects_fixture_proxy_and_mock_sources() -> None:
    for source in ("fixture", "proxy", "mock"):
        with pytest.raises(ValueError, match="forbidden"):
            build_release_manifest(
                source=source,
                as_of=date(2026, 8, 21),
                freshness="fresh",
                lineage_refs=("test",),
                fallback_count=0,
            )
