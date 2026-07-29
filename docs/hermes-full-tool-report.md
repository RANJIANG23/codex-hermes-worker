# Hermes 完整工具模式报告

## 目的

`trusted_full` 让 Codex 能把通用电脑任务交给 Hermes/Qwen，而不仅限于批量分类。它不会让 Hermes 继承 Codex 专属插件或连接器；它使用 Hermes 自己的工具和本项目 MCP。

## 已启用的工具集

terminal、file、code_execution、vision、skills、todo、memory、context_engine、session_search、clarify、delegation、cronjob、computer_use、web、browser、x_search、video、image_gen、video_gen、tts、stt、homeassistant、spotify、yuanbao、codex_worker_tools。

## 实测

- `hermes tools list --platform cli`：上述 24 类全部 enabled。
- `hermes doctor`：terminal、file、code_execution、browser、skills、memory、delegation、cronjob、todo、tts 等当前可用。
- 直接 Bridge 测试：Qwen 调用 terminal 创建项目内文件，然后用 `read_file` 读取两个文件，完成 3 次模型调用。
- MCP 测试：`delegate_trusted_full_task` 经 stdio MCP 调用，Qwen 实际执行 terminal，测试通过。
- 密钥隔离：实际 terminal 子进程中 `LMSTUDIO_API_KEY`、`OPENAI_API_KEY`、`OPENROUTER_API_KEY` 均为不存在。

## 当前不可用项

computer_use、CDP 浏览器、外部 Web 搜索、X 搜索、Home Assistant、Spotify、Yuanbao、vision/image/video generation 需要额外系统依赖或各自凭据。普通 agent-browser 已可用。不得把“配置启用”描述为“所有第三方服务均已配置”。

## 调用安全合同

```json
{
  "authorization": "explicit_user_authorized",
  "allow_network": false,
  "include_optional_tools": false
}
```

- 主机 terminal 在该模式下使用 `--yolo`，以支持非交互执行。
- `--checkpoints` 已启用，但不能保证恢复终端命令造成的所有外部修改。
- 工作目录必须位于 `trusted_full.working_roots`；默认是项目父工作区。
- network/optional 工具必须同时设置 `allow_network=true`。
- 高层任务开始、完成或失败会写入 `work/logs/trusted-full-audit.jsonl`，只记录提示词 SHA-256，不记录提示词正文或密钥。
