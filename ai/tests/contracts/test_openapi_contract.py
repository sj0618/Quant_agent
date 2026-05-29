from fastapi.testclient import TestClient

from ai_graph.api import (
    ANALYSIS_JOB_DETAIL_PATH,
    ANALYSIS_JOBS_PATH,
    API_STATUS_PATH,
    HEALTH_PATH,
    OPENAPI_URL,
    create_app,
)
from ai_graph.jobs import InMemoryAnalysisJobStore


def test_openapi_contract_keeps_core_routes_and_components() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    response = client.get(OPENAPI_URL)

    assert response.status_code == 200
    schema = response.json()
    components = schema["components"]["schemas"]

    assert HEALTH_PATH in schema["paths"]
    assert API_STATUS_PATH in schema["paths"]
    assert ANALYSIS_JOBS_PATH in schema["paths"]
    assert ANALYSIS_JOB_DETAIL_PATH in schema["paths"]
    assert "APIEnvelope" in components
    assert "AnalysisJob" in components
    assert "ReportBundle" in components


def test_openapi_analysis_job_result_uses_api_envelope_schema() -> None:
    client = TestClient(create_app(InMemoryAnalysisJobStore()))

    components = client.get(OPENAPI_URL).json()["components"]["schemas"]
    analysis_job = components["AnalysisJob"]
    result_schema = analysis_job["properties"]["result"]

    assert "APIEnvelope" in str(result_schema)
