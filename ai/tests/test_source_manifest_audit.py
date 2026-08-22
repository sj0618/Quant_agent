from __future__ import annotations

import json

from ai_graph.source_manifest import build_source_manifest
from ai_graph.source_manifest_audit import (
    audit_source_manifest_samples,
    load_source_manifest_samples,
)


def _manifest(*, source: str = "postgres") -> dict[str, object]:
    return build_source_manifest(
        source=source,
        as_of="2026-08-20",
        freshness="fresh",
        lineage_refs=["mart.common_stock_universe_asof", "core.adjusted_ohlcv"],
        source_version="warehouse-release-v1",
    ).model_dump(mode="json")


def test_release_manifest_sample_audit_has_complete_fields_and_matching_hashes() -> None:
    report = audit_source_manifest_samples([_manifest(), _manifest()])

    assert report.valid is True
    assert report.sample_count == 2
    assert report.required_field_missing_count == 0
    assert report.hash_match_count == 2
    assert report.hash_mismatch_count == 0
    assert report.required_fields_present_rate == 1.0
    assert report.hash_match_rate == 1.0
    assert all(sample.valid for sample in report.samples)


def test_release_manifest_sample_audit_catches_missing_fixture_and_recomputed_hash_mismatch() -> None:
    missing = _manifest()
    del missing["freshness"]
    fixture = _manifest(source="fixture")
    corrupted = _manifest()
    corrupted["source_version"] = "tampered"

    report = audit_source_manifest_samples([missing, fixture, corrupted])

    assert report.valid is False
    assert report.required_field_missing_count == 1
    assert report.samples_with_missing_required_fields == 1
    assert report.hash_mismatch_count == 1
    assert "freshness" in report.samples[0].missing_required_fields
    assert report.samples[1].validation_errors
    assert report.samples[2].hash_matches is False


def test_manifest_sample_file_loader_accepts_samples_envelope(tmp_path) -> None:
    sample_file = tmp_path / "release-manifest-samples.json"
    sample_file.write_text(json.dumps({"samples": [_manifest()]}), encoding="utf-8")

    loaded = load_source_manifest_samples(sample_file)

    assert len(loaded) == 1
    assert loaded[0]["source"] == "postgres"
