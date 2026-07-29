from __future__ import annotations

import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_bridge_stdio_handshake_and_required_tools() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "codex_hermes_worker.bridge.server"],
        cwd=os.getcwd(),
        env={**os.environ, "CODEX_HERMES_CONFIG": os.path.join(os.getcwd(), "config", "default.yaml")},
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            response = await session.list_tools()
            names = {tool.name for tool in response.tools}
            assert {
                "hermes_health",
                "delegate_trusted_full_task",
                "delegate_local_task",
                "submit_local_job",
                "get_local_job_status",
                "get_local_job_summary",
                "query_local_results",
                "cancel_local_job",
            }.issubset(names)

            health = await session.call_tool("hermes_health", {})

    assert not health.isError
    assert health.structuredContent is not None
    assert health.structuredContent["ok"] is True, health.structuredContent
    assert health.structuredContent["hermes"]["qwen_ok"] is True, health.structuredContent
