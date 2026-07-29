# Codex Hermes Worker v1.0.0

发布日期 / Release date: 2026-07-30

## 中文

### 概述

`v1.0.0` 是首个正式公开版本。它提供一条已经在 Windows 上实际验证的分层调用链：

```text
Codex
→ 项目级 stdio MCP Bridge
→ Hermes Agent
→ LM Studio / 本地 Qwen
→ 受限工具或显式授权的主机工具
```

Codex 保留总体规划、复杂判断、冲突裁决和最终验收；Hermes/Qwen 处理重复、
批量和本机工具密集型工作。

### 主要功能

- 8 个高级 MCP 工具：健康检查、同步委派、耐久 Job、状态、摘要、有界查询、
  取消和显式授权的完整工具任务。
- SQLite WAL、事务、Job Event、恢复、完整 JSONL 和 review manifest。
- `restricted_batch` 默认模式：研究输入只读、无通用终端、无默认网络访问。
- `trusted_full` 显式授权模式：可使用 Hermes 当前可用的 terminal、file、
  code execution、browser、skills、memory、delegation 等工具。
- 资产分类、音频分类、反编译初筛和独立复核 Worker Profile。
- Windows 安装、启动、状态、测试、停止和卸载脚本。
- Codex 项目级 MCP 配置、备份、信任项和可回滚卸载。

### 验证

- 离线测试：21 passed，3 个 live 测试按预期 skipped。
- 本机历史完整验收包含 Hermes/Qwen 工具调用、MCP 握手、Codex 模型驱动调用、
  批任务、摘要隔离、取消和重启恢复。
- Qwen 工具协议能力测试：12/12 通过。
- Python wheel 构建成功：`codex_hermes_worker-1.0.0-py3-none-any.whl`。

### 安全边界

- `.env`、生成的 `.codex/config.toml`、`.venv`、`work`、数据库、日志、
  Hermes Profile 和真实研究数据不会进入版本控制。
- `trusted_full` 可以运行非沙箱主机终端。它必须由用户针对当前任务明确授权，
  且网络访问需要单独授权。
- 当前版本不是经过认证的局域网或公网多租户服务。

### 已知限制

- Hermes 正式调用目前使用已经实测的 CLI Bridge，而非专用 Agent REST Job API。
- Windows 没有内核级任务网络隔离。
- Ghidra、radare2、Rizin、ExifTool、TrID、DIE 等外部工具需要用户另行安装。
- Web Search、computer use、Home Assistant、Spotify、图像/视频生成等能力取决于
  Hermes 环境、系统依赖和独立凭据。

## English

### Overview

`v1.0.0` is the first public release. It provides a Windows-validated layered
execution path from Codex through a project-local stdio MCP bridge to Hermes
Agent, an OpenAI-compatible local model endpoint, and a tool-capable Qwen model.

Codex retains planning, high-risk judgment, conflict resolution, and final
verification. Hermes and the local model handle repetitive, batch-oriented, and
tool-heavy work.

### Highlights

- Eight high-level MCP tools for health, synchronous delegation, durable jobs,
  status, summaries, bounded result queries, cancellation, and explicitly
  authorized host work.
- SQLite WAL, transactions, job events, recovery, complete JSONL exports, and
  review manifests.
- `restricted_batch` as the default read-only research mode without a general
  shell or default network access.
- `trusted_full` for explicitly authorized Hermes terminal, file, code,
  browser, skill, memory, and delegation capabilities.
- Asset, audio, disassembly-triage, and independent-verification worker profiles.
- Windows scripts for install, start, status, tests, stop, and uninstall.
- Project-scoped Codex MCP configuration with backup and rollback guidance.

### Validation

- Offline suite: 21 passed and 3 live tests skipped as designed.
- Historical live acceptance covers Hermes/Qwen tool calls, MCP handshake,
  model-driven Codex invocation, batch jobs, summary isolation, cancellation,
  and restart recovery.
- Local Qwen tool-protocol capability suite: 12/12 passed.
- The `codex_hermes_worker-1.0.0-py3-none-any.whl` package builds successfully.

### Security boundaries

- Secrets, generated Codex configuration, virtual environments, work data,
  databases, logs, Hermes profiles, and private research inputs are excluded
  from version control.
- `trusted_full` can launch an unsandboxed host terminal. It requires explicit
  per-task authorization, with a separate opt-in for network access.
- This release is not an authenticated LAN or public multi-tenant service.

### Known limitations

- The verified production path currently uses the Hermes CLI bridge rather than
  a dedicated Agent REST job API.
- Windows does not provide kernel-level per-job network isolation here.
- External reverse-engineering and asset tools must be installed separately.
- Optional web, computer-use, smart-home, media-generation, and third-party
  capabilities depend on the local Hermes environment and separate credentials.
