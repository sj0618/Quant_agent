import json
from datetime import date

from quant_agent.data.freshness_lineage_audit import (
    audit_freshness_lineage,
    compute_lineage_hash,
)
from scripts.rerun_freshness_lineage_audit import main

REVIEWER = {
    "reviewer_id": "조은채",
    "reviewed_at": "2026-08-31",
    "decision": "approved",
    "evidence": "server manifest freshness and lineage hash rerun",
}


def _sample(*, source: str = "postgres", freshness: str = "within_slo") -> dict[str, object]:
    sample: dict[str, object] = {
        "source": source,
        "as_of": date(2026, 8, 21).isoformat(),
        "freshness": freshness,
        "lineage_refs": ["core.ohlcv_daily:2026-08-21", "meta.lineage_event:run-001"],
        "source_version": "pipeline.v1",
    }
    sample["lineage_hash"] = compute_lineage_hash(sample)
    return sample


def test_freshness_lineage_audit_reruns_source_as_of_freshness_and_hash() -> None:
    report = audit_freshness_lineage([_sample()], REVIEWER)

    assert report.passed
    assert report.first_run.source_valid_count == 1
    assert report.first_run.as_of_valid_count == 1
    assert report.first_run.freshness_valid_count == 1
    assert report.first_run.lineage_hash_match_count == 1
    assert report.result_hash_equal
    assert report.provenance_trace_hash_equal
    assert report.reviewer_valid
    assert report.reviewer["reviewer_id"] == "조은채"


def test_freshness_lineage_audit_rejects_fixture_proxy_and_stale_inputs() -> None:
    fixture = _sample(source="fixture")
    proxy = _sample(source="proxy")
    stale = _sample(freshness="stale")

    report = audit_freshness_lineage([fixture, proxy, stale], REVIEWER)

    assert not report.passed
    assert report.first_run.source_valid_count == 1
    assert report.first_run.freshness_valid_count == 2
    assert report.first_run.lineage_hash_match_count == 3
    assert not report.first_run.samples[0].valid
    assert not report.first_run.samples[1].valid
    assert not report.first_run.samples[2].valid


def test_freshness_lineage_audit_cli_writes_reviewer_and_rerun_evidence(tmp_path) -> None:
    input_path = tmp_path / "server-release-manifest.json"
    output_path = tmp_path / "freshness-lineage-audit.json"
    input_path.write_text(
        json.dumps({"samples": [_sample()], "reviewer": REVIEWER}), encoding="utf-8"
    )

    assert main(["--input", str(input_path), "--output", str(output_path)]) == 0

    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert output["status"] == "pass"
    assert output["reviewer"]["reviewer_id"] == "조은채"
    assert output["qa_contract"] == {
        "source_as_of_freshness_hash_rerun": True,
        "result_hash_equal": True,
        "provenance_trace_hash_equal": True,
        "reviewer_record_present": True,
    }
