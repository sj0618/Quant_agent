from __future__ import annotations

import pytest

from ai_graph.immutable_results import read_immutable_result_evidence


class _Connection:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row
        self.sql = ""

    def execute(self, sql: str, _params: tuple[str, ...]):
        self.sql = sql
        return self

    def fetchone(self) -> dict[str, object] | None:
        return self.row


def _row() -> dict[str, object]:
    return {
        "job_id": "job-1",
        "execution_spec_version": "strategy-execution-spec.v1",
        "execution_spec_hash": "a" * 64,
        "analysis_result_id": "result-1",
        "manifest_hash": "b" * 64,
        "source": "postgres",
        "as_of": "2026-08-28",
        "observations": "500",
        "candidate_count": "2",
        "successful_aoai_calls": "1",
        "immutable_trigger_present": True,
    }


def test_evidence_projection_joins_immutable_result_and_counts_only_successful_aoai_calls() -> None:
    connection = _Connection(_row())

    evidence = read_immutable_result_evidence(connection, "job-1")

    assert evidence is not None
    assert evidence.execution_spec_version == "strategy-execution-spec.v1"
    assert evidence.successful_aoai_calls == 1
    assert "app.analysis_result" in connection.sql
    assert "model_call.status = 'succeeded'" in connection.sql
    assert "app.ai_prompt_log" not in connection.sql
    assert "assistant_response" not in connection.sql


def test_evidence_projection_rejects_an_incomplete_database_row() -> None:
    row = _row()
    del row["manifest_hash"]

    with pytest.raises(ValueError, match="invalid shape"):
        read_immutable_result_evidence(_Connection(row), "job-1")
