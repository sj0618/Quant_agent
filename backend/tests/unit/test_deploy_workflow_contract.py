from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "deploy.yml"


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
    assert "http://127.0.0.1:18001/ai-api/readiness" in workflow
    assert 'payload["status"] == "ready"' in workflow
    assert '"014_create_report_email_tables.sql"' in workflow
    assert '"022_immutable_analysis_results.sql"' in workflow
    assert workflow.index('"014_create_report_email_tables.sql"') < workflow.index(
        '"022_immutable_analysis_results.sql"'
    )
    assert 'payload["migration_revision"] == "022_immutable_analysis_results"' in workflow
    assert 'payload["ai_contract_version"] == "ai-mvp.v1"' in workflow
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
    assert "QUANTAGENT_DEPLOYMENT_REVISION" in workflow
    assert 'payload["deployment_revision"] == os.environ["EXPECTED_DEPLOYMENT_REVISION"]' in workflow
