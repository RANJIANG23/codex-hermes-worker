# 环境勘察报告

核验日期：2026-07-30（Asia/Shanghai）  
项目：`<project-root>`

## 结论

本机具备方案 B（Hermes CLI Bridge）条件。`hermes chat -q -Q --max-turns` 能稳定完成本地 Qwen 多轮工具调用；`--oneshot` 在本机曾产生空工具代码，因此未采用。

## Hermes Agent

- 可执行文件：`%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\hermes.exe`
- 版本：Hermes Agent `v0.19.0 (2026.7.20)`；本任务未升级或卸载。
- Python 3.11.15；OpenAI SDK 2.24.0；SQLite 3.53.1；配置版本 33。
- 用户默认配置：`%LOCALAPPDATA%\hermes\config.yaml`。
- 用户默认模型仍为 DeepSeek；本项目没有修改。
- `hermes serve` 和 `hermes mcp serve` 均可启动，但不是目标 Job API。
- 选定入口：非交互 `hermes chat --query --quiet --max-turns`。
- 项目 Profile：`work/hermes-profile` 和 `work/hermes-profile-trusted`。
- `hermes doctor`：核心环境、Git、rg、Docker、Node、agent-browser、Playwright Chromium 正常；Croniter 未安装；Web/TUI 工作区报告构建时 npm advisory。

## 完整工具模式的 Hermes 能力

配置层已启用 Hermes CLI 列出的全部 24 类工具集以及 `codex_worker_tools`。2026-07-30 `hermes doctor` 当前确认可用：

- browser、clarify、code_execution、cronjob、delegation、file
- memory、session_search、skills、terminal、todo、tts

运行时不可用或缺少外部条件：

- `computer_use`、browser CDP：系统依赖不满足。
- `web_search`：没有 EXA/Parallel/Tavily/Firecrawl 等搜索凭据；普通 browser 工具可用。
- `x_search`、Home Assistant、Spotify、Yuanbao、vision/image/video generation：缺少各自凭据或系统依赖。

启用工具集不等于伪造依赖；Hermes 会把不可用工具从实际模型 Schema 中过滤。实测 `trusted_full` 已完成 terminal → 两次 `read_file`，并确认三个推理密钥变量在终端环境中均不存在。

## LM Studio / Qwen

- 地址：`http://127.0.0.1:1234/v1`，Bearer 鉴权。
- API：`/v1/models`、`/v1/chat/completions` 已通过；`/v1/responses` 可访问但不是正式路径。
- 模型别名：`qwen3.6-27b`。
- 实际文件 ID：`unsloth/qwen3.6-27b-gguf/qwen3.6-27b-ud-mtp-q8_k_xl.gguf`。
- GGUF Q8_K_XL，约 36.70 GB；`trainedForToolUse=true`、vision=true。
- LM Studio 报告最大/当前上下文 262144，parallel=4；项目为 Hermes 固定 65536 上下文。
- 12 项工具调用能力测试：12/12 通过。
- 兼容性陷阱：LM Studio 对不存在的 model ID 仍可能返回 HTTP 200，并静默使用当前加载模型；Bridge 因此先查询 `/models` 并检查精确别名。

## Codex

- CLI：`codex-cli 0.146.0-alpha.3.1`。
- 用户配置：`%USERPROFILE%\.codex\config.toml`。
- 项目 MCP：`<project-root>\.codex\config.toml`。
- 传输：stdio；`codex mcp get hermes_worker` 显示 enabled。
- 用户配置改动：仅新增本项目 trust 段。原始备份：`work/backups/config.toml.20260730-010949.bak`；重复安装还会产生带时间戳的用户/项目配置备份。
- `codex exec` 实测由 GPT-5.6 Sol 调用 `hermes_worker/hermes_health` 成功，返回 `ok=true`、模型 `qwen3.6-27b`、默认模式 `restricted_batch` 和 `trusted_full_enabled=true`。
- 首次 `codex exec` 因 `hermes_health` 缺少 MCP `readOnlyHint` 被客户端拒绝；补充 ToolAnnotations 后复测通过。

## 其他工具与硬件

- GPU：NVIDIA RTX PRO 6000 Blackwell Workstation Edition，97887 MiB，驱动 596.36。
- Node.js 24.15.0；npm 11.12.1；Git 2.53.0；Docker 29.5.2。
- FFmpeg/FFprobe 8.1.1。
- PATH 未发现 ExifTool、TrID、Detect It Easy CLI、radare2、Rizin、Ghidra headless。
- 第一版接入 FFprobe、自有 Python 工具和结构化模拟反编译数据；不为凑名单安装软件。

## 安全边界

- `restricted_batch` 默认只读 `testdata`、`work/input`，只写项目 `work` 的明确子目录，无 shell 和网络工具。
- `trusted_full` 是明确的高风险能力，不是强沙箱；必须逐任务授权，联网再单独授权。
- Windows 没有为 Hermes 进程建立内核级网络防火墙；默认模式依靠无网络工具、无 shell 和 loopback 推理实现应用层限制。
- 密钥只来自环境变量。项目扫描未发现 key-shaped 文本；Hermes 自带 Skills 中的示例 `Bearer token` 不属于凭据。
- PowerShell 系统策略为 Restricted；脚本使用进程级 `-ExecutionPolicy Bypass` 运行，不修改机器策略。
