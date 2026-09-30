"""Typed error taxonomy.

One stable code per failure mode, each carrying a message, a cause, and a fix. The runbook (master
skill) is generated from this table, so each code's meaning lives in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorSpec:
    code: str
    message: str
    cause: str
    fix: str


ERRORS: dict[str, ErrorSpec] = {spec.code: spec for spec in [
    ErrorSpec("ollama_unreachable", "Ollama is unreachable",
              "the model host is offline or the proxy/DNS path is broken",
              "verify https://ai.siggy-lab.org is reachable and the model host is up"),
    ErrorSpec("vault_sealed", "Vault is sealed",
              "the worker restarted and the key is only held in memory",
              "unseal the vault with the escrowed passphrase"),
    ErrorSpec("selector_missing", "Element selector not found",
              "the page changed or the workflow is stale",
              "re-stage via the fallback agent and update the workflow"),
    ErrorSpec("postcondition_failed", "Step postcondition not met",
              "a fill/action did not produce the expected result",
              "check the step diff and re-run with the fallback agent"),
    ErrorSpec("replay_diverged", "Workflow replay diverged",
              "the recorded workflow no longer matches the page",
              "fall back to the agent and re-record the workflow"),
    ErrorSpec("email_timeout", "Verification email did not arrive",
              "IMAP delivery is slow or the alias is wrong",
              "check IMAP and the alias mapping"),
    ErrorSpec("blocker_captcha", "CAPTCHA or bot check",
              "the site is challenging the browser",
              "route to needs_human for manual solve"),
    ErrorSpec("submit_guard_blocked", "Submit was blocked",
              "the page-level guard intercepted a submit attempt (expected)",
              "no action — this is the safety guard working"),
    ErrorSpec("budget_exceeded", "Per-job budget exceeded",
              "the job used more steps/time/tokens than allowed",
              "review the job timeline; reduce scope or raise the budget"),
    ErrorSpec("domain_blocked", "Domain blocked by egress policy",
              "the page tried to reach a non-allowlisted or private host",
              "check the domain allowlist and the egress proxy logs"),
    ErrorSpec("account_exists", "Account already exists",
              "a signup found an existing account (reconcile path)",
              "try login, then password reset via the alias"),
    ErrorSpec("imap_unreachable", "IMAP unreachable",
              "the mailbox host is down or credentials are wrong",
              "verify the IMAP host and the Docker secret"),
    ErrorSpec("unauthorized", "Unauthorized",
              "missing/invalid bearer token or insufficient scope",
              "check the token scope"),
    ErrorSpec("not_found", "Not found",
              "the resource does not exist",
              "check the id"),
    ErrorSpec("internal", "Internal error",
              "an unexpected exception",
              "see the correlation id in the logs"),
]}


def get(code: str) -> ErrorSpec:
    """Return the spec for `code`, falling back to `internal` for unknown codes."""
    return ERRORS.get(code, ERRORS["internal"])
