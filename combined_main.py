from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
import sys

from fastapi import FastAPI


def _ensure_source_path(path: Path) -> None:
    resolved = str(path)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


REPO_ROOT = Path(__file__).resolve().parent
_ensure_source_path(REPO_ROOT / "backend")
_ensure_source_path(REPO_ROOT / "ai")

import app.main as general_main  # noqa: E402
import ai_graph.api as ai_main  # noqa: E402


general_app = general_main.app
ai_app = ai_main.app


@asynccontextmanager
async def lifespan(app: FastAPI):
    stack = AsyncExitStack()
    try:
        await stack.enter_async_context(general_app.router.lifespan_context(general_app))
        await stack.enter_async_context(ai_app.router.lifespan_context(ai_app))
    except Exception:
        await stack.aclose()
        raise
    try:
        yield
    finally:
        await stack.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="QuantAgent Combined Backend",
        version="0.1.0",
        description="Combined local integration wrapper for the General Backend and AI Backend.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.get("/combined-health")
    def combined_health() -> dict[str, str]:
        return {"status": "ok", "service": "quantagent-combined-backend"}

    app.mount("/ai-api", ai_app)
    app.mount("/", general_app)
    return app


app = create_app()
