# Changelog

## 1.1.0 - 2026-07-30

### 新增

- 新增仅监听 `127.0.0.1` 的 Codex Hermes Console 本地 Web 界面。
- 提供链路健康状态、任务指标、任务队列、详情、结果预览和取消操作。
- 提供可校验的受限任务表单，以及带逐次风险确认的 `trusted_full` 入口。
- 新增 `start-ui.ps1`、`stop-ui.ps1` 和 `status-ui.ps1` Windows 管理脚本。
- 新增控制台请求令牌、Origin/Host 校验、CSP 和 64 KiB 请求体限制。
- 新增控制台数据库查询接口，并允许 UI 与 Codex MCP 进程安全共存。
- 新增“数据统计”页面，集中显示任务状态与本地算力 Token 用量。
- 只读汇总受限和完整工具两套 Hermes 账本的输入、输出、趋势与模式分布。
- 按 GPT‑5.6 Sol 标准短上下文公开价格计算本地 Worker Token 等价金额。
- 将该金额标为保守下限，并与完整端到端节省和实际 API 账单区分。

### 界面

- 中文优先的深色本地运维控制台，包含键盘焦点、减少动画和响应式布局。
- 桌面端、平板和窄屏浏览器布局。
- Token 趋势提供可访问的数字表格替代视图。

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
