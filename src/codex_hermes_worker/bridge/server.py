from __future__ import annotations

import sqlite3
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from codex_hermes_worker.bridge.runtime import get_runtime
from codex_hermes_worker.bridge.schemas import (
    QueryFilters,
    TaskRequest,
    TrustedFullTaskRequest,
)
from codex_hermes_worker.policies.limits import bounded_limit


MCP = FastMCP(
    "codex-hermes-worker",
    instructions=(
        "Delegate bounded bulk work to an isolated local Hermes Agent backed by Qwen. "
        "Read summaries before individual records. trusted_full is a separate, explicit "
        "user-authorized mode with host terminal and network risk."
    ),
)

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
LOCAL_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
TRUSTED_FULL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)
CANCEL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)

@MCP.tool(annotations=READ_ONLY)
def hermes_health() -> dict[str, Any]:
    """Check bridge, Hermes, local Qwen, database, policies, profiles, and tool capabilities."""
    runtime = get_runtime()
    hermes = runtime.hermes.health()
    try:
        with runtime.database.connection() as conn:
            sqlite_version = conn.execute("select sqlite_version()").fetchone()[0]
        database_ok = True
    except sqlite3.Error:
        sqlite_version = None
        database_ok = False
    return {
        "ok": bool(hermes.get("ok") and database_ok),
        "bridge": {"status": "ready", "name": runtime.config.bridge.name},
        "hermes": hermes,
        "database": {
            "ok": database_ok,
            "sqlite_version": sqlite_version,
            "path": str(runtime.config.jobs.database),
            "recovered_jobs": runtime.manager.recovered_jobs,
        },
        "jobs": {
            "max_workers": runtime.config.jobs.max_workers,
        },
        "work_directory": str(runtime.config.project_root / "work"),
        "security": {
            "default_execution_mode": "restricted_batch",
            "readable_roots": [str(p) for p in runtime.config.filesystem.readable_roots],
            "writable_roots": [str(p) for p in runtime.config.filesystem.writable_roots],
            "allow_network": runtime.config.agent.allow_network,
            "allow_unrestricted_shell": runtime.config.agent.allow_unrestricted_shell,
            "max_steps": runtime.config.agent.max_steps,
            "max_tool_calls": runtime.config.agent.max_tool_calls,
            "max_runtime_seconds": runtime.config.agent.max_runtime_seconds,
            "trusted_full": {
                "enabled": runtime.config.trusted_full.enabled,
                "requires_explicit_authorization": True,
                "working_roots": [
                    str(path) for path in runtime.config.trusted_full.working_roots
                ],
                "local_toolsets": runtime.config.trusted_full.local_toolsets,
                "network_toolsets": runtime.config.trusted_full.network_toolsets,
                "optional_toolsets": runtime.config.trusted_full.optional_toolsets,
                "network_requires_per_task_opt_in": True,
                "host_shell_is_not_sandboxed": True,
            },
        },
        "profiles": sorted(runtime.config.profiles),
        "capabilities": [
            "bounded_file_listing",
            "bounded_text_read",
            "bounded_binary_slice",
            "sha256_magic_entropy",
            "printable_strings",
            "filename_search",
            "bounded_text_search",
            "ffprobe",
            "mock_disassembly_query",
            "persistent_jobs",
            "trusted_full_agent",
        ],
    }


@MCP.tool(annotations=TRUSTED_FULL)
def delegate_trusted_full_task(
    instructions: str,
    authorization: str,
    working_directory: str = ".",
    toolsets: list[str] | None = None,
    allow_network: bool = False,
    include_optional_tools: bool = False,
    max_steps: int = 20,
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    """Run a user-authorized Hermes/Qwen task with broad host tools.

    This mode enables unsandboxed host terminal/file/code tools and bypasses
    Hermes command prompts so it can run non-interactively. Pass
    authorization="explicit_user_authorized" only after the user explicitly
    authorizes this risk. Network and optional external tools require the
    separate allow_network=true opt-in.
    """
    request = TrustedFullTaskRequest(
        instructions=instructions,
        authorization=authorization,
        working_directory=working_directory,
        toolsets=toolsets or [],
        allow_network=allow_network,
        include_optional_tools=include_optional_tools,
        max_steps=max_steps,
        timeout_seconds=timeout_seconds,
    )
    response = get_runtime().hermes.run_trusted(
        request.instructions,
        working_directory=request.working_directory,
        requested_toolsets=request.toolsets,
        allow_network=request.allow_network,
        include_optional_tools=request.include_optional_tools,
        max_steps=request.max_steps,
        timeout=request.timeout_seconds,
        authorization=request.authorization,
    )
    return {
        "status": "completed",
        "task_id": response["task_id"],
        "execution_mode": response["execution_mode"],
        "working_directory": response["working_directory"],
        "toolsets": response["toolsets"],
        "allow_network": response["allow_network"],
        "result": response["text"],
        "runtime_seconds": response["runtime_seconds"],
        "output_truncated": response["stdout_truncated"],
        "audit_log": response["audit_log"],
        "model": response["model"],
    }


@MCP.tool(annotations=LOCAL_WRITE)
def delegate_local_task(
    task_type: str,
    instructions: str,
    input_paths: list[str],
    profile: str,
    output_schema: str,
    max_steps: int = 8,
) -> dict[str, Any]:
    """Run one bounded local task synchronously with strict path/type/schema validation."""
    request = TaskRequest(
        task_type=task_type,
        instructions=instructions,
        input_paths=input_paths,
        profile=profile,
        output_schema=output_schema,
        max_steps=max_steps,
    )
    return get_runtime().manager.run_sync(request)


@MCP.tool(annotations=LOCAL_WRITE)
def submit_local_job(
    task_type: str,
    instructions: str,
    input_paths: list[str],
    profile: str,
    output_schema: str,
    max_steps: int = 8,
) -> dict[str, Any]:
    """Queue a batch job and return immediately with a job ID."""
    request = TaskRequest(
        task_type=task_type,
        instructions=instructions,
        input_paths=input_paths,
        profile=profile,
        output_schema=output_schema,
        max_steps=max_steps,
    )
    return get_runtime().manager.submit(request)


@MCP.tool(annotations=READ_ONLY)
def get_local_job_status(job_id: str) -> dict[str, Any]:
    """Return bounded status, progress, counts, timestamps, and concise error."""
    return get_runtime().database.get_job(job_id)


@MCP.tool(annotations=READ_ONLY)
def get_local_job_summary(job_id: str) -> dict[str, Any]:
    """Return aggregate counts and artifact paths without raw batch output."""
    runtime = get_runtime()
    summary = runtime.database.summary(job_id)
    summary["result_jsonl"] = str(runtime.config.jobs.result_jsonl_dir / f"{job_id}.jsonl")
    summary["review_manifest"] = str(runtime.config.jobs.review_dir / f"{job_id}.jsonl")
    return summary


@MCP.tool(annotations=READ_ONLY)
def query_local_results(
    job_id: str | None = None,
    low_confidence: bool | None = None,
    label: str | None = None,
    path_contains: str | None = None,
    function_address: str | None = None,
    needs_review: bool | None = None,
    conflict: bool | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Query a bounded subset by confidence, label, path, address, review, conflict, or job."""
    runtime = get_runtime()
    actual_limit = bounded_limit(
        limit, runtime.config.bridge.default_query_limit, runtime.config.bridge.max_query_limit
    )
    filters = QueryFilters(
        job_id=job_id,
        low_confidence=low_confidence,
        label=label,
        path_contains=path_contains,
        function_address=function_address,
        needs_review=needs_review,
        conflict=conflict,
        limit=actual_limit,
    ).model_dump()
    rows = runtime.database.query(filters, actual_limit)
    return {"count": len(rows), "limit": actual_limit, "results": rows}


@MCP.tool(annotations=CANCEL)
def cancel_local_job(job_id: str) -> dict[str, Any]:
    """Request cooperative cancellation without damaging committed results."""
    return get_runtime().database.cancel(job_id)


def main() -> None:
    MCP.run(transport="stdio")


if __name__ == "__main__":
    main()
