# 架构

```text
Codex / GPT-5.6
  │  stdio MCP：8 个高级任务工具
  ▼
codex-hermes-worker
  ├─ 本地 Web Console（127.0.0.1:8765）
  │    健康状态、任务提交、队列、结果和显式授权入口
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

## 1.1.0 控制台

控制台是 Bridge 的本地浏览器界面，不是独立远程服务。它直接复用同一套
Pydantic Schema、文件系统策略、JobManager 和 SQLite 数据库。UI 进程使用
`recover_interrupted=False` 创建执行器，避免在 Codex MCP 仍处理任务时把它
误判成中断 Job。

HTTP 服务只允许回环地址绑定。页面启动时生成随机请求令牌，API 同时校验
Host、Origin、Content-Type 和 64 KiB 请求体上限，并返回 CSP、禁止嵌入及
禁止缓存响应头。`trusted_full` 仍由后端验证固定授权值和额外风险确认，不能
仅靠前端复选框绕过。
