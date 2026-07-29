# Codex Hermes Worker

Current release / 当前正式版本：**1.0.0**

[English](#english) | [简体中文](#简体中文)

## English

A Windows-first, dual-mode MCP bridge that lets Codex delegate bounded work to
Hermes Agent and a local Qwen model served through an OpenAI-compatible
endpoint such as LM Studio.

### Architecture

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

### Key capabilities

- Eight high-level MCP tools for health, delegation, durable jobs, result
  summaries, bounded queries, cancellation, and explicitly authorized host work.
- SQLite job state with WAL, JSONL exports, review manifests, and recovery.
- `restricted_batch` for read-only research inputs and project-scoped outputs.
- `trusted_full` for explicitly authorized terminal, file, code, browser, skill,
  memory, and delegation capabilities available in Hermes.
- Windows PowerShell scripts for install, status, tests, and uninstall.
- Unit, integration, live MCP, Hermes, and local-model capability tests.

### Safety

`restricted_batch` is the default for untrusted or bulk input.

`trusted_full` is intentionally high risk. It can launch an unsandboxed host
terminal and must never be selected automatically merely because restricted
execution is inconvenient. Network access requires a separate opt-in.

Local secrets, generated Codex configuration, virtual environments, job data,
SQLite databases, logs, and Hermes profiles are excluded from version control.
See [SECURITY.md](SECURITY.md) before enabling host tools.

### Quick start

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

### License

MIT

---

## 简体中文

这是一个可运行、可测试、可供其他团队成员复用的 Windows 本地分层代理系统：

```text
Codex / GPT-5.6
→ 项目级 stdio MCP Bridge
→ Hermes Agent
→ LM Studio / Qwen3.6 27B
→ 受限批处理工具或显式授权的完整 Hermes 工具
```

Codex 负责规划、复杂推理、冲突裁决和最终验收；Hermes/Qwen 负责批量、重复和本机工具密集型工作。

### 组件作用

- Codex：上层主代理和最终决策者。
- Bridge：提供 8 个高级 MCP 工具、参数校验、任务状态、摘要隔离和双模式权限。
- Hermes：本地 Agent Loop，选择并调用工具。
- Qwen：负责本地语义判断、分类、初筛、复核和工具规划。
- SQLite/JSONL：持久保存任务、证据、结果和复核清单。

### 两种执行模式

#### `restricted_batch`（默认）

用于游戏研究数据、外部输入和批处理：

- 无通用终端、无浏览器、无网络工具。
- 只读 `testdata`、`work/input` 或 `config/local.yaml` 中明确加入的目录。
- 只写本项目的 `work` 目录。
- 通过专用工具执行哈希、字符串、二进制切片、FFprobe 和结构化查询。

#### `trusted_full`（显式授权）

用于你明确希望 Hermes/Qwen 像 Codex 一样执行的电脑任务：

- 可选择 terminal、file、code_execution、browser、skills、memory、delegation、cronjob 和可用 MCP。
- 必须传入 `authorization="explicit_user_authorized"`。
- 外部网络或可选第三方工具还必须传入 `allow_network=true`。
- 主机终端不是沙箱，可能修改文件或执行危险命令。不要对不可信网页、文档或批量输入默认使用。

完整能力和当前缺失依赖见 [Hermes 完整工具报告](docs/hermes-full-tool-report.md)。

### 快速开始

环境要求：

- Windows
- Python 3.11+
- 支持本地 stdio MCP 的 Codex CLI 或 Desktop
- Hermes Agent
- LM Studio 或其他兼容 OpenAI API 的本地模型服务
- 支持工具调用的本地模型

```powershell
git clone https://github.com/RANJIANG23/codex-hermes-worker.git
cd codex-hermes-worker
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\status.ps1
```

运行完整验证流程：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

Bridge 是 stdio MCP，不监听常驻端口。Codex 会按任务需要启动它。

### 在 Codex 中确认 MCP

```text
请调用 hermes_health，并只报告：
1. 总体状态；
2. Hermes 版本；
3. Qwen 模型 ID；
4. 默认执行模式；
5. trusted_full 是否启用。
```

命令行检查：

```powershell
codex mcp get hermes_worker
```

### 第一个受限批处理任务

```text
请先调用 hermes_health。

然后调用 submit_local_job：
- task_type: asset_classification
- instructions: 使用确定性元数据和字符串证据分类；不修改输入
- input_paths: ["testdata/assets.jsonl"]
- profile: asset_worker
- output_schema: asset_classification_v1
- max_steps: 8

只返回 job_id。随后轮询 get_local_job_status，完成后读取
get_local_job_summary。只在需要复核时调用 query_local_results，
不要把完整批次载入主上下文。
```

### 第一个完整工具任务

只在你明确接受风险时使用：

```text
我明确授权本次任务使用 trusted_full，但不授权外部网络。

请调用 delegate_trusted_full_task：
- authorization: explicit_user_authorized
- working_directory: D:\WorkSpace
- toolsets: ["terminal", "file", "code_execution", "skills"]
- allow_network: false
- include_optional_tools: false
- max_steps: 20
- timeout_seconds: 600
- instructions: <具体任务>

完成后只返回结果摘要、修改文件列表和审计日志路径。
```

如确实需要浏览器或网络，必须在同一任务中明确授权并设置 `allow_network: true`。

### 结果与配置

- SQLite：`work\database\jobs.db`
- 完整 JSONL：`work\results\<job_id>.jsonl`
- 复核清单：`work\review\<job_id>.jsonl`
- 受限工具审计：`work\logs\tool-audit.jsonl`
- 完整模式审计：`work\logs\trusted-full-audit.jsonl`

本机目录配置保存在不会提交的 `config\local.yaml` 中。不要把原始游戏目录加入 `writable_roots`。本地密钥、生成的 Codex 配置、虚拟环境、任务数据、数据库和日志均已排除在版本控制之外。

### 安全与团队复用

`restricted_batch` 是处理不可信输入或批量数据时的默认模式。`trusted_full` 可以启动非沙箱主机终端，只能用于用户明确授权的可信任务。启用主机工具前请阅读 [SECURITY.md](SECURITY.md)。

团队成员应复制源码和配置模板，不应复制 `.venv`、`.codex/config.toml`、`work`、`.env` 或任何密钥。每个人都应在自己的电脑上运行安装器，形成：

```text
成员自己的 Codex → 本机 Bridge → 本机 Hermes → 本机 Qwen
```

团队部署方法见 [docs/team-deployment.md](docs/team-deployment.md)。当前版本不是无认证的远程 GPU 服务，不应直接开放到局域网。

更完整的安装、配置、恢复、故障排查和卸载说明见 [中文详细指南](README.zh-CN.md)。

### 许可证

MIT
