# Codex MCP 配置与回滚

## 修改内容

项目级文件：

```text
<project-root>\.codex\config.toml
```

安装器按当前电脑路径生成 `hermes_worker` stdio 配置，使用项目 `.venv` Python、项目工作目录、`CODEX_HERMES_CONFIG` 和继承的 `LMSTUDIO_API_KEY`。密钥值不写入 TOML。

用户级文件：

```text
%USERPROFILE%\.codex\config.toml
```

只添加：

```toml
[projects.'<normalized-project-root>']
trust_level = "trusted"
```

没有添加全局 MCP Server，没有删除或改写已有 MCP。

## 备份

- 修改用户配置前的首份备份：`work\backups\config.toml.20260730-010949.bak`
- 每次安装：`work\backups\user-config.toml.<timestamp>.bak`
- 覆盖项目生成配置前：`work\backups\project-config.toml.<timestamp>.bak`

优先使用卸载脚本精确移除本项目配置。只有确认备份后没有其他 Codex 配置变更时，才整体复制旧备份覆盖用户配置。

## 安装与检查

本机 PowerShell 策略为 Restricted，因此使用进程级 Bypass：

```powershell
cd '<project-root>'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\status.ps1
codex mcp get hermes_worker
```

Bridge 是 stdio，不需要常驻端口。Codex 打开本项目任务时按需启动。

## 实际验证

- Python MCP Client：握手、8 个工具列表、`hermes_health` 实际调用通过。
- Codex CLI：GPT-5.6 Sol 通过 `codex exec` 调用 `hermes_worker/hermes_health`，结果为 `ok=true`。
- 高风险工具：stdio MCP 调用 `delegate_trusted_full_task`，Hermes/Qwen 实际调用 terminal，测试通过。

## 启动、停止

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop.ps1
```

`stop.ps1` 只清理项目 readiness marker；stdio 子进程由 Codex 任务生命周期关闭，不停止用户 Hermes、LM Studio 或 Gateway。

## 移除与恢复

预览：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\uninstall.ps1 -WhatIf
```

保留任务数据卸载：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\uninstall.ps1
```

连同项目 `work` 数据卸载：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\uninstall.ps1 -RemoveData
```

脚本精确移除本项目 trust 段、项目生成的 `.codex/config.toml` 和 `.venv`；不会删除源码、Hermes、LM Studio、模型或研究源数据。
