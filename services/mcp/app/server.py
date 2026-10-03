"""MCP server for apply-app: the read/write job tools an AI assistant may call.

Non-negotiables (rule 9): this server NEVER exposes vault seal/unseal, password access, token
management, anything resembling submit (incl. mark-submitted), or shell/Docker/file access.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

_NO_SUBMIT = "mark_submitted and any submit action are intentionally NOT exposed via MCP."


def build_server(client) -> MCPServer:
    server = MCPServer(
        name="apply-app",
        version="0.1.0",
        instructions=(
            "Manage the local job-application queue. Reads need diagnose scope, writes need ops "
            f"scope. The agent never submits applications; {_NO_SUBMIT}"
        ),
    )

    @server.tool(description="List jobs, optionally filtered by state.")
    def list_jobs(state: str | None = None) -> list[dict]:
        return client.list_jobs(state)

    @server.tool(description="Get one job by id.")
    def get_job(job_id: int) -> dict:
        return client.get_job(job_id)

    @server.tool(description="Enqueue a new job application (never submits).")
    def enqueue(
        company_name: str,
        title: str,
        listing_url: str,
        application_url: str | None = None,
        description: str | None = None,
        ats: str | None = None,
        requires_account: bool = False,
        requires_verification: bool = True,
    ) -> dict:
        return client.create_job(
            {
                "company_name": company_name,
                "title": title,
                "listing_url": listing_url,
                "application_url": application_url,
                "description": description,
                "ats": ats,
                "requires_account": requires_account,
                "requires_verification": requires_verification,
            }
        )

    @server.tool(description="Cancel a job.")
    def cancel(job_id: int) -> dict:
        return client.job_action(job_id, "cancel")

    @server.tool(description="Skip a job (won't be retried).")
    def skip(job_id: int) -> dict:
        return client.job_action(job_id, "skip")

    @server.tool(description="Retry a failed job.")
    def retry(job_id: int) -> dict:
        return client.job_action(job_id, "retry")

    @server.tool(description="Requeue a job back to the queue.")
    def requeue(job_id: int) -> dict:
        return client.job_action(job_id, "requeue")

    @server.tool(description="Restage a job (re-fill with frozen answers + overrides).")
    def restage(job_id: int) -> dict:
        return client.job_action(job_id, "restage")

    @server.tool(description="Get the field diff (frozen answers + overrides) for a job.")
    def get_diff(job_id: int) -> dict:
        return client.get_review(job_id)

    @server.tool(description="Get a short-lived review link (KasmVNC) for a ready job.")
    def get_review_link(job_id: int) -> dict:
        return client.get_review_link(job_id)

    @server.tool(description="Set a per-job answer override (edit-and-rerun).")
    def update_answer(job_id: int, field: str, value: str) -> dict:
        return client.update_answers(job_id, {field: value})

    @server.tool(description="System status (doctor).")
    def system_status() -> dict:
        return client.doctor()

    return server
