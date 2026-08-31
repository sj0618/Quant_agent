from datetime import date

from scripts.benchmark_ingestion_capacity import run_capacity_benchmark


def test_capacity_benchmark_emits_load_freshness_and_recovery_artifacts() -> None:
    report = run_capacity_benchmark(rows=20, as_of=date(2026, 8, 21))

    assert report["execution_scope"] == "local_normalizer_and_resume_control_flow"
    assert report["load"]["rows_requested"] == 20
    assert report["load"]["rows_normalized"] == 20
    assert report["load"]["rows_per_second"] > 0
    assert report["freshness"]["input_as_of"] == "2026-08-21"
    assert report["freshness"]["status"] == "measured_local_only"
    assert report["recovery"] == {
        "failed_records_before_resume": 1,
        "recovered_records_after_resume": 1,
        "recovery_status": "pass",
    }
