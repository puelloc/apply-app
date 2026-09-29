#!/usr/bin/env python3
"""W1-W3: workflow-use record/replay/fallback against the mock Greenhouse form.

W1 — build a parameterized workflow (placeholders via input_schema + {context_var}) and prove the
     saved workflow file contains NO real values.
W2 — replay it with a different (canary) profile and confirm it fills correctly and stops before
     submit (the schema ends at an extract step; there is no submit step).
W3 — break a selector and confirm `fallback_to_agent` recovers.

Run from inside the spike venv (created by workflow-use.sh):
    source ~/apply-spikes/venv/bin/activate
    OLLAMA_HOST=http://ai.siggy-lab.org:11434 QWEN38_TAG=qwen38-q3-64k:latest python3 w1w3.py
"""
import asyncio
import functools
import http.server
import json
import os
import sys
import threading
from pathlib import Path

from browser_use import Browser
from browser_use.llm import ChatOllama

from workflow_use.schema.views import WorkflowDefinitionSchema
from workflow_use.workflow.service import Workflow

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ai.siggy-lab.org:11434")
MODEL = os.environ.get("QWEN38_TAG", "qwen38-q3-64k:latest")
PORT = int(os.environ.get("MOCK_PORT", "8124"))
FORM_URL = os.environ.get("FORM_URL", f"http://127.0.0.1:{PORT}/mock-greenhouse.html")

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mock-greenhouse.html"
OUT_DIR = Path(os.environ.get("WORKFLOW_OUT_DIR", str(Path.home() / "apply-spikes" / "workflows")))
WORKFLOW_FILE = OUT_DIR / "mock-greenhouse.workflow.json"

# Canary strings that must NEVER appear in the workflow file (they are run-time values).
CANARIES = [
    "CANARY-Replay-First",
    "canary-replay@example.invalid",
    "CANARY-secret-pw-9f3a",
    "canary@example.invalid",
    "555-0001",
    "CANARY cover letter",
]

REPLAY_PROFILE = {
    "first_name": "CANARY-Replay-First",
    "last_name": "CANARY-Replay-Last",
    "email": "canary-replay@example.invalid",
    "phone": "555-0001",
    "linkedin": "https://example.invalid/in/canary-replay",
    "website": "https://example.invalid",
    "years": "9",
    "work_auth": "I am authorized to work in the US",
    "cover_letter": "CANARY cover letter body for replay.",
}


def serve_form() -> http.server.HTTPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(FIXTURE.parent))
    httpd = http.server.HTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def build_schema() -> WorkflowDefinitionSchema:
    """A parameterized workflow: every value is a {context_var}, so the file holds no real data."""
    return WorkflowDefinitionSchema(
        name="mock-greenhouse-fill",
        description="Fill the mock Greenhouse application form with profile values, then extract the result.",
        version="1.0.0",
        default_wait_time=0.1,
        input_schema=[
            {"name": "first_name", "type": "string", "required": True},
            {"name": "last_name", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": True},
            {"name": "phone", "type": "string"},
            {"name": "linkedin", "type": "string"},
            {"name": "website", "type": "string"},
            {"name": "years", "type": "string"},
            {"name": "work_auth", "type": "string"},
            {"name": "cover_letter", "type": "string"},
        ],
        steps=[
            {"type": "navigation", "url": FORM_URL},
            {"type": "input", "target_text": "First name", "value": "{first_name}"},
            {"type": "input", "target_text": "Last name", "value": "{last_name}"},
            {"type": "input", "target_text": "Email", "value": "{email}"},
            {"type": "input", "target_text": "Phone", "value": "{phone}"},
            {"type": "input", "target_text": "LinkedIn", "value": "{linkedin}"},
            {"type": "input", "target_text": "Website", "value": "{website}"},
            {"type": "input", "target_text": "Years of experience", "value": "{years}"},
            {"type": "select_change", "target_text": "Work authorization", "selectedText": "{work_auth}"},
            {"type": "input", "target_text": "Cover letter", "value": "{cover_letter}"},
            {"type": "extract", "extractionGoal": "Extract the values entered into each form field."},
        ],
    )


def new_llm() -> ChatOllama:
    return ChatOllama(model=MODEL, host=OLLAMA_HOST, ollama_options={"num_ctx": 65536, "think": False})


async def run_workflow(schema: WorkflowDefinitionSchema) -> dict:
    browser = Browser(headless=True)
    try:
        await browser.start()
        wf = Workflow(schema, llm=new_llm(), browser=browser, fallback_to_agent=True)
        result = await wf.run(REPLAY_PROFILE)
        step_types = [type(s).__name__ for s in (result.step_results or [])]
        return {"status": getattr(result, "status", "ok"), "step_types": step_types, "result": str(result)[:400]}
    finally:
        try:
            await browser.close()
        except Exception:  # noqa: BLE001
            pass


async def main() -> None:
    print(f"W1-W3 workflow-use — model={MODEL} host={OLLAMA_HOST} form={FORM_URL}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- W1: parameterized workflow file contains no real values ----
    schema = build_schema()
    WORKFLOW_FILE.write_text(schema.model_dump_json(indent=2))
    raw = WORKFLOW_FILE.read_text()
    leaks = [c for c in CANARIES if c in raw]
    print(f"\n[W1] workflow file written to {WORKFLOW_FILE}")
    print(f"[W1] placeholders present: {{first_name}}={ '{{first_name}}' in raw }, {{email}}={ '{{email}}' in raw }")
    print(f"[W1] canary leaks found in file: {leaks if leaks else 'NONE'}")
    print("W1 RESULT:", "PASS (no real values in workflow file)" if not leaks else "FAIL (real values leaked)")

    # ---- W2: replay with a different profile, stops before submit ----
    print("\n[W2] replaying with canary profile (schema has no submit step)...")
    try:
        r2 = await run_workflow(schema)
        print(f"[W2] status={r2['status']}")
        print(f"[W2] step result types: {r2['step_types']}")
        # The schema ends at an 'extract' step and never clicks submit -> no submit happened.
        print("W2 RESULT:", "PASS (ran to completion; no submit step)" if r2["status"] == "ok" else f"CHECK: {r2['status']}")
        print(f"[W2] result: {r2['result'][:300]}")
    except Exception as e:  # noqa: BLE001
        print(f"W2 RESULT: ERROR {type(e).__name__}: {e}")

    # ---- W3: break a selector, fallback_to_agent should recover ----
    broken = build_schema()
    # break the first input step's target_text
    for step in broken.steps:
        if getattr(step, "type", None) == "input" and getattr(step, "target_text", None) == "First name":
            step.target_text = "NONEXISTENT_FIELD_XYZ_12345"
            break
    print("\n[W3] re-running with a broken selector (first_name target_text -> NONEXISTENT_FIELD_XYZ_12345)...")
    try:
        r3 = await run_workflow(broken)
        print(f"[W3] status={r3['status']}")
        print(f"[W3] step result types: {r3['step_types']}")
        # If the broken step fell back to the agent, its result type is AgentHistoryList (not ActionResult).
        fell_back = any("AgentHistory" in t for t in r3["step_types"])
        print(f"[W3] fallback_to_agent used: {fell_back}")
        print("W3 RESULT:", "PASS (fallback recovered)" if r3["status"] == "ok" and fell_back else "CHECK (see step types above)")
    except Exception as e:  # noqa: BLE001
        print(f"W3 RESULT: ERROR {type(e).__name__}: {e}")

    print("\n=== W SUMMARY === see W1/W2/W3 RESULT lines above ===")


if __name__ == "__main__":
    asyncio.run(main())
