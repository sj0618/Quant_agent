import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "deploy.yml"
HEALTH_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "server-health.yml"
READINESS_GATE = REPOSITORY_ROOT / "scripts" / "readiness-semantic-gate.mjs"
AI_API_SOURCE = REPOSITORY_ROOT / "ai" / "ai_graph" / "api.py"
SERVICE_DB_REPLAY = REPOSITORY_ROOT / "service_db" / "scripts" / "verify_fixed_migration_replay.py"


def _canonical_fixed_migrations() -> list[str]:
    """The ordered migration set the service DB replay contract pins as canonical."""

    source = SERVICE_DB_REPLAY.read_text(encoding="utf-8")
    block = source.split("FIXED_MIGRATIONS = (", maxsplit=1)[1].split(")", maxsplit=1)[0]
    return re.findall(r'"([^"]+\.sql)"', block)


def test_deploy_uses_the_backtest_dependency_graph_and_verifies_imports():
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert '-e "$APP_DIR/backtest_module"' in workflow
    assert '-e "$APP_DIR/backend"' in workflow
    assert '-e "$APP_DIR/ai"' in workflow
    assert "import backtest_module, quantstats" in workflow


def test_deploy_requires_offline_release_trust_and_fail_closed_readiness():
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "release-trust:\n    name: Offline release-trust gate" in workflow
    assert "deploy:\n    needs: release-trust" in workflow
    assert "push:" not in workflow.split("concurrency:", maxsplit=1)[0]
    assert "Verify same-SHA S/R/O/C release evidence" in workflow
    assert "node scripts/evaluate-release-trust.mjs --verify-release-evidence" in workflow
    assert "RELEASE_TRUST_REPOSITORY: ${{ github.repository }}" in workflow
    for kind in ("S", "R", "O", "C"):
        assert f"RELEASE_EVIDENCE_{kind}_REF" in workflow
        assert f"RELEASE_EVIDENCE_{kind}_SHA" in workflow
    assert "node scripts/evaluate-release-trust.mjs" in workflow
    assert "Verify pre-deploy readiness" in workflow
    assert "Create deploy snapshot archive" in workflow
    assert "Mark deploy mutation started" in workflow
    assert 'DEPLOY_MUTATION_STARTED=true' in workflow
    assert "failure() && env.DEPLOY_MUTATION_STARTED == 'true'" in workflow
    assert "http://127.0.0.1:18001/ai-api/readiness" in workflow
    assert 'node scripts/readiness-semantic-gate.mjs --label "$label"' in workflow
    assert "current-backend-readiness" in workflow
    assert "current-ai-api-readiness" in workflow
    assert "No deploy snapshot available to restore" in workflow
    assert "rollback-applied.marker" in workflow
    assert "restart_restored_release" in workflow
    assert 'wait_for_semantic_readiness "Backend readiness" "http://127.0.0.1:18001/readiness" "rollback-backend-readiness"' in workflow
    assert 'wait_for_semantic_readiness "AI API readiness" "http://127.0.0.1:18001/ai-api/readiness" "rollback-ai-api-readiness"' in workflow
    assert '"014_create_report_email_tables.sql"' in workflow
    assert '"022_immutable_analysis_results.sql"' in workflow
    assert workflow.index('"014_create_report_email_tables.sql"') < workflow.index(
        '"022_immutable_analysis_results.sql"'
    )
    assert '"024_parse_bound_analysis_job_admission.sql"' in workflow
    assert 'REQUIRED_AI_CONTRACT_VERSION = "ai-mvp.v1"' in (
        REPOSITORY_ROOT / "ai" / "ai_graph" / "api.py"
    ).read_text(encoding="utf-8")
    assert "AUTH_TRUSTED_PROXY_HEADERS=true" in workflow
    assert "AUTH_TRUSTED_PROXY_HOSTS=127.0.0.1,::1" in workflow
    auth_unset_block = workflow.split("for auth_var in", maxsplit=1)[1].split("do", maxsplit=1)[0]
    assert "AUTH_TRUSTED_PROXY_HEADERS" in auth_unset_block
    assert "AUTH_TRUSTED_PROXY_HOSTS" in auth_unset_block
    assert 'settings.auth_trusted_proxy_headers' in workflow
    assert 'set(settings.trusted_proxy_hosts) == {"127.0.0.1", "::1"}' in workflow
    assert "xfwd: true" in (REPOSITORY_ROOT / "fe" / "vite.config.ts").read_text(encoding="utf-8")
    assert "node scripts/production-gateway.mjs" in workflow
    assert 'HOST="127.0.0.1" PORT="18000"' in workflow
    assert "retired-internal-route" in workflow
    assert "npm run preview" not in workflow
    assert "AI_RULE_DRAFT_HMAC_SECRET" in workflow
    assert "ai-rule-draft-hmac.secret" in workflow
    assert "--exclude='.releases/'" in workflow
    assert "--exclude='.run/'" in workflow
    assert "--exclude='.venv/'" in workflow
    assert "--exclude='venv/'" in workflow
    assert "--exclude='**/.venv/'" in workflow
    assert "--exclude='**/venv/'" in workflow
    assert "--exclude='ai/.venv/'" in workflow
    assert workflow.index("Verify pre-deploy readiness") < workflow.index(
        "Create deploy snapshot archive"
    )
    assert workflow.index("Create deploy snapshot archive") < workflow.index("Deploy via rsync")
    assert workflow.index("Deploy via rsync") < workflow.index("Restore deploy snapshot on failure")
    assert workflow.index("Mark deploy mutation started") < workflow.index("Deploy via rsync")
    assert workflow.index("Restore deploy snapshot on failure") < workflow.index("restart_restored_release")


def test_deploy_ai_audit_replay_applies_every_canonical_migration_in_order():
    """The deploy AI-audit replay must apply the full canonical migration set, in order.

    Dropping any of them (this is how 015-018 were silently omitted, so freshly
    provisioned databases were missing the notification-settings columns and the
    email-delivery outbox that reachable production endpoints query) must fail here.
    """

    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    canonical = _canonical_fixed_migrations()
    assert len(canonical) >= 12, "canonical FIXED_MIGRATIONS could not be parsed"

    positions: list[int] = []
    for name in canonical:
        marker = f'"{name}"'
        assert marker in workflow, f"deploy workflow is missing migration {name}"
        positions.append(workflow.index(marker))
    assert positions == sorted(positions), "deploy workflow applies migrations out of canonical order"


def _ai_readiness_check_names() -> list[str]:
    """The dependency names the AI API actually publishes on /ai-api/readiness."""

    source = AI_API_SOURCE.read_text(encoding="utf-8")
    block = source.split("def _release_readiness(", maxsplit=1)[1].split("def _core_execution_readiness(", maxsplit=1)[0]
    return re.findall(r'ReadinessCheck\(\s*name="([^"]+)"', block)


def _gate_ai_profile_names() -> list[str]:
    source = READINESS_GATE.read_text(encoding="utf-8")
    block = source.split("REQUIRED_AI_READINESS_CHECKS = Object.freeze([", maxsplit=1)[1].split("]", maxsplit=1)[0]
    return re.findall(r'"([^"]+)"', block)


def test_the_readiness_gate_ai_profile_tracks_the_ai_api_dependency_set():
    """The semantic gate must check the AI API against its own dependency names.

    Gating /ai-api/readiness on the backend names (auth_runtime, main_db,
    trading_data_db, redis) can never pass: the gate reports them as missing and
    reports every AI dependency as unexpected. That is what failed the pre-deploy
    readiness step and left the server pinned to an older revision.
    """

    ai_checks = _ai_readiness_check_names()
    assert ai_checks == [
        "durable_job_store",
        "migration_revision",
        "live_provider_configuration",
        "ai_contract_version",
        "rule_draft_signer",
    ]
    assert _gate_ai_profile_names() == ai_checks


def test_every_readiness_gate_invocation_selects_a_profile():
    for workflow_path in (DEPLOY_WORKFLOW, HEALTH_WORKFLOW):
        workflow = workflow_path.read_text(encoding="utf-8")
        for line in workflow.splitlines():
            if "readiness-semantic-gate.mjs" not in line:
                continue
            assert "--profile" in line, f"{workflow_path.name} gates readiness without a profile: {line.strip()}"

    deploy = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert 'check_readiness "current-ai-api-readiness" "http://127.0.0.1:18001/ai-api/readiness" ai' in deploy
    assert 'check_readiness "current-backend-readiness" "http://127.0.0.1:18001/readiness" backend' in deploy
    for label in ("deployed-ai-api-readiness", "rollback-ai-api-readiness"):
        assert f'"http://127.0.0.1:18001/ai-api/readiness" "{label}" ai' in deploy

    health = HEALTH_WORKFLOW.read_text(encoding="utf-8")
    assert 'check_readiness "AI API readiness" "http://127.0.0.1:$COMBINED_PORT/ai-api/readiness" ai' in health
    # The remote shell starts in $HOME, so a relative gate path resolves outside the
    # deployed tree and the health check dies with MODULE_NOT_FOUND.
    assert 'node "$APP_DIR/scripts/readiness-semantic-gate.mjs"' in health
    assert "| node scripts/readiness-semantic-gate.mjs" not in health
