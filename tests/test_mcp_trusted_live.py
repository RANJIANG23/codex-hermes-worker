from __future__ import annotations

import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("RUN_LIVE_QWEN") or not os.getenv("LMSTUDIO_API_KEY"),
    reason="set RUN_LIVE_QWEN=1 with the runtime LM Studio key",
)
async def test_mcp_trusted_full_tool_reaches_hermes_qwen_terminal() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "codex_hermes_worker.bridge.server"],
        cwd=os.getcwd(),
        env={
            **os.environ,
            "CODEX_HERMES_CONFIG": os.path.join(
                os.getcwd(), "config", "default.yaml"
            ),
        },
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            response = await session.call_tool(
                "delegate_trusted_full_task",
                {
                    "instructions": (
                        "Use the terminal tool exactly once to run an echo command that prints "
                        "HERMES_MCP_TRUSTED_FULL_OK. Then return exactly that marker."
                    ),
                    "authorization": "explicit_user_authorized",
                    "working_directory": os.getcwd(),
                    "toolsets": ["terminal"],
                    "allow_network": False,
                    "include_optional_tools": False,
                    "max_steps": 4,
                    "timeout_seconds": 120,
                },
            )
    assert not response.isError
    assert response.structuredContent is not None
    assert response.structuredContent["status"] == "completed"
    assert "HERMES_MCP_TRUSTED_FULL_OK" in response.structuredContent["result"]
