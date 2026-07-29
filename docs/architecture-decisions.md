# 架构决策

## ADR-001：选择方案 B

选择 Hermes CLI Bridge。

- `hermes serve` 是 JSON-RPC/WebSocket 后端；`hermes mcp serve` 暴露会话/消息面，都不是本任务所需的批处理 Job API。
- `hermes chat -q -Q --max-turns` 已实测完成本地 Qwen 多轮工具循环，并能按调用选择工具集。
- 既然方案 B 可用，不另写一套替代 Hermes 的 Agent Loop。

## ADR-002：两个隔离的 Hermes Home

- `work/hermes-profile`：默认受限批处理，只加载 `codex_worker_tools`。
- `work/hermes-profile-trusted`：显式授权的完整工具模式。

两者都不修改 `%LOCALAPPDATA%\hermes\config.yaml`、默认模型、默认 Skills 或默认 MCP。

## ADR-003：默认受限，完整能力显式升级

原始需求明确禁止向批处理 Qwen 暴露无限制 shell；后续需求又要求它能像 Codex 一样使用所有可调用工具。因此不把两者互相覆盖，而采用双模式：

- 大批量、不可信输入和游戏研究数据始终走 `restricted_batch`。
- 用户明确授权的通用电脑任务才走 `trusted_full`。
- `trusted_full` 还要求网络单独 opt-in，MCP 工具标记为 destructive/open-world，使 Codex 客户端能显示高风险确认。

## ADR-004：沿用 LM Studio

继续使用已运行的 Windows LM Studio GGUF 服务和 `qwen3.6-27b`，不安装 WSL/vLLM、不迁移模型、不改变现有模型服务参数。

## ADR-005：凭据仅做运行时映射并从工具环境剥离

Bridge 从 `LMSTUDIO_API_KEY` 读取令牌，映射给 Hermes 推理 Provider。启动 Hermes 后移除原始变量；Hermes 自身再从 terminal/execute_code 子进程环境剥离 Provider 密钥。错误请求转储中的 Authorization 字段会被二次改为 `<redacted>`。

## ADR-006：SQLite + JSONL

SQLite 是状态和查询源，启用 WAL、foreign keys 和事务。JSONL 是完整便携副本及复核清单。MCP 查询保持 `limit<=100`，但耐久导出使用流式全量读取，不会把第 101 条以后静默丢失。

## ADR-007：项目级 Codex MCP + 最小用户级信任项

MCP 定义位于项目 `.codex/config.toml`。Codex 只有在受信任项目中加载该文件，因此安装器备份用户配置后只增加本项目的 `trust_level="trusted"`，不添加全局 MCP Server。卸载脚本精确移除该信任段。

## ADR-008：本地团队拓扑优先

第一版采用每位成员本机的 stdio MCP，不开放 LAN 端口。它避免远程认证、密钥分发和多租户任务隔离问题。集中式 GPU/远程 Bridge 属于后续独立设计，不能通过直接暴露当前 stdio 服务替代。

## ADR-009：控制台采用本地 Web UI

1.1.0 选择由 Python 标准库 HTTP Server 承载原生 HTML/CSS/JavaScript，
不引入 Electron、Node 运行时或新的生产依赖。

- 保持 Windows 安装包轻量，现有 Python 虚拟环境即可运行。
- 浏览器负责渲染和响应式布局，团队成员无需学习命令行即可查看和提交任务。
- 只绑定回环地址并使用进程级请求令牌，不把当前实现当作远程多用户服务。
- UI 与 stdio MCP 共用业务层和 SQLite，但 UI 启动不会恢复或改写另一个进程
  正在执行的 Job。
- `trusted_full` 在界面中明确区分并逐次确认，不与默认受限任务混在同一提交
  按钮中。
