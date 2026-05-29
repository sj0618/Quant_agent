from ai_graph.jobs import InMemoryAnalysisJobStore, classify_failure


def test_connection_timeout_maps_to_safe_failure_bucket() -> None:
    diagnostic = classify_failure(ConnectionError("connection timeout expired: secret DSN details"), stage="data_collect")

    assert diagnostic.category == "infrastructure_failure"
    assert diagnostic.subcause == "db_connect_timeout"
    assert diagnostic.owner == "data_source_config"
    assert diagnostic.retryable is True
    assert "secret" not in diagnostic.safe_message.lower()
    assert "dsn" not in diagnostic.safe_message.lower()


def test_run_job_sync_uses_safe_failed_envelope_instead_of_raw_exception() -> None:
    store = InMemoryAnalysisJobStore()
    job = store.create("RSI가 30 이하인 KOSPI200")

    failed = store.run_sync(job.job_id, lambda _query, _trace_id: (_ for _ in ()).throw(ConnectionError("connection timeout expired: raw host")))

    assert failed.result is not None
    assert failed.result.status == "failed"
    assert failed.result.failure_cause is not None
    assert failed.result.failure_cause.subcause == "db_connect_timeout"
    assert "raw host" not in failed.result.user_payload.message
