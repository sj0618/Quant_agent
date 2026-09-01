from __future__ import annotations

from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[3]
    / ".github"
    / "workflows"
    / "ai-staging-pipeline-gate.yml"
)


def test_staging_gate_is_manual_same_sha_and_never_names_the_public_host() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "environment: ai-staging" in workflow
    assert "AI_STAGING_EXPECTED_REVISION: ${{ github.sha }}" in workflow
    assert "python -m ai_graph.staging_pipeline_gate" in workflow
    assert "isolated-staging-ai-pipeline-evidence-${{ github.run_id }}" in workflow
    assert "qt-agent.kro.kr" not in workflow
