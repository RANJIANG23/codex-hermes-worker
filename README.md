# Codex Hermes Worker

Current release: **1.0.0**

A Windows-first, dual-mode MCP bridge that lets Codex delegate bounded work to
Hermes Agent and a local Qwen model served through an OpenAI-compatible
endpoint such as LM Studio.

中文说明：[README.zh-CN.md](README.zh-CN.md)

## Architecture

```text
Codex
  -> project-local stdio MCP bridge
  -> Hermes Agent
  -> LM Studio / local Qwen
  -> restricted deterministic tools or explicitly authorized host tools
```

Codex remains responsible for planning, high-risk judgment, verification, and
the final answer. Hermes and the local model handle repetitive, batch-oriented,
and tool-heavy work.

## Key capabilities

- Eight high-level MCP tools for health, delegation, durable jobs, result
  summaries, bounded queries, cancellation, and explicitly authorized host work.
- SQLite job state with WAL, JSONL exports, review manifests, and recovery.
- `restricted_batch` for read-only research inputs and project-scoped outputs.
- `trusted_full` for explicitly authorized terminal, file, code, browser, skill,
  memory, and delegation capabilities available in Hermes.
- Windows PowerShell scripts for install, status, tests, and uninstall.
- Unit, integration, live MCP, Hermes, and local-model capability tests.

## Safety

`restricted_batch` is the default for untrusted or bulk input.

`trusted_full` is intentionally high risk. It can launch an unsandboxed host
terminal and must never be selected automatically merely because restricted
execution is inconvenient. Network access requires a separate opt-in.

Local secrets, generated Codex configuration, virtual environments, job data,
SQLite databases, logs, and Hermes profiles are excluded from version control.
See [SECURITY.md](SECURITY.md) before enabling host tools.

## Quick start

Requirements:

- Windows
- Python 3.11+
- Codex CLI or Desktop with local stdio MCP support
- Hermes Agent
- LM Studio or another OpenAI-compatible local model server
- A tool-capable local model

```powershell
git clone https://github.com/RANJIANG23/codex-hermes-worker.git
cd codex-hermes-worker
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\status.ps1
```

Run the complete validation flow:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

For configuration, first delegation examples, recovery, and uninstall
instructions, read the [Chinese guide](README.zh-CN.md).

## License

MIT
