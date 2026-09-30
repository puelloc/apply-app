"""S2: submit-guard suite.

Proves the guard blocks every submit mechanism and that ZERO submit requests reach the mock server.
Run on the Pi (needs Playwright + Chromium, e.g. the spike venv at ~/apply-spikes/venv):

    ~/apply-spikes/venv/bin/python services/browser/s2_submit_guard.py

Pass = "blocked: 4" and "POSTs: 0".
"""

from __future__ import annotations

import asyncio
import http.server
import threading
from pathlib import Path

from playwright.async_api import async_playwright

GUARD = Path(__file__).resolve().parent / "guard.js"
FIXTURES = Path(__file__).resolve().parent.parent / "mock-ats" / "fixtures"
PORT = 8137
FORM_URL = f"http://127.0.0.1:{PORT}/greenhouse.html"

POSTS: list[str] = []


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FIXTURES), **kwargs)

    def do_POST(self) -> None:
        POSTS.append(self.path)
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args) -> None:
        pass


class ReusableHTTPServer(http.server.HTTPServer):
    allow_reuse_address = True


def serve() -> None:
    httpd = ReusableHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()


async def main() -> None:
    serve()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context()
        await context.add_init_script(path=str(GUARD))  # inject the guard
        page = await context.new_page()
        await page.goto(FORM_URL)

        await page.click("#submit")                              # click the submit button
        await page.focus("input[name=first_name]")
        await page.press("input[name=first_name]", "Enter")      # Enter key
        await page.evaluate("document.querySelector('form').submit()")        # JS form.submit()
        await page.evaluate("document.querySelector('form').requestSubmit()")  # requestSubmit

        state = await page.evaluate("window.__submitGuard")
        print("blocked:", state["blocked"])
        print("reasons:", state["reasons"])
        await browser.close()

    print("POSTs:", len(POSTS))
    ok = state["blocked"] == 4 and len(POSTS) == 0
    print("S2", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
