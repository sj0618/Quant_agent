from ai_graph.data_sources import PipelineDataUnavailableError
from ai_graph.jobs import InMemoryAnalysisJobStore, classify_failure


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
