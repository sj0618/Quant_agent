import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "deploy.yml"
HEALTH_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "server-health.yml"
SMOKE_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "production-backtest-smoke.yml"
READINESS_GATE = REPOSITORY_ROOT / "scripts" / "readiness-semantic-gate.mjs"
AI_API_SOURCE = REPOSITORY_ROOT / "ai" / "ai_graph" / "api.py"


def test_deploy_uses_the_backtest_dependency_graph_and_verifies_imports():
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert '-e "$APP_DIR/backtest_module"' in workflow
    assert '-e "$APP_DIR/backend"' in workflow
    assert '-e "$APP_DIR/ai"' in workflow
    assert "import backtest_module, quantstats" in workflow


def test_long_running_deploy_and_rollback_sessions_keep_ssh_alive():
    """A quiet restart must not be rolled back just because the SSH transport idles out."""

    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    deploy_restart = workflow.split("- name: Install and restart development servers", maxsplit=1)[1].split(
        "- name: Restore deploy snapshot on failure", maxsplit=1
    )[0]
    rollback = workflow.split("- name: Restore deploy snapshot on failure", maxsplit=1)[1]

    for section in (deploy_restart, rollback):
        assert "ServerAliveInterval=30" in section
        assert "ServerAliveCountMax=20" in section


def test_deploy_requires_offline_release_trust_and_fail_closed_readiness():
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "release-trust:\n    name: Offline release-trust gate" in workflow
    assert "deploy:\n    needs: release-trust" in workflow
    assert "rollback_drill:" in workflow
    assert "Run a controlled non-production rollback drill instead of deploy" in workflow
    assert "Controlled rollback drill" in workflow
    assert 'if: ${{ inputs.rollback_drill == true }}' in workflow
    assert 'if: ${{ inputs.rollback_drill != true }}' in workflow
    assert "node scripts/rollback-drill-harness.mjs --artifact" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "push:" in workflow.split("concurrency:", maxsplit=1)[0]
    assert "branches:\n      - main" in workflow
    assert "if: github.event_name == 'workflow_dispatch'" in workflow
    assert "Verify same-SHA S/R/O/C release evidence" in workflow
    assert "node scripts/evaluate-release-trust.mjs --verify-release-evidence" in workflow
    assert "Verify same-SHA rollback drill evidence" in workflow
    assert "node scripts/evaluate-release-trust.mjs --verify-rollback-evidence" in workflow
    assert "RELEASE_TRUST_REPOSITORY: ${{ github.repository }}" in workflow
    assert "rollback_evidence_ref" in workflow
    assert "rollback_evidence_sha" in workflow
    assert "ROLLBACK_DRILL_EVIDENCE_REF" in workflow
    assert "ROLLBACK_DRILL_EVIDENCE_SHA" in workflow
    for kind in ("S", "R", "O", "C"):
        assert f"RELEASE_EVIDENCE_{kind}_REF" in workflow
        assert f"RELEASE_EVIDENCE_{kind}_SHA" in workflow
    assert "node scripts/evaluate-release-trust.mjs" in workflow
    assert "Verify pre-deploy readiness" in workflow
    assert "Create deploy snapshot archive" in workflow
    assert "Mark deploy mutation started" in workflow
    assert 'DEPLOY_MUTATION_STARTED=true' in workflow
    assert "failure() && env.DEPLOY_MUTATION_STARTED == 'true'" in workflow
    assert "http://127.0.0.1:18011/ai-api/readiness" in workflow
    assert 'node scripts/readiness-semantic-gate.mjs --label "$label"' in workflow
    assert "current-backend-readiness" in workflow
    assert "current-ai-api-readiness" in workflow
    assert "No deploy snapshot available to restore" in workflow
    assert "rollback-applied.marker" in workflow
    assert "restart_restored_release" in workflow
    assert 'wait_for_semantic_readiness "Backend readiness" "http://127.0.0.1:18011/readiness" "rollback-backend-readiness"' in workflow
    assert 'wait_for_semantic_readiness "AI API readiness" "http://127.0.0.1:18011/ai-api/readiness" "rollback-ai-api-readiness"' in workflow
    assert "Database migrations are verified by readiness" in workflow
    assert "no DDL runs in application deploy" in workflow
    assert "conn.execute(" not in workflow
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
    assert 'HOST="0.0.0.0" PORT="18010"' in workflow
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


def test_deploy_never_executes_db_migrations_and_fails_closed_on_readiness():
    """DB migrations are a separate release responsibility, never an app deploy side effect."""

    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert "Database migrations are verified by readiness" in workflow
    assert "psycopg.connect" not in workflow
    assert "conn.execute(" not in workflow
    assert 'wait_for_semantic_readiness "AI API readiness"' in workflow


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
    gate_invocation_tokens = (
        "readiness-semantic-gate.mjs",
        '"$READINESS_CHECKER"',
    )

    for workflow_path in (DEPLOY_WORKFLOW, HEALTH_WORKFLOW):
        workflow = workflow_path.read_text(encoding="utf-8")
        for line in workflow.splitlines():
            if "node " not in line:
                continue
            if not any(token in line for token in gate_invocation_tokens):
                continue
            assert "--profile" in line, f"{workflow_path.name} gates readiness without a profile: {line.strip()}"

    deploy = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert 'check_readiness "current-ai-api-readiness" "http://127.0.0.1:18011/ai-api/readiness" ai' in deploy
    assert 'check_readiness "current-backend-readiness" "http://127.0.0.1:18011/readiness" backend' in deploy
    for label in ("deployed-ai-api-readiness", "rollback-ai-api-readiness"):
        assert f'"http://127.0.0.1:18011/ai-api/readiness" "{label}" ai' in deploy

    health = HEALTH_WORKFLOW.read_text(encoding="utf-8")
    assert 'check_readiness "AI API readiness" "http://127.0.0.1:$COMBINED_PORT/ai-api/readiness" ai' in health
    # The gate ships with the repo, so the health check must run it on the checked-out
    # release. A server still on an older revision has no $APP_DIR/scripts copy, and
    # gating there dies with MODULE_NOT_FOUND before any dependency is checked.
    assert "uses: actions/checkout@" in health
    assert "| node scripts/readiness-semantic-gate.mjs" in health
    assert "$APP_DIR/scripts/readiness-semantic-gate.mjs" not in health


def test_email_worker_start_is_gated_and_points_at_the_ai_venv():
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "print(str(load_settings().email_delivery_worker_enabled).lower())" in workflow
    assert 'if [ "$email_worker_enabled" = "true" ]; then' in workflow
    assert "WARNING: email worker check failed" in workflow
    assert '"$APP_DIR/backend/scripts/manage_email_delivery_worker.sh" start' in workflow
    assert '"$APP_DIR/backend/scripts/manage_email_delivery_worker.sh" check' in workflow
    assert '"$APP_DIR/backend/scripts/manage_email_delivery_worker.sh" stop' in workflow
    assert 'QUANTAGENT_BACKEND_PYTHON="$APP_DIR/ai/.venv/bin/python"' in workflow
    assert "email worker disabled (EMAIL_DELIVERY_WORKER_ENABLED != true)" in workflow

    start_idx = workflow.index('"$APP_DIR/backend/scripts/manage_email_delivery_worker.sh" start')
    ai_ready_idx = workflow.index('"deployed-ai-api-readiness" ai')
    fe_wait_idx = workflow.index('wait_for_url "Frontend gateway"')
    assert ai_ready_idx < start_idx < fe_wait_idx


def test_public_ai_readiness_smoke_uses_the_ai_dependency_set():
    smoke = SMOKE_WORKFLOW.read_text(encoding="utf-8")

    assert "public-ai-readiness" in smoke
    assert "ai_required_checks='durable_job_store,migration_revision,live_provider_configuration,ai_contract_version,rule_draft_signer'" in smoke
    assert '--label public-ai-readiness --checks "$ai_required_checks"' in smoke


def test_failure_rollback_restores_ai_readiness_runtime():
    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    rollback_start = workflow.index("restart_restored_release() {")
    rollback_end = workflow.index(
        "          restore_deploy_snapshot",
        rollback_start,
    )
    rollback = workflow[rollback_start:rollback_end]

    required = (
        'SECRET_DIR="$HOME/.config/quantagent"',
        "export APP_ENV=production",
        "export AI_JOB_STORE=persistent",
        'RULE_DRAFT_SECRET_FILE="$SECRET_DIR/ai-rule-draft-hmac.secret"',
        "export AI_RULE_DRAFT_HMAC_SECRET",
        "export AI_RULE_DRAFT_HMAC_KEY_VERSION=server-v1",
    )

    for token in required:
        assert token in rollback

    assert rollback.index("export AI_JOB_STORE=persistent") < rollback.index(
        'nohup "$APP_DIR/ai/.venv/bin/python"'
    )

    assert rollback.index("export AI_RULE_DRAFT_HMAC_SECRET") < rollback.index(
        'nohup "$APP_DIR/ai/.venv/bin/python"'
    )

    assert "npm ci" not in rollback
    assert "npm run build" not in rollback
    assert "stop_listeners_on_port() {" not in rollback


def test_deploy_exports_a_persistent_backtest_cache_dir_before_starting_the_ai_service():
    """Under APP_ENV=production the AI service refuses to run backtests without it."""

    workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert 'export AI_BACKTEST_CACHE_DIR="$APP_DIR/.run/backtest-cache"' in workflow
    assert workflow.index('export AI_BACKTEST_CACHE_DIR="$APP_DIR/.run/backtest-cache"') < workflow.index(
        'nohup "$APP_DIR/ai/.venv/bin/python" -m uvicorn combined_main:app'
    )
