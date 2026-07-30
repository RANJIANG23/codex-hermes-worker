from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from codex_hermes_worker.bridge.config import load_config
from codex_hermes_worker.policies.filesystem import FilesystemPolicy
from codex_hermes_worker.worker_tools.audit import append_audit
from codex_hermes_worker.worker_tools.deterministic import (
    binary_slice,
    file_metadata,
    ffprobe_metadata,
    printable_strings,
    search_file_names as deterministic_search_file_names,
    search_text as deterministic_search_text,
    text_excerpt,
)


CONFIG = load_config()
POLICY = FilesystemPolicy(CONFIG)
MCP = FastMCP(
    "codex-worker-tools",
    instructions="Read-only, bounded deterministic tools for local research tasks.",
)


def _run(tool: str, arguments: dict[str, Any], callback):
    try:
        result = callback()
        append_audit(CONFIG, tool, arguments, "ok")
        return result
    except Exception:
        append_audit(CONFIG, tool, arguments, "error")
        raise


@MCP.tool()
def list_workspace_files(path: str = "testdata", limit: int = 100) -> dict[str, Any]:
    """List bounded file metadata under an allowed read root."""
    args = {"path": path, "limit": limit}

    def action():
        root = POLICY.resolve_read(path)
        if not root.is_dir():
            raise NotADirectoryError(root)
        rows = []
        cap = max(1, min(limit, 500))
        for item in sorted(root.rglob("*")):
            if item.is_file():
                rows.append(
                    {
                        "path": POLICY.relative_display(item),
                        "size": item.stat().st_size,
                        "extension": item.suffix.lower(),
                    }
                )
            if len(rows) >= cap:
                break
        return {"files": rows, "limit": cap, "truncated": len(rows) >= cap}

    return _run("list_workspace_files", args, action)


@MCP.tool()
def read_text_excerpt(
    path: str, max_chars: int = 4000, offset_chars: int = 0
) -> dict[str, Any]:
    """Read a bounded UTF-8 text chunk; use offset_chars to continue a large file."""
    args = {
        "path": path,
        "max_chars": max_chars,
        "offset_chars": offset_chars,
    }
    return _run(
        "read_text_excerpt",
        args,
        lambda: text_excerpt(POLICY, path, max_chars, offset_chars),
    )


@MCP.tool()
def get_file_metadata(path: str) -> dict[str, Any]:
    """Return deterministic size, hash, magic, extension, MIME guess, and entropy."""
    args = {"path": path}
    return _run("get_file_metadata", args, lambda: file_metadata(POLICY, path))


@MCP.tool()
def read_binary_slice(path: str, offset: int, length: int) -> dict[str, Any]:
    """Read one bounded binary slice as hexadecimal."""
    args = {"path": path, "offset": offset, "length": length}
    return _run("read_binary_slice", args, lambda: binary_slice(POLICY, path, offset, length))


@MCP.tool()
def extract_printable_strings(path: str, limit: int = 100) -> dict[str, Any]:
    """Extract bounded ASCII strings from a file without invoking a model."""
    args = {"path": path, "limit": limit}
    return _run("extract_printable_strings", args, lambda: printable_strings(POLICY, path, limit))


@MCP.tool()
def search_file_names(path: str, query: str, limit: int = 100) -> dict[str, Any]:
    """Find bounded filename matches; query may be text or a glob such as *.json."""
    args = {"path": path, "query": query, "limit": limit}
    return _run(
        "search_file_names",
        args,
        lambda: deterministic_search_file_names(POLICY, path, query, limit),
    )


@MCP.tool()
def search_text(path: str, query: str, limit: int = 100) -> dict[str, Any]:
    """Search one allowed text file or all eligible files below an allowed directory."""
    args = {"path": path, "query": query, "limit": limit}
    return _run(
        "search_text",
        args,
        lambda: deterministic_search_text(POLICY, path, query, limit),
    )


@MCP.tool()
def run_ffprobe(path: str) -> dict[str, Any]:
    """Run the fixed ffprobe metadata command on an allowed input path."""
    args = {"path": path}
    return _run("run_ffprobe", args, lambda: ffprobe_metadata(CONFIG, POLICY, path))


@MCP.tool()
def query_mock_function(address: str) -> dict[str, Any]:
    """Query one test pseudocode record by address; never modifies a disassembler DB."""
    args = {"address": address}

    def action():
        source = POLICY.resolve_read("testdata/functions.jsonl")
        for line in source.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("address", "").lower() == address.lower():
                return row
        return {"address": address, "found": False}

    return _run("query_mock_function", args, action)


def main() -> None:
    MCP.run(transport="stdio")


if __name__ == "__main__":
    main()
