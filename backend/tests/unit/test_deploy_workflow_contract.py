from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "deploy.yml"
SMOKE_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "production-backtest-smoke.yml"


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
    assert "node scripts/evaluate-release-trust.mjs" in workflow
    assert "http://127.0.0.1:18001/readiness" in workflow
    assert "http://127.0.0.1:18001/ai-api/readiness" in workflow
    assert 'payload["status"] == "ready"' in workflow
    assert 'assert all(check["ready"] for check in payload["checks"])' in workflow
    assert 'payload["migration_revision"] == "021_ai_analysis_jobs"' in workflow
    assert 'payload["ai_contract_version"] == "ai-mvp.v1"' in workflow
    assert "AUTH_TRUSTED_PROXY_HEADERS=true" in workflow
    assert "AUTH_TRUSTED_PROXY_HOSTS=127.0.0.1,::1" in workflow
    auth_unset_block = workflow.split("for auth_var in", maxsplit=1)[1].split("do", maxsplit=1)[0]
    assert "AUTH_TRUSTED_PROXY_HEADERS" in auth_unset_block
    assert "AUTH_TRUSTED_PROXY_HOSTS" in auth_unset_block
    assert 'settings.auth_trusted_proxy_headers' in workflow
    assert 'set(settings.trusted_proxy_hosts) == {"127.0.0.1", "::1"}' in workflow
    assert "xfwd: true" in (REPOSITORY_ROOT / "fe" / "vite.config.ts").read_text(encoding="utf-8")
    assert "AI_RULE_DRAFT_HMAC_SECRET" in workflow
    assert "ai-rule-draft-hmac.secret" in workflow


def test_public_smoke_requires_readiness_not_health_only():
    workflow = SMOKE_WORKFLOW.read_text(encoding="utf-8")

    assert "https://qt-agent.kro.kr/ai-api/readiness" in workflow
    assert "https://qt-agent.kro.kr/ai-api/health" not in workflow
    assert 'payload["status"] == "ready"' in workflow
    assert 'assert all(check["ready"] for check in payload["checks"])' in workflow
