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
- 新增“数据统计”页面，将全部任务、运行中、完成和待复核指标集中到该页面。
- 只读统计两套隔离 Hermes Profile 的输入/输出 Token、趋势和执行模式分布。
- 按 GPT‑5.6 Sol 标准短上下文公开价格和固定 2.5 倍用量倍率计算估算金额。
- 受限任务队列默认启用两路并发，可同时驱动两个本地 Qwen 任务。
- 防止重启前遗留的 Worker 覆盖已经结束的任务状态。
- 将含未解决条目的任务显示为“部分完成”，并分别统计完整完成和部分完成。
- 文本工具新增单文件搜索、通配符文件名搜索和偏移分段读取。
- 本地收敛超过 Schema 长度限制的摘要，减少无意义的模型修复调用。

### 验证

- 离线测试：32 passed，3 个可选实时测试按预期 skipped。
- 真实受限 Qwen 工具链测试通过，两个要求的 MCP 工具均实际调用成功。
- 两个受限任务在同一个 Qwen3.6 27B 上相隔约 0.03 秒启动，重叠运行
  34.2 秒，并且全部完整完成。
- 并发测试后 Hermes 生成两个独立会话，工具审计日志 125 行全部为有效
  JSON，没有出现并发写入损坏。
- Console、Bridge、Hermes、Qwen 和 SQLite 健康检查通过。

### 安全边界与限制

- 两路并发仅用于受限任务队列；`trusted_full` 仍要求逐次明确授权。
- 外部网络仍然默认关闭，完整模式的网络工具仍需单独授权。
- 并发任务共享同一个本地模型和硬件，总吞吐量可能提升，但单任务速度不会
  保证线性加倍。
- 控制台继续只监听 `127.0.0.1`，本版本不是局域网或公网多租户服务。

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
- An Analytics page for job-state metrics, input/output Token usage, daily
  trends, and restricted-versus-trusted execution breakdown.
- Read-only aggregation from the isolated Hermes usage ledgers, repriced at
  GPT-5.6 Sol standard short-context rates with a fixed 2.5 usage multiplier.
- The restricted job queue now runs up to two local Qwen tasks concurrently.
- Terminal job states can no longer be overwritten by a stale worker left from
  before a bridge restart.
- Jobs with unresolved records are surfaced as partially completed and counted
  separately from clean completions.
- Text tools now support single-file search, filename globs, and offset-based
  chunked reads.
- Overlong summaries are fitted locally to their schema limit instead of
  spending another model call on a length-only repair.

### Validation

- Offline suite: 32 passed and 3 optional live tests skipped as designed.
- A live restricted Qwen tool-chain test completed with both required MCP tools
  actually invoked.
- Two restricted jobs started about 0.03 seconds apart on the same Qwen3.6 27B
  model, overlapped for 34.2 seconds, and both completed cleanly.
- Hermes recorded two independent sessions, and all 125 tool-audit rows
  remained valid JSON after the concurrent run.
- Console, Bridge, Hermes, Qwen, and SQLite health checks passed.

### Security boundaries and limitations

- Two-way concurrency applies only to the restricted job queue;
  `trusted_full` still requires explicit authorization for every task.
- External network access remains disabled by default, with a separate opt-in
  for network tools in full mode.
- Concurrent jobs share one local model and the same hardware. Aggregate
  throughput may improve, but per-job speed is not guaranteed to scale
  linearly.
- The console remains bound to `127.0.0.1`; this is not a LAN or public
  multi-tenant service.
