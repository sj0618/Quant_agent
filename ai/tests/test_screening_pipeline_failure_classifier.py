import pytest

from ai_graph.data_sources import PipelineDataUnavailableError
from ai_graph.jobs import InMemoryAnalysisJobStore, classify_failure
from ai_graph.schemas import APIEnvelope


def test_connection_timeout_maps_to_safe_failure_bucket() -> None:
    diagnostic = classify_failure(ConnectionError("connection timeout expired: secret DSN details"), stage="data_collect")

    assert diagnostic.category == "infrastructure_failure"
    assert diagnostic.subcause == "db_connect_timeout"
    assert diagnostic.owner == "data_source_config"
    assert diagnostic.retryable is True
    assert "secret" not in diagnostic.safe_message.lower()
    assert "dsn" not in diagnostic.safe_message.lower()


def test_empty_screen_is_a_data_gap_answer_not_an_unknown_crash() -> None:
    """An empty warehouse result must tell the user their condition matched nothing.

    Both empty-data paths were raised as bare ValueErrors, so they fell through every
    branch of classify_failure into unknown_failure - "분류되지 않은 오류", which says
    nothing about the screen having simply matched no names and is indistinguishable
    from a genuine crash.
    """

    diagnostic = classify_failure(
        PipelineDataUnavailableError(
            "no_screening_matches",
            "no screening candidates found in mart.kis_adjusted_feature_frame_asof",
        ),
        stage="finalizing",
    )

    assert diagnostic.category == "data_gap"
    assert diagnostic.subcause == "no_screening_matches"
    # Nothing to retry: the same query against the same data matches nothing again.
    assert diagnostic.retryable is False
    assert "조건" in diagnostic.safe_message
    # Internal table names stay out of the public message.
    assert "mart." not in diagnostic.safe_message


def test_missing_price_history_is_reported_separately_from_an_empty_screen() -> None:
    diagnostic = classify_failure(
        PipelineDataUnavailableError("no_price_rows", "returned no price rows for 005930"),
        stage="finalizing",
    )

    assert diagnostic.category == "data_gap"
    assert diagnostic.subcause == "no_price_rows"
    assert "005930" not in diagnostic.safe_message


def test_split_release_fixture_guard_is_a_safe_classified_failure() -> None:
    """A split-source release guard must not degrade into a schema-validation 500."""

    from ai_graph.data_sources import db_split

    diagnostic = classify_failure(
        db_split.FixtureModeForbiddenError("must-not-leak"),
        stage="data_loading",
    )

    assert diagnostic.category == "infrastructure_failure"
    assert diagnostic.subcause == "fixture_mode_forbidden_in_release"
    assert diagnostic.owner == "data_source_config"
    assert diagnostic.retryable is False
    assert "must-not-leak" not in diagnostic.safe_message


def test_run_job_sync_reports_an_empty_screen_as_a_finished_failed_job() -> None:
    """The job must reach a terminal state, not stay RUNNING.

    A job left RUNNING is what the client eventually gives up on at its wall-clock
    limit, which is why an empty screen used to surface as a timeout rather than as
    the answer "아무 종목도 조건에 맞지 않았습니다".
    """

    store = InMemoryAnalysisJobStore()
    job = store.create("반도체 섹터 주도주 중 상대강도 강한 종목을 찾아줘")

    def runner(_query: str, _trace_id: str) -> object:
        raise PipelineDataUnavailableError("no_screening_matches", "internal detail")

    failed = store.run_sync(job.job_id, runner)  # type: ignore[arg-type]

    assert failed.result is not None
    assert failed.result.status == "failed"
    assert failed.result.failure_cause is not None
    assert failed.result.failure_cause.category == "data_gap"
    assert "internal detail" not in failed.result.user_payload.message


def test_run_job_sync_uses_safe_failed_envelope_instead_of_raw_exception() -> None:
    store = InMemoryAnalysisJobStore()
    job = store.create("RSI가 30 이하인 KOSPI200")

    failed = store.run_sync(job.job_id, lambda _query, _trace_id: (_ for _ in ()).throw(ConnectionError("connection timeout expired: raw host")))

    assert failed.result is not None
    assert failed.result.status == "failed"
    assert failed.result.failure_cause is not None
    assert failed.result.failure_cause.subcause == "db_connect_timeout"
    assert "raw host" not in failed.result.user_payload.message


def test_schema_validation_failure_does_not_zero_fill_a_successful_analysis() -> None:
    """Malformed graph output is terminal and cannot inherit success-shaped values.

    A schema mismatch is not a data shortage: retrying it cannot make the malformed
    payload valid.  The job therefore needs the stable contract failure code and a
    payload with none of the fields that a client could render as a completed analysis.
    """

    store = InMemoryAnalysisJobStore()
    job = store.create("RSI가 30 이하인 KOSPI200")

    def runner(_query: str, _trace_id: str) -> APIEnvelope:
        # Use the actual public result schema rather than a message-shaped ValueError.
        # This lacks all required envelope fields except the nominal status, so Pydantic
        # raises a genuine ValidationError at the runner boundary.
        return APIEnvelope.model_validate({"status": "ready"})

    failed = store.run_sync(job.job_id, runner)  # type: ignore[arg-type]

    assert failed.status == "failed"
    assert failed.completed_at is not None
    assert failed.result is not None
    assert failed.result.status == "failed"
    assert failed.result.retryable is False
    assert failed.result.failure_cause is not None
    assert failed.result.failure_cause.category == "semantic_failure"
    assert failed.result.failure_cause.subcause == "contract_shape_error"
    assert failed.result.strategy_spec is None
    assert failed.result.user_payload.candidate_cards == []
    assert failed.result.user_payload.ticker_actions == []
    assert failed.result.user_payload.performance is None
    assert failed.result.user_payload.report is None
    assert failed.result.user_payload.recommendation_gate is None
    assert "analysis runner" not in failed.result.user_payload.message


@pytest.mark.parametrize("empty_result", [{}, None])
def test_empty_runner_result_is_not_completed_or_reused_as_an_analysis(
    empty_result: object,
) -> None:
    """An empty runner result must be a terminal unavailable envelope, not a crash.

    Empty output and malformed schema output are separate operator diagnoses.  Neither
    may reach the completed-job path or leak a prior success-shaped analysis payload.
    """

    store = InMemoryAnalysisJobStore()
    job = store.create("RSI가 30 이하인 KOSPI200")

    failed = store.run_sync(  # type: ignore[arg-type]
        job.job_id,
        lambda _query, _trace_id: empty_result,
    )

    assert failed.status == "failed"
    assert failed.completed_at is not None
    assert failed.result is not None
    assert failed.result.status == "failed"
    assert failed.result.retryable is False
    assert failed.result.failure_cause is not None
    assert failed.result.failure_cause.category == "data_gap"
    assert failed.result.failure_cause.subcause == "empty_analysis_result"
    assert failed.result.user_payload.candidate_cards == []
    assert failed.result.user_payload.ticker_actions == []
    assert failed.result.user_payload.performance is None
    assert failed.result.user_payload.report is None
    assert failed.result.user_payload.recommendation_gate is None
    assert "analysis runner" not in failed.result.user_payload.message


def test_lock_exhaustion_is_named_not_swallowed_as_unknown() -> None:
    """`out of shared memory` is a warehouse capacity fault, not a mystery.

    psycopg surfaces the server's lock-table exhaustion as OutOfMemory, whose message
    carries none of the words the string heuristics look for. A production run died this
    way in the Data node and was reported as "분류되지 않은 오류", which reads as an AI
    bug and gave the user no reason to retry - the one thing that would have worked.
    """

    class OutOfMemory(Exception):
        """Stands in for psycopg.errors.OutOfMemory, matched by type name."""

    diagnostic = classify_failure(
        OutOfMemory("out of shared memory\nHINT: You might need to increase max_locks_per_transaction."),
        stage="data_collect",
    )

    assert diagnostic.category == "infrastructure_failure"
    assert diagnostic.subcause == "db_lock_capacity_exhausted"
    assert diagnostic.owner == "data_source_config"
    # Retrying is the correct advice: the lock table is shared, so the same query
    # succeeds once whatever else was holding chunks finishes.
    assert diagnostic.retryable is True
    # The stage the caller reached is preserved rather than replaced with finalizing.
    assert diagnostic.failure_stage == "data_collect"
    # Server internals stay out of the public message.
    assert "shared memory" not in diagnostic.safe_message
    assert "max_locks" not in diagnostic.safe_message


def test_lock_exhaustion_matches_on_message_when_type_name_differs() -> None:
    """Drivers other than psycopg raise their own class for the same server error."""

    diagnostic = classify_failure(
        RuntimeError("ERROR: out of shared memory"), stage="data_collect"
    )

    assert diagnostic.subcause == "db_lock_capacity_exhausted"
