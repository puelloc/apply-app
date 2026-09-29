#!/usr/bin/env python3
"""P4: browser-use (ChatOllama -> Qwen3.8) fills the mock Greenhouse form, headless vs headed.

Verifies the browser-use <-> Ollama integration (num_ctx/think passthrough via `ollama_options`)
and measures wall time, RAM delta, and throttling per mode. The model has no vision projector, so
`use_vision=False` is mandatory.

Run from inside the spike venv (created by workflow-use.sh):
    source ~/apply-spikes/venv/bin/activate
    OLLAMA_HOST=http://ai.siggy-lab.org:11434 QWEN38_TAG=qwen38-q3-64k:latest python3 p4_browseruse.py
"""
import asyncio
import functools
import http.server
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ai.siggy-lab.org:11434")
MODEL = os.environ.get("QWEN38_TAG", "qwen38-q3-64k:latest")
PORT = int(os.environ.get("MOCK_PORT", "8124"))
DISPLAY = os.environ.get("DISPLAY", ":99")  # headed mode needs an X server (Xvfb/KasmVNC)
FORM_URL = os.environ.get("FORM_URL", f"http://127.0.0.1:{PORT}/mock-greenhouse.html")

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mock-greenhouse.html"

TASK = (
    "Open the mock application form. Fill it with these CANARY test values only: "
    "first name CANARY-First, last name CANARY-Last, email canary@example.invalid, "
    "phone 555-0001, linkedin https://example.invalid/in/canary, website https://example.invalid, "
    "years of experience 9, work authorization select 'I am authorized to work in the US', "
    "cover letter 'CANARY cover letter body'. Then STOP. Do NOT click the Submit button."
)


def _chromium_path() -> str:
    """Resolve Playwright's Chromium path for browser-use (its own binary scan misses it on the Pi)."""
    override = os.environ.get("BROWSER_USE_CHROMIUM_PATH", "").strip()
    if override:
        return override
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        return pw.chromium.executable_path


def _browser_args() -> list:
    raw = os.environ.get("BROWSER_USE_BROWSER_ARGS", "--no-sandbox --disable-gpu --disable-dev-shm-usage").strip()
    return raw.split() if raw else []


# Resolved at module level, before asyncio.run (Playwright's sync API refuses to start in an event loop).
EXECUTABLE_PATH = _chromium_path()
BROWSER_ARGS = _browser_args()


def free_kb() -> int:
    out = subprocess.check_output(["free", "-k"]).decode()
    return int([l for l in out.splitlines() if l.startswith("Mem:")][0].split()[2])


def throttled() -> str:
    try:
        return subprocess.check_output(["vcgencmd", "get_throttled"]).decode().strip()
    except Exception:
        return "n/a"


def serve_form() -> http.server.HTTPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(FIXTURE.parent))
    httpd = http.server.HTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


async def run_once(headless: bool) -> dict:
    from browser_use import Agent, BrowserProfile
    from browser_use.llm import ChatOllama

    llm = ChatOllama(model=MODEL, host=OLLAMA_HOST, ollama_options={"num_ctx": 65536, "think": False})
    profile = BrowserProfile(executable_path=EXECUTABLE_PATH, headless=headless, args=BROWSER_ARGS)
    before = free_kb()
    t0 = time.time()
    status = "ok"
    snippet = ""
    try:
        agent = Agent(task=TASK, llm=llm, browser_profile=profile, use_vision=False, use_thinking=False, max_failures=2)
        result = await agent.run()
        snippet = str(result)[:400]
    except Exception as e:  # noqa: BLE001
        status = f"ERROR: {type(e).__name__}: {e}"
    dt = time.time() - t0
    after = free_kb()
    return {
        "mode": "headless" if headless else "headed",
        "status": status,
        "wall_s": round(dt, 1),
        "ram_delta_kb": after - before,
        "throttled": throttled(),
        "snippet": snippet,
    }


async def main() -> None:
    print(f"P4 browser-use fill — model={MODEL} host={OLLAMA_HOST} form={FORM_URL}")
    print(f"fixture={FIXTURE} (exists={FIXTURE.exists()})")
    if not FIXTURE.exists():
        print("FIXTURE MISSING"); sys.exit(2)
    serve_form()

    results = []
    # headless first (known to work), then headed (needs DISPLAY)
    for headless in (True, False):
        print(f"\n=== running { 'headless' if headless else 'headed' } (DISPLAY={DISPLAY}) ===")
        r = await run_once(headless)
        results.append(r)
        print(f"  {r['mode']}: status={r['status']} wall={r['wall_s']}s ram_delta={r['ram_delta_kb']}KB throttled={r['throttled']}")
        if r["snippet"]:
            print("  result:", r["snippet"].replace("\n", " ")[:250])

    print("\n=== P4 SUMMARY ===")
    for r in results:
        print(f"  {r['mode']}: {r['status']} | {r['wall_s']}s | {r['ram_delta_kb']}KB | {r['throttled']}")
    print("CHECK: headed may fail without a running X server (expected on a headless Pi). Record headless vs headed.")


if __name__ == "__main__":
    asyncio.run(main())
