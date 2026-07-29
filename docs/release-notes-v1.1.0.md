# Codex Hermes Worker 1.1.0

发布日期：2026-07-30

## 中文

1.1.0 将原有 MCP Bridge 扩展为带本地操作界面的 Windows 分层代理工具。

### 主要更新

- 新增 Codex Hermes Console 深色本地控制台。
- 可查看 Bridge、Hermes、Qwen 和 SQLite 健康状态。
- 可提交受限批处理任务并查看队列、进度、事件和结构化结果。
- 可取消排队中或运行中的任务。
- 为 `trusted_full` 提供独立高风险页面、工具组选择和逐次明确授权。
- 新增一键启动、停止和状态 PowerShell 脚本。
- 控制台只监听 `127.0.0.1`，加入随机请求令牌、Host/Origin 校验和 CSP。

### 启动

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

默认地址：`http://127.0.0.1:8765/`

## English

Version 1.1.0 adds a local Windows operations console while preserving the
existing stdio MCP integration.

### Highlights

- Live Bridge, Hermes, Qwen, and SQLite health.
- Restricted job submission, queue, progress, events, result previews, and
  cancellation.
- A separate high-risk `trusted_full` surface with per-run acknowledgement.
- Windows scripts for console start, stop, and status.
- Loopback-only binding, a per-process request token, Host/Origin validation,
  CSP, and bounded request bodies.
