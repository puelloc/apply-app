"""Run one job: acquire -> fill via browser-use (with submit guard) -> record reasoning -> release.

Uses browser-use 0.13.10's verified API (see scripts/spikes/p4_browseruse.py). The submit guard is
injected via `_cdp_add_init_script` (browser-use injects per-document scripts through CDP for both
local and remote sessions); each step's reasoning is captured via `register_new_step_callback`.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

from browser_use import Agent, BrowserProfile, BrowserSession
from browser_use.llm import ChatOllama

from adapters import requires_account
from reasoning import agent_step_to_payload, from_browser_use_step

MODEL = os.environ.get("QWEN38_TAG", "qwen38-q3-64k:latest")
OLLAMA_HOST = os.environ.get("OLLAMA_BASE_URL", "https://ai.siggy-lab.org")
GUARD = Path("guard.js").read_text()


def _chromium_path() -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        return pw.chromium.executable_path


# Resolved at import time, before the event loop (Playwright's sync API can't run inside asyncio).
EXECUTABLE_PATH = _chromium_path()


def _browser_args() -> list[str]:
    raw = os.environ.get("BROWSER_USE_BROWSER_ARGS", "--no-sandbox --disable-gpu --disable-dev-shm-usage")
    return raw.split()


def make_llm() -> ChatOllama:
    return ChatOllama(model=MODEL, host=OLLAMA_HOST, ollama_options={"num_ctx": 65536, "think": False})


def make_session() -> BrowserSession:
    cdp_url = os.environ.get("BROWSER_CDP_URL")
    if cdp_url:
        return BrowserSession(cdp_url=cdp_url)
    return BrowserSession(
        browser_profile=BrowserProfile(executable_path=EXECUTABLE_PATH, headless=True, args=_browser_args())
    )


async def inject_guard(session: BrowserSession) -> None:
    await session._cdp_add_init_script(GUARD)


def build_task(job: dict) -> str:
    # TODO(step 7): build the fill task from the job's profile/answers + the adapter's fields.
    # Step 6d uses fixed CANARY values so the end-to-end run is self-contained (no profile yet).
    url = job.get("application_url") or job.get("listing_url")
    return (
        f"Open the application form at {url}. Fill first name CANARY-First, last name CANARY-Last, "
        "email canary@example.invalid, phone 555-0001. Then STOP. Do NOT click the Submit button."
    )


async def _fill_and_park(api, job: dict, llm: ChatOllama) -> None:
    run_id = uuid.uuid4().hex[:16]
    adapter = job.get("ats") or "unknown"
    session = make_session()
    await session.start()
    try:
        await inject_guard(session)

        def on_step(browser_state, model_output, step_number) -> None:
            payload = agent_step_to_payload(
                adapter, run_id, from_browser_use_step(browser_state, model_output, step_number)
            )
            api.add_step_event(job["id"], payload)

        agent = Agent(
            task=build_task(job),
            llm=llm,
            browser_session=session,
            use_vision=False,
            use_thinking=False,
            max_failures=2,
            register_new_step_callback=on_step,
        )
        result = await agent.run()
        # Park only on a true success; otherwise mark failed (a stopped-with-error agent is not reviewable).
        api.set_state(job["id"], "ready_for_review" if result.is_successful() is True else "failed")
    finally:
        await session.stop()


async def run_job(api, job: dict, llm: ChatOllama) -> None:
    """Dispatch to the right application path (quick-apply vs account-required)."""
    if job.get("requires_account") or requires_account(job.get("ats")):
        # Account path (step 7c): signup/login -> verify -> confirm -> apply.
        api.set_state(job["id"], "awaiting_email")
        return
    await _fill_and_park(api, job, llm)


async def run_once(api, llm: ChatOllama) -> bool:
    lease = api.acquire()
    if lease is None:
        return False
    job = lease["job"]
    try:
        await run_job(api, job, llm)
    except Exception:
        # A failed run must not leave the job stuck in `running`.
        try:
            api.set_state(job["id"], "failed")
        except Exception:
            pass
        raise
    finally:
        api.release(job["id"], lease["lease_token"])
    return True


async def main() -> None:
    from pathlib import Path

    from api_client import ApiClient

    token = os.environ.get("WORKER_API_TOKEN") or Path("/run/secrets/worker_api_token").read_text().strip()
    api = ApiClient(os.environ["API_URL"], token)
    llm = make_llm()
    while True:
        try:
            if not await run_once(api, llm):
                await asyncio.sleep(5)
        except Exception as exc:  # noqa: BLE001
            print(f"job error: {type(exc).__name__}: {exc}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
