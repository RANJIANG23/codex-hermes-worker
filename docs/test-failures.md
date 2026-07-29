# 测试失败与修复记录

本文件保留真实失败，不把调试过程伪装成一次通过。

## Hermes 快捷调用未返回有效工具代码

- 命令：`hermes --oneshot ...`
- 错误摘要：本机返回空 `<tool_code>`，无法证明工具执行。
- 相关日志：`work/hermes-profile/logs/agent.log`
- 修复：改用 `hermes chat -q -Q --max-turns`。
- 复测：三次模型调用、两个受限工具，成功。

## Provider 适配失败

- 尝试：`provider=openai` 和 `provider=auto`。
- 错误摘要：Hermes 当前版本不接受前者；后者没有可用 Provider。
- 修复：使用 Hermes 已支持的 `openrouter` Provider，但把 base URL 和密钥映射到本机 LM Studio。
- 复测：推理和 Tool Calling 成功；没有改变用户默认 Hermes Provider。

## 第一轮资产批处理部分失败

- Job：`251c7368-076b-4d21-bfe7-099ed8f2fe70`
- 错误摘要：17 条后，模型摘要超出 Schema 长度。
- 工件：`work/results/251c7368-076b-4d21-bfe7-099ed8f2fe70.jsonl`
- 修复：5 条一批、摘要提示收紧、按条 Schema 校验、失败条目单条修复。
- 复测：Job `779351a5-40f4-49d4-970d-2968624c707d`，20/20 完成。

## Codex 首次实际 MCP 调用被拒绝

- 命令：`codex exec ... hermes_health`
- 错误摘要：`user cancelled MCP tool call`。
- 原因：MCP 工具未声明只读语义，Codex 非交互 approval=never 不执行未知副作用工具。
- 修复：为 8 个高层工具增加 `ToolAnnotations`；health/status/query 标为 read-only，高风险完整模式标为 destructive/open-world。
- 复测：GPT-5.6 Sol 实际调用 `hermes_health`，`ok=true`。

## PowerShell 直接运行脚本被策略阻止

- 命令：`.\scripts\install.ps1`
- 错误摘要：系统执行策略禁止脚本。
- 修复：文档和验收改用 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File`。
- 边界：只影响该 PowerShell 子进程，不修改系统策略。
- 复测：安装连续执行两次成功，信任项无重复。

## Hermes 错误转储保留掩码令牌前后缀

- 发现：两个早期 `request_dump_*.json` 的 Authorization 值为部分掩码。
- 处置：删除这两个项目调试转储，并在 Bridge 中对未来请求转储执行二次 Authorization 全量替换。
- 复测：项目 key-shaped 文本扫描无命中（Hermes 自带 Skills 中的示例 `Bearer token` 除外）。
