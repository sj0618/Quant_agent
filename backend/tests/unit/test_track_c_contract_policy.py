from __future__ import annotations

import pytest

from app.api.contract_policy import (
    CONTRACT_POLICY,
    TRACK_A_CONTRACT_POLICY,
    TRACK_C_CONTRACT_POLICY,
    api_status_endpoints,
    fe_live_allowlist,
    get_contract,
    raise_feature_not_implemented,
)
from app.core.errors import AppError


def test_track_ac_contract_policy_is_the_ordered_union_of_track_a_and_track_c():
    assert CONTRACT_POLICY == TRACK_A_CONTRACT_POLICY + TRACK_C_CONTRACT_POLICY
    assert len({item.key for item in CONTRACT_POLICY}) == len(CONTRACT_POLICY)
    assert {(entry["method"], entry["path"]) for entry in api_status_endpoints()} == {
        (item.method, item.path) for item in CONTRACT_POLICY
    }
    assert fe_live_allowlist() == {
        (item.method, item.path) for item in CONTRACT_POLICY if item.fe_live_allowed
    }


def test_track_ac_contract_metadata_updates_classified_openapi_operations():
    from app.main import create_app

    schema = create_app().openapi()

    assert schema["paths"]["/health"]["get"]["x-quantagent-owner"] == "backend"
    assert schema["paths"]["/api/v1/auth/me"]["get"]["x-quantagent-auth-required"] is True
    assert "/auth/me" not in schema["paths"]
    assert schema["paths"]["/api/v1/api-status"]["get"]["x-quantagent-implementation"] == "schema-only-not-db"
    assert schema["paths"]["/api/v1/runs"]["post"]["x-quantagent-owner"] == "backend"
    assert schema["paths"]["/api/v1/runs"]["post"]["x-quantagent-csrf-required-for-unsafe"] is True
    assert schema["paths"]["/api/v1/runs/{run_id}"]["get"]["x-quantagent-implementation"] == "db-backed"
    assert schema["paths"]["/api/v1/runs"]["post"]["x-quantagent-fe-live-allowed"] is True
    assert schema["paths"]["/api/v1/runs"]["post"]["x-quantagent-production-ready"] is True
    assert schema["paths"]["/api/v1/runs/{run_id}/complete"]["post"]["x-quantagent-fe-live-allowed"] is True
    assert schema["paths"]["/api/v1/runs/{run_id}/complete"]["post"]["x-quantagent-production-ready"] is True
    assert schema["paths"]["/api/v1/me/notifications"]["patch"]["x-quantagent-csrf-required-for-unsafe"] is True
    assert schema["paths"]["/api/v1/me/email-deliveries"]["get"]["x-quantagent-auth-required"] is True
    assert schema["paths"]["/api/v1/me/email-reports/{report_id}"]["get"]["x-quantagent-production-ready"] is True
    assert schema["paths"]["/api/v1/unsubscribe"]["post"]["x-quantagent-auth-required"] is False
    assert schema["paths"]["/api/v1/reports"]["get"]["x-quantagent-auth-required"] is True
    assert schema["paths"]["/api/v1/reports/{report_id}"]["get"]["x-quantagent-production-ready"] is True
    # `/ai/backtests/generate-and-run` is gone: it duplicated the AI graph's own public
    # surface. Assert its absence so re-registering it has to be a deliberate act.
    assert "/ai/backtests/generate-and-run" not in schema["paths"]


def test_track_c_contract_lookup_and_guard_rails():
    contract = get_contract("get", "/api/v1/reports/{report_id}")
    assert contract is not None
    assert contract.path == "/api/v1/reports/{report_id}"
    assert contract.auth_required is True

    with pytest.raises(AppError) as exc:
        raise_feature_not_implemented(feature="legacy-digest", method="POST", path="/api/v1/runs")
    assert exc.value.code == "feature_not_implemented"
