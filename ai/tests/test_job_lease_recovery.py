"""CORE-JOB-01: restart recovery decides by lease, not by "written by someone else".

`owner_incarnation` only says a different process wrote the row. It cannot say whether
that process is still alive, so a sweep driven by it alone settles work a sibling worker
is actively running. A lease answers the question directly: a holder that keeps renewing
is working, and one that stopped renewing has, by the only evidence available, stopped.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_graph.job_repository_postgres import _row_level_fields
from ai_graph.job_store_persistent import PersistentAnalysisJobStore
from ai_graph.jobs import (
    PROCESS_INCARNATION,
    AnalysisJobStatus,
    InMemoryAnalysisJobStore,
    JobStoreConfigurationError,
    _lease_is_live,
    reap_interrupted_jobs,
)

DEAD_OWNER = "4242:deadbeefcafe"
LIVE_SIBLING = "8888:alivecafe0001"


def _running_job(**overrides):
    store = InMemoryAnalysisJobStore()
    job = store.create_job("RSI가 30 이하인 KOSPI200")
    store.update_job_status(job.job_id, AnalysisJobStatus.RUNNING, "interpreting")
    store.jobs[job.job_id] = store.jobs[job.job_id].model_copy(update=overrides)
    return store, job.job_id


def test_a_live_lease_protects_a_sibling_workers_job() -> None:
    """The case the incarnation rule got wrong: alive, mid-run, and not us."""

    store, job_id = _running_job(
        owner_incarnation=LIVE_SIBLING,
        lease_expires_at=datetime.now(UTC) + timedelta(seconds=30),
    )

    assert reap_interrupted_jobs(store, incarnation=PROCESS_INCARNATION) == []
    assert store.get_job(job_id).status is AnalysisJobStatus.RUNNING


def test_an_expired_lease_means_the_owner_stopped_renewing() -> None:
    store, job_id = _running_job(
        owner_incarnation=DEAD_OWNER,
        lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    assert reap_interrupted_jobs(store, incarnation=PROCESS_INCARNATION) == [job_id]
    assert store.get_job(job_id).status is AnalysisJobStatus.FAILED


def test_a_job_with_no_lease_still_falls_back_to_the_incarnation_rule() -> None:
    """In-memory stores never take a lease; that path must keep working."""

    store, job_id = _running_job(owner_incarnation=DEAD_OWNER)

    assert reap_interrupted_jobs(store, incarnation=PROCESS_INCARNATION) == [job_id]


def test_our_own_live_job_is_never_reaped() -> None:
    store, _ = _running_job(owner_incarnation=PROCESS_INCARNATION)

    assert reap_interrupted_jobs(store, incarnation=PROCESS_INCARNATION) == []


def test_a_naive_expiry_is_read_as_utc_rather_than_crashing() -> None:
    """A row read back without a timezone must not take startup down."""

    store, job_id = _running_job(
        owner_incarnation=LIVE_SIBLING,
        lease_expires_at=(datetime.now(UTC) + timedelta(seconds=30)).replace(tzinfo=None),
    )

    assert _lease_is_live(store.get_job(job_id)) is True
    assert reap_interrupted_jobs(store, incarnation=PROCESS_INCARNATION) == []


def test_row_level_columns_are_merged_onto_the_decoded_job() -> None:
    """A job read without its version cannot be written back: CAS would use the default."""

    expiry = datetime.now(UTC)
    assert _row_level_fields({"job_jsonb": {}, "version": 7, "lease_expires_at": expiry}) == {
        "version": 7,
        "lease_expires_at": expiry,
    }


def test_a_row_without_the_lease_columns_decodes_anyway() -> None:
    """Reads that predate the columns, and the fakes in the other job tests."""

    assert _row_level_fields({"job_jsonb": {}}) == {}
    assert _row_level_fields({"job_jsonb": {}, "version": None}) == {}


def test_a_store_without_lease_support_refuses_to_pretend_it_claimed() -> None:
    """A claim that always succeeds is worse than none: callers read it as arbitration."""

    class _NoLeaseRepository:
        store_mode = "persistent"

        def create_job(self, request_text, **_kwargs):  # pragma: no cover - unused
            raise NotImplementedError

        def get_job(self, job_id): ...
        def update_job_status(self, job_id, status, polling_stage, **_kwargs): ...
        def complete_job(self, job_id, result_envelope, **_kwargs): ...
        def fail_job(self, job_id, error_message, **_kwargs): ...
        def list_jobs(self, *, limit=100): return []

    store = PersistentAnalysisJobStore(_NoLeaseRepository())
    with pytest.raises(JobStoreConfigurationError):
        store.claim_job("job_1", owner="worker-a", lease_seconds=30)


def test_lease_calls_reach_the_repository() -> None:
    class _LeaseRepository:
        store_mode = "persistent"

        def __init__(self):
            self.calls = []

        def create_job(self, request_text, **_kwargs):  # pragma: no cover - unused
            raise NotImplementedError

        def get_job(self, job_id): ...
        def update_job_status(self, job_id, status, polling_stage, **_kwargs): ...
        def complete_job(self, job_id, result_envelope, **_kwargs): ...
        def fail_job(self, job_id, error_message, **_kwargs): ...
        def list_jobs(self, *, limit=100): return []

        def claim_job(self, job_id, *, owner, lease_seconds):
            self.calls.append(("claim", job_id, owner, lease_seconds))
            return 3

        def renew_lease(self, job_id, *, owner, lease_seconds):
            self.calls.append(("renew", job_id, owner, lease_seconds))
            return True

        def release_lease(self, job_id, *, owner):
            self.calls.append(("release", job_id, owner))
            return True

    repository = _LeaseRepository()
    store = PersistentAnalysisJobStore(repository)

    assert store.claim_job("job_1", owner="worker-a", lease_seconds=30) == 3
    assert store.renew_lease("job_1", owner="worker-a", lease_seconds=30) is True
    assert store.release_lease("job_1", owner="worker-a") is True
    assert [call[0] for call in repository.calls] == ["claim", "renew", "release"]
