# Codex + Hermes + 本地 Qwen 分层代理

当前正式版本：**1.1.0**

这是一个可运行、可测试、可给其他团队成员复用的 Windows 本地分层代理系统：

```text
Codex / GPT-5.6
→ 项目级 stdio MCP Bridge
→ Hermes Agent
→ LM Studio / Qwen3.6 27B
→ 受限批处理工具或显式授权的完整 Hermes 工具
```

Codex 负责规划、复杂推理、冲突裁决和最终验收；Hermes/Qwen 负责批量、重复和本机工具密集型工作。

## 组件作用

- Codex：上层主代理和最终决策者。
- Bridge：8 个高级 MCP 工具、参数校验、任务状态、摘要隔离和双模式权限。
- Hermes：本地 Agent Loop，选择并调用工具。
- Qwen：本地语义判断、分类、初筛、复核和工具规划。
- SQLite/JSONL：任务、证据、结果和复核清单的持久存储。

## 两种执行模式

### `restricted_batch`（默认）

用于游戏研究数据、外部输入和批处理：

- 无通用终端、无浏览器、无网络工具。
- 只读 `testdata`、`work/input` 或 `config/local.yaml` 中明确加入的目录。
- 只写本项目 `work`。
- 通过专用工具做哈希、字符串、二进制切片、FFprobe 和结构化查询。

### `trusted_full`（显式授权）

用于你明确希望 Hermes/Qwen 像 Codex 一样执行的电脑任务：

- 可选择 terminal、file、code_execution、browser、skills、memory、delegation、cronjob 和可用 MCP。
- 必须传 `authorization="explicit_user_authorized"`。
- 外部网络或可选第三方工具还必须传 `allow_network=true`。
- 主机终端不是沙箱，可能修改文件或执行危险命令。不要对不可信网页、文档或批量输入默认使用。

完整能力与当前缺失依赖见 `docs/hermes-full-tool-report.md`。

## 首次安装

这台电脑的 PowerShell 策略禁止直接运行 `.ps1`，使用仅影响当前子进程的 Bypass：

```powershell
git clone https://github.com/RANJIANG23/codex-hermes-worker.git
cd codex-hermes-worker
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

安装器会自动发现 Hermes/Python、创建 `.venv`、生成本机 `.codex/config.toml`、备份用户 Codex 配置并只添加当前项目的信任项。它不会升级 Hermes、改变 LM Studio 模型或写入密钥。

安装完成后，重新打开一个以本项目为工作目录的 Codex 任务。

## 启动、停止、状态

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\status.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop.ps1
```

Bridge 是 stdio MCP，不监听常驻端口。Codex 按任务需要启动；`stop.ps1` 不停止用户 Hermes、LM Studio 或 Gateway。

### 1.1.0 本地控制台

`start.ps1` 默认同时启动控制台并在浏览器打开：

```text
http://127.0.0.1:8765/
```

控制台提供：

- Codex → Bridge → Hermes → Qwen 链路健康状态；
- 独立“数据统计”页面，集中显示任务总数、运行中、完成和待复核指标；
- 汇总受限批处理与完整工具两种模式的输入 Token、输出 Token 和每日趋势；
- 按 GPT‑5.6 Sol 标准短上下文公开价格计算本地 Worker Token 等价金额；
- 将该保守下限与完整端到端节省、实际 API 账单明确区分；
- 受限批处理任务表单；
- 任务队列、进度、事件、结果预览和取消操作；
- 带非沙箱风险提示和逐次确认的 `trusted_full` 任务入口。

只启动或管理 UI：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-ui.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\status-ui.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop-ui.ps1
```

控制台只绑定 `127.0.0.1`，使用每次启动生成的请求令牌，并校验 Host、
Origin 和请求大小。当前版本不应通过端口转发或代理开放到局域网。

Token 数据从项目隔离的两套 Hermes `state.db` 账本中只读汇总，并只统计
本系统以 `source=tool` 产生的会话。金额按 GPT‑5.6 Sol 标准短上下文公开
价格计算：输入 `$5/百万`、缓存输入 `$0.50/百万`、缓存写入 `$6.25/百万`、
输出 `$30/百万`。

该金额只是本地 Worker 直接 Token 的等价成本，是保守下限，不是完整的
“实际节省”。它未覆盖 Codex 上层的系统提示词、工具定义与返回、上下文
重放、失败重试和独立复核。本地 LM Studio 推理通常没有 API 账单，因此
提供方报告的实际扣费会单独显示。

## 在 Codex 中确认 MCP

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

## 第一个受限批处理任务

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

## 第一个完整工具任务

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

若确实需要浏览器或网络，必须在同一任务中明确授权并设置 `allow_network: true`。

## 查看结果

- SQLite：`work\database\jobs.db`
- 完整 JSONL：`work\results\<job_id>.jsonl`
- 复核清单：`work\review\<job_id>.jsonl`
- 受限工具审计：`work\logs\tool-audit.jsonl`
- 完整模式审计：`work\logs\trusted-full-audit.jsonl`

MCP 查询最多 100 条，但 JSONL 全量导出不受该上限影响。

## 更换游戏或研究目录

创建不会提交的 `config\local.yaml`：

```yaml
filesystem:
  readable_roots:
    - D:\YourReadOnlyResearchDirectory
    - testdata
    - work\input
```

不要把原始游戏目录加入 `writable_roots`。

若希望 `trusted_full` 从另一个工作区启动：

```yaml
trusted_full:
  working_roots:
    - D:\YourTrustedWorkspace
```

这只限制启动工作目录，不是主机终端的强文件系统沙箱。

## 测试

全部测试：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

只跑离线测试：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -SkipLive
```

## 故障排查

- `LMSTUDIO_API_KEY missing`：启动 Codex 的进程必须继承该变量；不要把值写入项目。
- Qwen 不可达：检查 LM Studio Local Server、`127.0.0.1:1234` 和加载的 `qwen3.6-27b`。
- Hermes 不可达：运行 `hermes --version`、`hermes doctor`；项目不会自动升级 Hermes。
- MCP 不出现：确认项目受信任，关闭并重新打开本项目 Codex 任务，再运行 `codex mcp get hermes_worker`。
- Web 搜索不可用：Hermes 当前没有 EXA/Tavily/Firecrawl 等凭据；普通 agent-browser 已安装。
- computer_use/图像生成不可用：当前系统依赖或服务凭据未满足，不能只靠打开开关解决。
- 脚本被策略拒绝：使用上述 `powershell.exe -ExecutionPolicy Bypass -File`，不要修改系统全局策略。

## 恢复 Codex 配置

详细记录见 `docs/codex-mcp-setup.md`。预览卸载影响：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\uninstall.ps1 -WhatIf
```

卸载脚本会精确移除本项目 trust 段和生成的项目 MCP 配置。`work\backups` 保存修改前副本；整体恢复旧副本前应确认没有更新的 Codex 配置需要保留。

## 完全卸载

保留任务数据：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\uninstall.ps1
```

同时删除本项目生成的 `work` 数据：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\uninstall.ps1 -RemoveData
```

不会删除源码、Hermes、LM Studio、模型或研究源数据。

## 安全与许可证

- 请勿提交 `.env`、本机 `.codex/config.toml`、`work`、SQLite、日志或 Hermes Profile。
- `trusted_full` 可以启动非沙箱主机终端，只能在用户明确授权的可信任务中使用。
- 安全问题请按 `SECURITY.md` 通过 GitHub Private Vulnerability Reporting 报告。
- 本项目采用 MIT License，详见 `LICENSE`。

## 给团队成员使用

团队成员应复制源码和配置模板，不复制 `.venv`、`.codex/config.toml`、`work`、`.env` 或任何密钥。每个人在自己的电脑运行安装器，形成：

```text
成员自己的 Codex → 本机 Bridge → 本机 Hermes → 本机 Qwen
```

详见 `docs/team-deployment.md`。当前版本不是无认证的远程 GPU 服务，不应直接开放到局域网。
