#!/usr/bin/env python3
"""Step 6c (standalone): browser-use fills the mock form WITH the submit guard + captures reasoning.

Verifies the three step-6 integrations before wiring the full compose pipeline:
  1. the submit guard is injected and active (window.__submitGuard),
  2. the agent fills the form and STOPS without submitting,
  3. each step's reasoning (eval/next_goal/action) is captured.

Run via scripts/step6c-fill.sh (Docker, worker image).
"""
import asyncio
import functools
import http.server
import os
import threading
from pathlib import Path

os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")

OLLAMA_HOST = os.environ.get("OLLAMA_BASE_URL", "https://ai.siggy-lab.org")
MODEL = os.environ.get("QWEN38_TAG", "qwen38-q3-64k:latest")
PORT = int(os.environ.get("MOCK_PORT", "8138"))
FORM_URL = os.environ.get("FORM_URL", f"http://127.0.0.1:{PORT}/greenhouse.html")
FIXTURES = Path(os.environ.get("FIXTURES", "/spike/services/mock-ats/fixtures"))
GUARD = Path(os.environ.get("GUARD_JS", "/app/guard.js")).read_text()

TASK = (
    f"Open {FORM_URL}. Fill first name CANARY-First, last name CANARY-Last, "
    "email canary@example.invalid, phone 555-0001. Then STOP. Do NOT click the Submit button."
)

STEPS = []


def _serve() -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(FIXTURES))
    httpd = http.server.HTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()


def _chromium_path() -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        return pw.chromium.executable_path


# Resolved at module level, before asyncio.run (Playwright's sync API can't run inside a loop).
EXECUTABLE_PATH = _chromium_path()


async def main() -> None:
    from browser_use import Agent, BrowserProfile, BrowserSession
    from browser_use.llm import ChatOllama

    _serve()
    print(f"step6c fill — model={MODEL} host={OLLAMA_HOST} form={FORM_URL}")

    llm = ChatOllama(model=MODEL, host=OLLAMA_HOST, ollama_options={"num_ctx": 65536, "think": False})
    session = BrowserSession(
        browser_profile=BrowserProfile(
            executable_path=EXECUTABLE_PATH, headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        )
    )
    await session.start()
    try:
        await session._cdp_add_init_script(GUARD)
        print("guard injected")

        def on_step(browser_state, model_output, step_number) -> None:
            action = model_output.action[0] if model_output.action else None
            name = next(iter(action.model_dump(exclude_unset=True).keys()), "no-action") if action else "no-action"
            rec = {
                "step": step_number,
                "action": name,
                "eval": model_output.evaluation_previous_goal,
                "next_goal": model_output.next_goal,
                "url": getattr(browser_state, "url", None),
            }
            STEPS.append(rec)
            goal = (model_output.next_goal or "")[:70]
            print(f"  [step {step_number}] action={name} next_goal={goal!r}")

        agent = Agent(
            task=TASK, llm=llm, browser_session=session,
            use_vision=False, use_thinking=False, max_failures=2,
            register_new_step_callback=on_step,
        )
        await agent.run()
    finally:
        await session.stop()

    print("\n=== STEP 6c SUMMARY ===")
    print(f"steps captured: {len(STEPS)}")
    for s in STEPS:
        print(f"  {s['step']}: {s['action']} | next_goal={s['next_goal'][:60] if s['next_goal'] else None}")
    print("CHECK: agent should have filled the fields and stopped WITHOUT submitting; guard was injected.")


if __name__ == "__main__":
    asyncio.run(main())
