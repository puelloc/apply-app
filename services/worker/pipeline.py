"""Run one job: acquire a lease, fill the form via browser-use, record reasoning, release.

The browser-use integration (ChatOllama + Agent + BrowserProfile) follows the verified spike pattern
(scripts/spikes/p4_browseruse.py). The submit guard, CDP-to-browser-service connection, and the exact
fill state machine are wired and verified on the Pi in step 6c; this is the skeleton + contract.
"""

from __future__ import annotations

import asyncio
import os
import uuid

from browser_use import Agent, BrowserProfile
from browser_use.llm import ChatOllama

from reasoning import agent_step_to_payload, from_browser_use

MODEL = os.environ.get("QWEN38_TAG", "qwen38-q3-64k:latest")
OLLAMA_HOST = os.environ.get("OLLAMA_BASE_URL", "https://ai.siggy-lab.org")


def _chromium_path() -> str:
    # Playwright's sync API refuses to run inside an event loop, so resolve it lazily per run.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        return pw.chromium.executable_path


def _browser_args() -> list[str]:
    raw = os.environ.get("BROWSER_USE_BROWSER_ARGS", "--no-sandbox --disable-gpu --disable-dev-shm-usage")
    return raw.split()


def make_llm() -> ChatOllama:
    return ChatOllama(model=MODEL, host=OLLAMA_HOST, ollama_options={"num_ctx": 65536, "think": False})


def build_task(job: dict) -> str:
    # TODO(step 6c): build the fill task from the job's profile/answers + the adapter's fields.
    url = job.get("application_url") or job.get("listing_url")
    return (
        f"Open the application form at {url}. Fill every field with the profile values, then STOP. "
        "Do NOT click any Submit or Next button."
    )


async def run_job(api, job: dict, llm: ChatOllama) -> None:
    run_id = uuid.uuid4().hex[:16]
    adapter = job.get("ats") or "unknown"
    agent = Agent(
        task=build_task(job),
        llm=llm,
        browser_profile=BrowserProfile(executable_path=_chromium_path(), headless=True, args=_browser_args()),
        use_vision=False,
        use_thinking=False,
        max_failures=2,
    )
    result = await agent.run()

    # Capture every step's reasoning (eval/memory/next_goal/action) into step events.
    history = getattr(result, "history", None) or []
    for step in history:
        api.add_step_event(job["id"], agent_step_to_payload(adapter, run_id, from_browser_use(step)))

    # TODO(step 6c): transition the job to ready_for_review once the state machine supports it.


async def run_once(api, llm: ChatOllama) -> bool:
    lease = api.acquire()
    if lease is None:
        return False
    job = lease["job"]
    try:
        await run_job(api, job, llm)
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
