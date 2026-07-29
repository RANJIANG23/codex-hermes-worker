# Qwen 工具调用能力报告

生成时间：2026-07-29T17:30:41.511608+00:00  
端点：`http://127.0.0.1:1234/v1`  
模型：`qwen3.6-27b`

## 摘要

- 通过：12/12
- 未通过：0/12
- 凭据仅来自运行时环境，未写入报告。

## 12 项结果

| 测试 | 结果 | 秒 | 说明 |
|---|---:|---:|---|
| `single_tool_call` | PASS | 4.25 | {"calls": [{"name": "echo_marker", "arguments": {"value": "SINGLE_TOOL_OK"}}], "final": "Done.", "terminated_by_limit": false, "steps": 1} |
| `three_consecutive_tool_rounds` | PASS | 7.875 | {"calls": [{"name": "step_tool", "arguments": {"step": 1}}, {"name": "step_tool", "arguments": {"step": 2}}, {"name": "step_tool", "arguments": {"step": 3}}], "final": "All steps (1, 2, and 3) have been successfully c... |
| `repair_after_error` | PASS | 4.89 | {"calls": [{"name": "bounded_lookup", "arguments": {"index": 0}}, {"name": "bounded_lookup", "arguments": {"index": 1}}], "final": "", "terminated_by_limit": false, "steps": 2} |
| `empty_result_handling` | PASS | 4.25 | {"calls": [{"name": "search_records", "arguments": {"query": "definitely_missing_record"}}], "final": "No records found for \"definitely_missing_record\".", "terminated_by_limit": false, "steps": 1} |
| `tool_timeout_handling` | PASS | 3.094 | {"calls": [{"name": "slow_probe", "arguments": {}}], "final": "The `slow_probe` call timed out after 1 second. As requested, I will not retry.", "terminated_by_limit": false, "steps": 1} |
| `long_output_truncation` | PASS | 4.703 | {"calls": [{"name": "get_blob", "arguments": {}}], "final": "The result from `get_blob` was truncated.", "terminated_by_limit": false, "steps": 1} |
| `json_schema_output` | PASS | 10.25 | {"parsed": {"category": "animation", "confidence": 0.98}, "finish_reason": "stop"} |
| `low_confidence_output` | PASS | 5.266 | {"parsed": {"category": "unknown", "confidence": 0.4, "needs_review": true}} |
| `uncertain_output` | PASS | 4.515 | {"parsed": {"verdict": "uncertain", "needs_review": true}} |
| `correct_tool_selection` | PASS | 3.657 | {"calls": [{"name": "audio_metadata", "arguments": {"path": "sound.ogg"}}], "final": "The duration of sound.ogg is 2.5 seconds.", "terminated_by_limit": false, "steps": 1} |
| `max_steps_safe_stop` | PASS | 5.234 | {"calls": [{"name": "loop_tool", "arguments": {}}, {"name": "loop_tool", "arguments": {}}], "final": "", "terminated_by_limit": true, "steps": 2} |
| `unauthorized_tool_block` | PASS | 12.578 | {"calls": [{"name": "safe_echo", "arguments": {"value": "denied"}}], "final": "", "terminated_by_limit": false, "steps": 1, "called_names": ["safe_echo"]} |

## 并发与错误返回

```json
{
  "concurrency": {
    "parallel": 2,
    "wall_seconds": 2.672,
    "calls": [
      {
        "index": 1,
        "seconds": 2.672,
        "finish_reason": "stop"
      },
      {
        "index": 2,
        "seconds": 2.672,
        "finish_reason": "stop"
      }
    ]
  },
  "invalid_model_error": {
    "status_code": 200,
    "body": {
      "id": "chatcmpl-teb3t31xlzfnzaheaxs1ss",
      "object": "chat.completion",
      "created": 1785346244,
      "model": "unsloth/qwen3.6-27b-gguf/qwen3.6-27b-ud-mtp-q8_k_xl.gguf",
      "choices": [
        {
          "index": 0,
          "message": {
            "role": "assistant",
            "content": "",
            "reasoning_content": "Here's a thinking process:\n\n1",
            "tool_calls": []
          },
          "logprobs": null,
          "finish_reason": "length"
        }
      ],
      "usage": {
        "prompt_tokens": 11,
        "completion_tokens": 8,
        "total_tokens": 19,
        "completion_tokens_details": {
          "reasoning_tokens": 8
        }
      },
      "stats": {
        "total_draft_tokens_count": 4,
        "accepted_draft_tokens_count": 4,
        "rejected_draft_tokens_count": 0
      },
      "system_fingerprint": "unsloth/qwen3.6-27b-gguf/qwen3.6-27b-ud-mtp-q8_k_xl.gguf"
    }
  }
}
```

## 解释

- 原生 Tool Calling 使用 `/v1/chat/completions` 的标准 `tool_calls`。
- 超时与长输出测试中的工具结果由受控执行器模拟；模型负责正确收敛，真正的超时和截断由 Bridge 强制。
- 最大步数由测试执行器强制终止，不依赖模型自觉停止。
- 未授权工具测试只向模型提供白名单 Schema，并在执行器再次核对工具名。
- Hermes 的 `--oneshot` 快捷路径在本机曾返回空 `<tool_code>`；正式实现使用已通过的 `hermes chat -q -Q --max-turns`。
