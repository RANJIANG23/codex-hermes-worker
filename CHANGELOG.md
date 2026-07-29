# Changelog

## 1.0.0 - 2026-07-30

首个正式公开版本。

### 功能

- Codex 到 Hermes Agent 和本地 Qwen 的项目级 stdio MCP 调用链。
- 八个高级 MCP 工具，覆盖健康检查、同步委派、耐久 Job、状态、摘要、
  有界查询、取消和显式授权的完整工具任务。
- `restricted_batch` 默认安全模式与 `trusted_full` 高风险显式授权模式。
- SQLite WAL、Job Event、恢复、完整 JSONL 和 review manifest。
- 资产、音频、反编译初筛和独立复核 Worker Profile。
- Windows 安装、启动、状态、测试、停止和卸载脚本。
- 离线、实时 Hermes/Qwen、MCP 和 Codex 驱动验收测试。

### 安全边界

- 研究输入默认只读，输出限制在项目 `work` 目录。
- 密钥、本机 MCP 配置、虚拟环境、数据库、日志、任务结果和 Hermes
  Profile 不进入版本控制。
- `trusted_full` 可以运行非沙箱主机终端，必须由用户对当前任务明确授权；
  网络访问需要额外授权。
