"""Capture agent/browser-use reasoning into the step-event payload the API stores.

Each browser-use step's thinking — evaluation of the previous goal, memory, and next goal — plus the
action it took, becomes one step-event. Those rows are what the diagnostics API (timelines,
explain_failure, filtered logs) reads back. This module is pure (no browser-use import): it takes a
canonical step dict, which `from_browser_use` produces from a browser-use history step.
"""

from __future__ import annotations

from typing import Any


def agent_step_to_payload(adapter: str, run_id: str, step: dict[str, Any]) -> dict[str, Any]:
    """Map a canonical agent step to the step-event payload (the API's StepEventCreate contract)."""
    return {
        "run_id": run_id,
        "step": f"agent-{step['step']}",
        "adapter": adapter,
        "action": step.get("action") or "no-action",
        "postcondition": "fail" if step.get("error") else "pass",
        "duration_ms": step.get("duration_ms"),
        "error_code": step.get("error_code"),
        "model_meta": {
            "eval": step.get("eval"),
            "memory": step.get("memory"),
            "next_goal": step.get("next_goal"),
            "url": step.get("url"),
        },
    }


def from_browser_use_step(browser_state: Any, model_output: Any, step_number: int) -> dict[str, Any]:
    """Normalize browser-use's per-step callback args to the canonical step dict.

    browser-use 0.13.10 calls `register_new_step_callback(browser_state_summary, model_output,
    step_number)` after each step. The action name is the first key of `model_output.action[0]` (a
    dynamic ActionModel, e.g. `{'input_text': {...}}`). `run_id`/`adapter` are added by the caller.
    """
    actions = getattr(model_output, "action", None) or []
    names = [next(iter(a.model_dump(exclude_unset=True).keys()), "?") for a in actions]
    action_name = ",".join(names) if names else "no-action"
    return {
        "step": step_number,
        "action": action_name,
        "eval": getattr(model_output, "evaluation_previous_goal", None),
        "memory": getattr(model_output, "memory", None),
        "next_goal": getattr(model_output, "next_goal", None),
        "url": getattr(browser_state, "url", None),
    }
