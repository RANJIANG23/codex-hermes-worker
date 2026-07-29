# 架构

```text
Codex / GPT-5.6
  │  stdio MCP：8 个高级任务工具
  ▼
codex-hermes-worker
  ├─ Pydantic 参数与 Schema 校验
  ├─ SQLite Job、事件、恢复和结果查询
  ├─ 聚合摘要、完整 JSONL、review manifest
  ├─ MCP 只读/写入/高风险工具注解
  └─ 双执行模式
       │
       ├─ restricted_batch（默认）
       │    │ 独立 work/hermes-profile
       │    │ hermes chat -q -Q --max-turns
       │    ▼
       │  Hermes → LM Studio / qwen3.6-27b
       │    ▼
       │  codex_worker_tools
       │  受控读取、哈希、字符串、FFprobe、模拟反编译查询
       │
       └─ trusted_full（逐任务显式授权）
            │ 独立 work/hermes-profile-trusted
            │ --yolo + --checkpoints + 步数/超时/输出上限
            ▼
          Hermes → LM Studio / qwen3.6-27b
            ▼
          terminal、file、code_execution、browser、skills、
          memory、delegation、cronjob、可用 MCP 等 Hermes 工具
```

## 默认数据流

批处理任务写入 SQLite，并导出不受 MCP 查询上限影响的完整 JSONL。Codex 默认只读取聚合摘要、冲突和低置信度项；`query_local_results` 每次最多返回 100 条。

## 双模式边界

- `restricted_batch` 满足原始研究数据安全要求：无通用 shell、无网络工具、只读配置根、只写项目 `work`。
- `trusted_full` 满足显式提出的“像 Codex 一样使用可用工具”需求。调用方必须传入 `authorization="explicit_user_authorized"`；网络和可选外部工具还需 `allow_network=true`。
- `trusted_full` 的主机终端不是 OS 沙箱。工作目录虽然必须位于配置的可信根内，但终端命令仍可能使用绝对路径访问其他位置；这是能力本身带来的风险，不伪装成隔离。
- 两个模式使用不同 `HERMES_HOME`，不会改写用户默认 Hermes 配置。

## 团队复用

每位成员在自己的 Windows 电脑上运行同一套源码和安装器。安装器自动发现 Hermes/Python，创建本机 `.venv`，生成带本机绝对路径的项目 MCP 配置；模型、密钥、SQLite、日志和分析结果不跨成员共享。
