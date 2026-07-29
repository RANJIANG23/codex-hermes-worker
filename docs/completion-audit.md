# 需求完成审计

对应正式版本：1.0.0

本表按原始 19 个章节核对当前机器上的权威证据。

| 要求 | 状态 | 证据 |
|---|---|---|
| 分层架构 | 完成 | `docs/architecture.md`；Codex model-driven MCP 调用；Hermes/Qwen live tests |
| 不预设环境 | 完成 | `docs/environment-report.md`；实际 Hermes、LM Studio、Codex、GPU、工具版本 |
| 不修改原始数据 | 完成 | 默认只读根和写入根；越界测试；模拟数据验收 |
| 确定性优先 | 完成 | SHA-256、元数据、魔数、熵、二进制、字符串、搜索、FFprobe |
| 架构 A/B/C 决策 | 完成 | `docs/architecture-decisions.md`，选择 B 并记录实测理由 |
| Hermes Bridge MCP | 完成 | 8 个高级工具；stdio 握手和实际调用 |
| 四个 Worker Profile | 完成 | asset、audio、disassembly、verification 配置文件 |
| 本地工具层 | 完成/本机降级 | 9 个受限工具；未安装的反汇编/资产工具不伪造 |
| 执行器安全策略 | 完成 | 路径解析、Schema、步骤、超时、输出、查询、日志轮转、密钥剥离 |
| 任务路由 | 完成 | 根目录 `AGENTS.md`；默认受限、升级条件、上下文隔离 |
| SQLite + JSONL | 完成 | 10 个指定表、WAL、事务、完整流式导出 |
| Qwen 12 项能力测试 | 完成 | `docs/qwen-tool-calling-report.md`，12/12 |
| Codex MCP 配置 | 完成 | 备份、项目配置、信任项、ToolAnnotations、Codex 实际调用 |
| 20 条资产验收 | 完成 | Job `779351a5-40f4-49d4-970d-2968624c707d`，20/20 |
| 10 条反编译验收 | 完成 | Job `17096685-47ad-46fa-924d-7c707d642044`，10/10 |
| 多步工具调用 | 完成 | 受限 2 工具；完整 terminal + 2 次 file |
| 摘要隔离 | 完成 | MCP summary 不含原始记录；query<=100；JSONL 全量 125 条测试 |
| 任务恢复 | 完成 | running 重启标 failed、partial retained；SQLite 一致性测试 |
| 安全边界测试 | 完成（默认模式） | 越界读写、未授权工具、步骤、超时、密钥和审计测试 |
| PowerShell 用户体验 | 完成 | install/start/stop/status/test/uninstall；实际执行和幂等测试 |
| 中文 README | 完成 | 12 项操作说明、双模式、故障排查、团队部署 |
| 工程质量 | 完成 | 类型、Pydantic、异常、事务、超时、5 MiB 审计轮转、单元/集成测试 |
| 最终报告 | 完成 | `docs/final-report.md` |

## 后续要求：完整工具与团队复用

- `trusted_full` 已实现，主机 terminal/file 实际通过。
- Hermes 所列全部工具集已在专属 Profile 中启用；缺依赖的工具由运行时过滤并记录。
- 安装器不含开发机绝对路径，按每台电脑生成项目 MCP 配置。
- 团队使用说明见 `docs/team-deployment.md`。
- 当前设计是每成员本机 stdio，不是共享 GPU 的远程多租户服务。

## 不声称完成的外部能力

- 未安装的 Ghidra/radare2/Rizin/ExifTool/TrID/DIE。
- 缺少独立凭据或驱动的 Web Search、X、computer_use、Home Assistant、Spotify、图像/视频生成。
- Windows 内核级网络隔离。
- 无认证 LAN/公网 Bridge。

这些属于本机依赖或下一版本架构，不影响第一版本地 stdio 分层系统的完成。
