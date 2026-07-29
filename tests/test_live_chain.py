from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from codex_hermes_worker.bridge.config import load_config
from codex_hermes_worker.bridge.hermes_client import HermesClient


@pytest.mark.skipif(
    not os.getenv("RUN_LIVE_QWEN") or not os.getenv("LMSTUDIO_API_KEY"),
    reason="set RUN_LIVE_QWEN=1 with the runtime LM Studio key",
)
def test_hermes_qwen_calls_two_restricted_tools() -> None:
    config = load_config()
    client = HermesClient(config)
    audit = config.project_root / "work" / "logs" / "tool-audit.jsonl"
    before = audit.stat().st_size if audit.exists() else 0
    response = client.run_json(
        "Call list_workspace_files on testdata/tool_loop, then call read_text_excerpt "
        "on testdata/tool_loop/evidence.txt. Return only "
        '<json>{"answer":"QWEN_TWO_TOOL_CHAIN_OK","tools_used":'
        '["list_workspace_files","read_text_excerpt"],"confidence":0.95,'
        '"needs_review":false}</json> after both real calls.',
        timeout=180,
    )
    assert "QWEN_TWO_TOOL_CHAIN_OK" in str(response["json"])
    with audit.open("rb") as handle:
        handle.seek(before)
        delta = handle.read().decode("utf-8")
    rows = [json.loads(line) for line in delta.splitlines() if line.strip()]
    names = {row["tool"] for row in rows}
    assert {"list_workspace_files", "read_text_excerpt"}.issubset(names)


@pytest.mark.skipif(
    not os.getenv("RUN_LIVE_QWEN") or not os.getenv("LMSTUDIO_API_KEY"),
    reason="set RUN_LIVE_QWEN=1 with the runtime LM Studio key",
)
def test_trusted_full_uses_terminal_then_file_tool() -> None:
    config = load_config()
    client = HermesClient(config)
    output = config.project_root / "work" / "trusted-probe" / "terminal-created.txt"
    env_output = config.project_root / "work" / "trusted-probe" / "env-scrub.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    if env_output.exists():
        env_output.unlink()

    response = client.run_trusted(
        (
            "This is an authorized local integration test. You MUST first use the terminal "
            "tool to create work/trusted-probe/terminal-created.txt containing exactly "
            "HERMES_TRUSTED_TERMINAL_OK. In that same terminal call, run Python to write "
            "work/trusted-probe/env-scrub.json as a JSON object whose keys are "
            "LMSTUDIO_API_KEY, OPENAI_API_KEY, and OPENROUTER_API_KEY, and whose boolean "
            "values report whether each variable exists; never print or write any variable "
            "value. Then use read_file to read both created files and "
            "testdata/trusted_full_probe.txt. Do not use write_file or execute_code. Finish "
            "with exactly HERMES_TRUSTED_FULL_CHAIN_OK only after all reads succeed."
        ),
        working_directory=str(config.project_root),
        requested_toolsets=["terminal", "file"],
        allow_network=False,
        include_optional_tools=False,
        max_steps=8,
        timeout=180,
        authorization="explicit_user_authorized",
    )
    assert output.read_text(encoding="utf-8").strip() == "HERMES_TRUSTED_TERMINAL_OK"
    scrub_status = json.loads(env_output.read_text(encoding="utf-8"))
    assert scrub_status == {
        "LMSTUDIO_API_KEY": False,
        "OPENAI_API_KEY": False,
        "OPENROUTER_API_KEY": False,
    }
    assert "HERMES_TRUSTED_FULL_CHAIN_OK" in response["text"]
