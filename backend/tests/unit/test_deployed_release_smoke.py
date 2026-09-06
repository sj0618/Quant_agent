"""The login-free deployed-release smoke: its judgement logic and its workflow contract."""

import importlib.util
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SMOKE_SCRIPT = REPOSITORY_ROOT / "scripts" / "deployed_release_smoke.py"
SMOKE_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "deployed-release-smoke.yml"
DEPLOY_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "deploy.yml"


def _smoke_module():
    spec = importlib.util.spec_from_file_location("deployed_release_smoke", SMOKE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_a_job_is_terminal_only_once_it_carries_a_result():
    smoke = _smoke_module()

    assert smoke.is_terminal({"job_id": "j", "stages": [], "result": None}) is False
    assert smoke.is_terminal({"job_id": "j", "result": {"status": "ready"}}) is True
    assert smoke.is_terminal(None) is False


def test_evaluation_accepts_only_the_expected_result_statuses():
    smoke = _smoke_module()
    ready = {"result": {"status": "ready", "user_payload": {"headline": "매수 후보 3종"}}}
    failed = {
        "result": {
            "status": "failed",
            "user_payload": {"headline": "분석 실패", "message": "provider unavailable"},
            "failure_cause": {"failure_stage": "backtest"},
        }
    }

    passed, reason = smoke.evaluate_job(ready, ("ready",))
    assert passed is True
    assert "status=ready" in reason

    passed, reason = smoke.evaluate_job(failed, ("ready",))
    assert passed is False
    assert "status=failed" in reason and "backtest" in reason

    passed, _ = smoke.evaluate_job(failed, ("ready", "failed"))
    assert passed is True
    assert smoke.evaluate_job({"result": None}, ("ready",)) == (False, "job has no result yet")


def test_smoke_workflow_follows_the_deploy_and_targets_the_release_it_starts():
    """It runs after a successful deploy, against the same tree and ports deploy.yml
    starts, and reaches the API on loopback with a minted session - never via Google."""

    workflow = SMOKE_WORKFLOW.read_text(encoding="utf-8")
    deploy = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_run:" in workflow
    assert "- Deploy to SSH Server" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "/home/etluser/mvp_sp2/quant-proj" in workflow
    assert 'APP_DIR="$HOME/mvp_sp2/quant-proj"' in deploy
    assert 'COMBINED_PORT: "18011"' in workflow and "--port 18011" in deploy
    assert 'GATEWAY_PORT: "18010"' in workflow and 'PORT="18010"' in deploy
    assert "scripts/deployed_release_smoke.py" in workflow
    assert "readiness-semantic-gate.mjs" in workflow
    assert "auth/google" not in workflow
    assert "qt-agent.kro.kr:38010" not in workflow
    assert re.search(r"--expect ready", workflow)
    # ssh does not re-quote its arguments for the remote login shell: the query (which
    # legitimately contains parentheses, spaces and Korean) must never be passed raw.
    assert '"$SMOKE_QUERY" <<' not in workflow
    assert "base64 -w0" in workflow and "base64 -d" in workflow


def test_smoke_script_mints_and_revokes_its_own_session_instead_of_logging_in():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "AuthSessionStore" in source
    assert "create_session(user_id=user_id)" in source
    assert "revoke_session(" in source
    assert "auth/google" not in source
    assert 'user_id = f"qa-smoke:' in source
