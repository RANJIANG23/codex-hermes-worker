# 团队复用与部署

## 可复用范围

可共享：

- `src`、`config`（不含 `local.yaml`）、`scripts`、`tests`、`testdata`、`docs`
- `AGENTS.md`、`README.zh-CN.md`、`pyproject.toml`、`.env.example`

不得共享：

- `.env`、API Key、`.codex/config.toml`
- `.venv`、`work`、SQLite、日志、Hermes Profile、分析结果
- 真实游戏或研究源数据

## 每位成员的本地拓扑

```text
成员自己的 Codex
→ 成员本机 stdio MCP
→ 成员本机 Hermes
→ 成员本机 LM Studio / Qwen
```

系统不是 Hermes 远程控制 Codex，也不会共享 Codex 登录状态。Codex 是上层调用方。

## 每台电脑的前置条件

1. Windows、Codex CLI、Hermes Agent、Python 3.11+。
2. LM Studio OpenAI-compatible Server 正在运行。
3. 一个支持 Tool Calling 的本地模型；默认别名为 `qwen3.6-27b`。
4. `LMSTUDIO_API_KEY` 已进入启动 Codex 的进程环境。

版本或模型不同的成员先复制 `.env.example` 中的变量说明，并在未提交的 `config/local.yaml` 覆盖：

```yaml
hermes:
  base_url: http://127.0.0.1:1234/v1
  model: qwen3.6-27b
  api_key_env: LMSTUDIO_API_KEY
```

## 安装

每位成员在项目根目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

安装器会：

1. 自动发现 `hermes` 和相邻 Python，失败时回退到 PATH Python。
2. 创建本机 `.venv`。
3. 用本机绝对路径生成 `.codex/config.toml`。
4. 备份用户 Codex 配置，只信任当前项目。
5. 验证 Bridge 健康状态和 `codex mcp get hermes_worker`。

## 团队安全规则

- 不把一个人的 `work` 目录复制给另一个人。
- 不在聊天、Issue、Git 或配置模板中粘贴密钥。
- 默认使用 `restricted_batch`。
- `trusted_full` 只能用于任务发起人明确授权的电脑操作；网络再单独授权。
- 不把当前 stdio 服务未经认证地改成 LAN HTTP 服务。集中 GPU 需要身份认证、TLS、租户隔离、任务配额和审计，作为独立版本设计。

## 验收

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

然后新建以该项目为工作目录的 Codex 任务，要求它调用 `hermes_health`。返回的路径、模型和工具可用性应属于该成员自己的电脑。
