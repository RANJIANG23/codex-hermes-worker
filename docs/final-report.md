# 最终交付报告

正式版本：1.0.0

核验日期：2026-07-30（Asia/Shanghai）

## 总结

第一版完整分层调用链已经实现并在本机实测：

```text
Codex GPT-5.6 Sol
→ hermes_worker stdio MCP
→ Python Bridge
→ Hermes Agent 0.19.0
→ LM Studio
→ qwen3.6-27b
→ 受限工具或显式授权的 Hermes 完整工具
```

系统同时保留原始需求的安全批处理模式，并根据后续要求增加可复用的 `trusted_full` 模式。

## 逐项结论

1. **完整调用链：已实现。** Codex、Bridge、Hermes、Qwen 和本地工具均有运行证据。
2. **Codex 识别 Bridge：成功。** `codex mcp get hermes_worker` 显示 enabled；GPT-5.6 Sol 通过 `codex exec` 实际调用 `hermes_health` 并获得 `ok=true`。
3. **Bridge 调用 Hermes：成功。** 正式路径为 `hermes chat -q -Q --max-turns`。
4. **Hermes 调用本地 Qwen：成功。** LM Studio 实际模型 `qwen3.6-27b`。
5. **Qwen 使用至少两个工具：成功。** 受限链调用 `list_workspace_files` 和 `read_text_excerpt`；完整链调用 terminal 后再调用两次 `read_file`。
6. **状态与结果持久化：成功。** SQLite、WAL、事务、Job Event、JSONL、review manifest、取消和重启恢复均已实现。
7. **安全测试：默认模式通过。** 越界读写、未授权工具、步骤上限、输出截断、超时协议、密钥扫描和恢复测试通过。`trusted_full` 明确不是沙箱，这是已接受的能力边界。
8. **当前可用：** 资产分类、音频 Profile、反编译初筛、独立复核、批任务、摘要查询、完整结果导出、受限多工具 Agent、主机 terminal/file/code/browser 等 Hermes 工具路由。
9. **降级实现：** 反编译数据使用模拟结构化函数记录；Windows 无内核级出站隔离；Hermes CLI 代替专用 Agent REST API；完整模式暂为同步高层任务。
10. **本机无法完成：** 未安装 Ghidra/radare2/Rizin/ExifTool/TrID/DIE；computer_use、外部 Web 搜索、X、Home Assistant、Spotify、图像/视频生成缺少系统依赖或独立凭据。
11. **用户第一条命令：**

```powershell
cd '<project-root>'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\status.ps1
```

12. **Codex 第一条正式委派：** 使用本报告末尾的受限任务示例。

## 验收证据

### Qwen 能力

- 自动能力测试：12/12 通过。
- 两并发请求：parallel=2，墙钟约 2.67 秒。
- LM Studio 当前模型：Q8_K_XL，约 36.70 GB，parallel=4。
- LM Studio 的未知 model ID 可能仍返回 200 并回退到已加载模型；Bridge 通过 `/models` 精确检查避免误判。

### 项目测试

- 离线测试：21 passed，3 个 live 用例按预期 skipped。
- 用户入口 `scripts/test.ps1`：离线 21 passed；live 3 passed；随后真实批处理工具 Job completed。
- live restricted：Qwen 调用两个 `codex_worker_tools`，通过。
- live trusted：Qwen 调用 terminal + file，且终端看不到三个推理密钥变量，通过。
- live MCP trusted：stdio MCP → Bridge → Hermes → Qwen → terminal，通过。
- MCP health：握手、8 个工具、实际 `hermes_health` 调用，通过。
- Codex model-driven：GPT-5.6 Sol 实际调用 `hermes_worker/hermes_health`，通过。

### 批处理

资产分类 Job `779351a5-40f4-49d4-970d-2968624c707d`：

- 20/20 完成，失败 0。
- 高置信度 19，低置信度 1，需复核 2。

反编译初筛 Job `17096685-47ad-46fa-924d-7c707d642044`：

- 10/10 完成，失败 0。
- 高置信度 6，低置信度 3，需复核 4。

最新双受限工具 Job `def0a63e-ced6-495f-b7fc-e4dc22a70062`：

- completed，processed=1，failed=0。

早期失败任务保留在 SQLite 中作为真实调试证据，没有伪装或删除。

### 恢复与摘要隔离

- 遗留 `running` Job 重启后明确标为 failed，错误说明 partial results retained。
- 已提交分类记录不回滚丢失。
- MCP 摘要不含原始记录。
- MCP 单次查询最多 100 条；全量 JSONL 导出已单独测试 125 条，不受查询上限截断。

### 安装与回滚

- `install.ps1` 连续运行两次成功，用户配置中项目 trust 段仍只有 1 个。
- `start.ps1`、`status.ps1`、`stop.ps1` 实测通过。
- `uninstall.ps1 -WhatIf` 正确列出：项目 trust、`.venv`、项目 MCP 配置；没有用户数据或外部目录。
- Codex 用户配置首份备份：`work/backups/config.toml.20260730-010949.bak`。

## 安全说明

`restricted_batch` 是默认且适合不可信输入的模式。`trusted_full`：

- 要求 `authorization="explicit_user_authorized"`。
- 网络/可选服务要求 `allow_network=true`。
- 使用独立 Hermes Home、步数/超时/输出限制、任务摘要审计和 Hermes checkpoints。
- 主机 terminal 使用非交互 `--yolo`，不是强隔离；绝不能因为受限模式“不方便”而自动升级。
- checkpoints 不保证撤销任意终端命令对外部系统造成的影响。

## 团队复用

源码、Profiles、Schemas、测试和安装器可共享。每位成员必须在本机重新运行安装器，生成自己的 `.venv` 和 `.codex/config.toml`；不得共享密钥、`work`、SQLite 或 Hermes Profile。当前 stdio 拓扑不开放网络端口，适合“每人自己的 Codex 驱动自己的本地算力”。

## 第一条正式任务示例

```text
请先调用 hermes_health 检查本地工作代理。

然后将 testdata/assets.jsonl 交给本地 Hermes/Qwen：
1. 调用 submit_local_job，使用 asset_classification、asset_worker 和
   asset_classification_v1；
2. 使用确定性工具提取或核对元数据；
3. 按模型、纹理、动画、音频、脚本、配置和未知文件分类；
4. 每项给出置信度和证据；
5. 只向主代理返回聚合摘要、冲突项和低置信度项目；
6. 原始结果写入本地 SQLite 和 JSONL；
7. 不修改任何输入文件；
8. 未经我另外明确授权，不要调用 trusted_full。
```
