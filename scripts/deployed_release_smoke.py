"""Login-free smoke test of a deployed QuantAgent release.

Runs ON the server (over SSH) with the release's own virtualenv and the release
directory as cwd, so the backend `.env` is what gets loaded. Google login is never
involved: the backend's own session store mints a short-lived ``qa_session`` for a
synthetic QA user in the shared Redis, the AI API is called through the frontend
gateway on loopback with that cookie - the same path a browser takes, minus TLS and
Google - and the session is revoked at the end.

Exit code 0 means: auth is enforced (no cookie -> 401), the cookie is accepted, one
analysis job was admitted, it reached a terminal result within the time budget, and
that result carries one of the expected statuses.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

# Names a market (코스피), not an index: "KOSPI200 종목" is a point-in-time membership
# filter that seals only when feature.krx_index_membership_history holds KOSPI200 rows;
# on a warehouse without them it is refused with need_clarification naming that gap.
DEFAULT_QUERY = "RSI(14)가 30 이하로 떨어진 코스피 종목을 사고, 70 이상이면 파는 전략"
DEFAULT_EXPECTED_STATUSES = ("ready",)
# The combined service runs as one process; while a backtest is computing, the gateway
# can answer a poll with 502/504 for a while. That is a poll to retry, not a verdict.
POLL_FAILURE_GRACE_SECONDS = 300.0


def is_terminal(job: Any) -> bool:
    """A job is finished when the API has attached a result envelope."""

    return isinstance(job, dict) and job.get("result") is not None


def evaluate_job(job: Any, expected_statuses: tuple[str, ...]) -> tuple[bool, str]:
    """Judge a terminal job: (passed, one-line reason)."""

    if not is_terminal(job):
        return False, "job has no result yet"
    result = job.get("result") or {}
    status = str(result.get("status") or "")
    payload = result.get("user_payload") or {}
    headline = str(payload.get("headline") or "").strip()
    if status in expected_statuses:
        return True, f"status={status} headline={headline!r}"
    message = str(payload.get("message") or "").strip()
    failure = result.get("failure_cause") or {}
    detail = failure.get("failure_stage") or failure.get("category") or ""
    return False, f"status={status} headline={headline!r} message={message!r} failure={detail!r}"


def clarification_details(job: Any) -> str:
    """What the release asked back or refused: the diagnosis for a non-ready result."""

    result = (job.get("result") or {}) if isinstance(job, dict) else {}
    payload = result.get("user_payload") or {}
    ambiguity = result.get("ambiguity") or {}
    lines = []
    if payload.get("question"):
        lines.append(f"question={payload['question']!r}")
    for action in payload.get("next_actions") or []:
        lines.append(f"next_action={action!r}")
    labels = [o.get("label") for o in (payload.get("options") or []) if isinstance(o, dict)]
    if labels:
        lines.append(f"options={labels!r}")
    if ambiguity.get("reason"):
        lines.append(f"ambiguity={ambiguity.get('category')!r} reason={ambiguity['reason']!r}")
    return "\n".join(f"[smoke]   {line}" for line in lines)


def poll_outcome(status: int, job: Any, *, failing_since: float | None, now: float) -> tuple[str, float | None]:
    """Classify one poll: ("ok", None), ("retry", first_failure_time) or ("fail", first_failure_time).

    A non-200 answer is tolerated until it has persisted for POLL_FAILURE_GRACE_SECONDS.
    """

    if status == 200 and isinstance(job, dict):
        return "ok", None
    started = now if failing_since is None else failing_since
    if now - started > POLL_FAILURE_GRACE_SECONDS:
        return "fail", started
    return "retry", started


def stage_summary(job: Any) -> str:
    stages = job.get("stages") if isinstance(job, dict) else None
    if not isinstance(stages, list):
        return ""
    return " ".join(f"{s.get('stage')}={s.get('status')}" for s in stages if isinstance(s, dict))


def http_json(
    method: str,
    url: str,
    *,
    cookie: tuple[str, str] | None = None,
    body: Any | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    data = None
    request = urllib.request.Request(url, method=method)
    request.add_header("Accept", "application/json")
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request.add_header("Content-Type", "application/json")
    if cookie is not None:
        request.add_header("Cookie", f"{cookie[0]}={cookie[1]}")
    try:
        with urllib.request.urlopen(request, data=data, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else None
        except ValueError:
            return exc.code, raw.decode("utf-8", errors="replace")


async def _session_store():
    from app.core.config import load_settings
    from app.services.session_store import AuthSessionStore
    from redis import asyncio as redis_asyncio

    settings = load_settings()
    redis_url = getattr(settings, "redis_url_value", None)
    if not redis_url and settings.redis_url is not None:
        redis_url = settings.redis_url.get_secret_value()
    if not redis_url:
        raise SystemExit("REDIS_URL is not configured in the release environment")
    client = redis_asyncio.from_url(redis_url, decode_responses=True)
    return AuthSessionStore(client, settings), client, settings.auth_session_cookie_name


async def _close(client: Any) -> None:
    close = getattr(client, "aclose", None) or getattr(client, "close", None)
    if close is not None:
        result = close()
        if asyncio.iscoroutine(result):
            await result


# Each asyncio.run() is its own event loop and a redis-py connection is bound to the
# loop that opened it, so mint and revoke each open and close their own client; the
# session itself lives in Redis, not in the client.
async def mint_session(user_id: str) -> tuple[str, str]:
    store, client, cookie_name = await _session_store()
    try:
        session_id, _csrf = await store.create_session(user_id=user_id)
    finally:
        await _close(client)
    return cookie_name, session_id


async def revoke_session(session_id: str) -> None:
    store, client, _cookie_name = await _session_store()
    try:
        await store.revoke_session(session_id)
    finally:
        await _close(client)


def run(args: argparse.Namespace) -> int:
    base = args.base_url.rstrip("/")
    jobs_url = f"{base}/ai-api/analysis-jobs"
    user_id = f"qa-smoke:{args.run_label}"
    expected = tuple(s.strip() for s in args.expect.split(",") if s.strip())

    cookie_name, session_id = asyncio.run(mint_session(user_id))
    print(f"[smoke] minted session for {user_id} (cookie {cookie_name})")
    job_id: str | None = None
    try:
        status, job = http_json("POST", jobs_url, cookie=(cookie_name, session_id), body={"query": args.query})
        if status not in (200, 201, 202) or not isinstance(job, dict) or not job.get("job_id"):
            print(f"[smoke] job admission failed: HTTP {status} {json.dumps(job, ensure_ascii=False)[:800]}")
            return 2
        job_id = str(job["job_id"])
        print(f"[smoke] admitted job {job_id} trace={job.get('trace_id')}")

        # Auth is enforced: the same job is invisible without the cookie.
        status, _ = http_json("GET", f"{jobs_url}/{job_id}")
        if status != 401:
            print(f"[smoke] expected 401 without a session cookie, got HTTP {status}")
            return 3

        deadline = time.monotonic() + args.timeout_seconds
        last_stages = ""
        failing_since: float | None = None
        while True:
            status, job = http_json("GET", f"{jobs_url}/{job_id}", cookie=(cookie_name, session_id))
            outcome, failing_since = poll_outcome(
                status, job, failing_since=failing_since, now=time.monotonic()
            )
            if outcome == "fail":
                print(f"[smoke] polling kept failing for {POLL_FAILURE_GRACE_SECONDS:.0f}s: HTTP {status} {json.dumps(job, ensure_ascii=False)[:400]}")
                return 4
            if outcome == "retry":
                print(f"[smoke] {time.strftime('%H:%M:%S')} poll returned HTTP {status}; retrying (service busy)")
                if time.monotonic() > deadline:
                    print(f"[smoke] job {job_id} did not finish within {args.timeout_seconds}s")
                    return 5
                time.sleep(args.poll_seconds)
                continue
            stages = stage_summary(job)
            if stages != last_stages:
                print(f"[smoke] {time.strftime('%H:%M:%S')} {stages}")
                last_stages = stages
            if is_terminal(job):
                break
            if time.monotonic() > deadline:
                print(f"[smoke] job {job_id} did not finish within {args.timeout_seconds}s")
                return 5
            time.sleep(args.poll_seconds)

        passed, reason = evaluate_job(job, expected)
        print(f"[smoke] {'PASS' if passed else 'FAIL'} job={job_id} {reason}")
        if not passed:
            details = clarification_details(job)
            if details:
                print(details)
        print(json.dumps({"job_id": job_id, "passed": passed, "reason": reason, "stages": stage_summary(job)}, ensure_ascii=False))
        return 0 if passed else 6
    finally:
        try:
            asyncio.run(revoke_session(session_id))
            print("[smoke] session revoked")
        except Exception as exc:  # noqa: BLE001 - the verdict above must not be masked
            print(f"[smoke] session revoke failed ({type(exc).__name__}: {exc}); it expires by TTL")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:18010", help="frontend gateway on loopback")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--expect", default=",".join(DEFAULT_EXPECTED_STATUSES), help="comma-separated accepted result statuses")
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--run-label", default=str(int(time.time())), help="suffix of the synthetic QA user id")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
