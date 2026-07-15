import pytest


@pytest.fixture(autouse=True)
def _disable_ai_api_auth_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The AI API requires a logged-in session by default (see ai_graph/auth.py).

    Most existing tests exercise the API surface directly without a real Redis-backed
    session, so default auth off for the whole suite; tests that specifically cover
    auth/ownership behavior opt back in via AUTH_ENABLED or an injected session_resolver.
    """

    monkeypatch.setenv("AUTH_ENABLED", "0")
