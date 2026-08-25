import pytest


@pytest.fixture(autouse=True)
def _disable_ai_api_auth_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The AI API requires a logged-in session by default (see ai_graph/auth.py).

    Most existing tests exercise the API surface directly without a real Redis-backed
    session, so default auth off for the whole suite; tests that specifically cover
    auth/ownership behavior opt back in via AUTH_ENABLED or an injected session_resolver.
    """

    monkeypatch.setenv("AUTH_ENABLED", "0")


@pytest.fixture
def enforced_objective_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put the backtest acceptance floor back in the path for one test.

    The floor ships report-only while the product is in its test phase, so a test that
    asserts the floor *blocks* has to say which mode it means. See
    `ai_graph/validation_gates.py`.
    """

    from ai_graph.validation_gates import AI_VALIDATION_GATES_ENV, ENFORCED

    monkeypatch.setenv(AI_VALIDATION_GATES_ENV, ENFORCED)
