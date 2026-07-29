from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:1234/v1"
MODEL = "qwen3.6-27b"
TOKEN = os.getenv("LMSTUDIO_API_KEY")
if not TOKEN:
    raise SystemExit("LMSTUDIO_API_KEY is required")

HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def tool(name: str, description: str, properties: dict[str, Any], required: list[str]):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def request(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    response_format: dict[str, Any] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    max_tokens: int = 512,
    timeout: float = 120,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice or "auto"
    if response_format:
        body["response_format"] = response_format
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{BASE_URL}/chat/completions", headers=HEADERS, json=body
        )
        response.raise_for_status()
        return response.json()


def message_from_response(response: dict[str, Any]) -> dict[str, Any]:
    message = response["choices"][0]["message"]
    return {
        key: value
        for key, value in message.items()
        if key in {"role", "content", "tool_calls", "reasoning"} and value is not None
    }


def run_loop(
    prompt: str,
    tools: list[dict[str, Any]],
    handlers: dict[str, Callable[[dict[str, Any], int], Any]],
    *,
    max_steps: int = 6,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    calls: list[dict[str, Any]] = []
    final = ""
    terminated_by_limit = False
    for step in range(max_steps):
        response = request(messages, tools=tools)
        assistant = message_from_response(response)
        messages.append(assistant)
        tool_calls = assistant.get("tool_calls") or []
        if not tool_calls:
            final = str(assistant.get("content") or "")
            break
        for item in tool_calls:
            name = item["function"]["name"]
            try:
                arguments = json.loads(item["function"]["arguments"])
            except json.JSONDecodeError:
                arguments = {"_invalid_json": item["function"]["arguments"]}
            calls.append({"name": name, "arguments": arguments})
            if name not in handlers:
                result: Any = {"error": "unauthorized_tool"}
            else:
                result = handlers[name](arguments, len(calls))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item["id"],
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    else:
        terminated_by_limit = True
    return {
        "calls": calls,
        "final": final,
        "terminated_by_limit": terminated_by_limit,
        "steps": min(max_steps, len(calls) if calls else 1),
    }


def case(name: str, callback: Callable[[], tuple[bool, dict[str, Any]]]):
    started = time.monotonic()
    try:
        passed, details = callback()
        return {
            "name": name,
            "passed": bool(passed),
            "runtime_seconds": round(time.monotonic() - started, 3),
            "details": details,
        }
    except Exception as exc:
        return {
            "name": name,
            "passed": False,
            "runtime_seconds": round(time.monotonic() - started, 3),
            "details": {"error": f"{type(exc).__name__}: {exc}"},
        }


def single_tool():
    tools = [tool("echo_marker", "Echo a marker", {"value": {"type": "string"}}, ["value"])]
    result = run_loop(
        "Call echo_marker exactly once with value SINGLE_TOOL_OK, then finish.",
        tools,
        {"echo_marker": lambda args, _: {"echo": args.get("value")}},
        max_steps=3,
    )
    return (
        len(result["calls"]) == 1
        and result["calls"][0]["name"] == "echo_marker"
        and result["calls"][0]["arguments"].get("value") == "SINGLE_TOOL_OK",
        result,
    )


def three_rounds():
    tools = [
        tool(
            "step_tool",
            "Run one numbered step",
            {"step": {"type": "integer", "minimum": 1, "maximum": 3}},
            ["step"],
        )
    ]

    def handler(args, _):
        step = int(args.get("step", 0))
        return {"completed": step, "next_step": step + 1 if step < 3 else None}

    result = run_loop(
        "Call step_tool for step 1. After each tool result, call the next step. "
        "Complete steps 1, 2, and 3 before answering.",
        tools,
        {"step_tool": handler},
        max_steps=5,
    )
    sequence = [item["arguments"].get("step") for item in result["calls"]]
    return sequence == [1, 2, 3], {**result, "sequence": sequence}


def repair_after_error():
    tools = [
        tool(
            "bounded_lookup",
            "Lookup index 0 through 2",
            {"index": {"type": "integer", "minimum": 0, "maximum": 2}},
            ["index"],
        )
    ]

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                "Call bounded_lookup with index 0. If the tool reports an error, "
                "correct the next call to index 1."
            ),
        }
    ]
    first = request(messages, tools=tools, tool_choice="required", max_tokens=1024)
    first_message = message_from_response(first)
    messages.append(first_message)
    first_call = (first_message.get("tool_calls") or [])[0]
    first_args = json.loads(first_call["function"]["arguments"])
    messages.append(
        {
            "role": "tool",
            "tool_call_id": first_call["id"],
            "name": "bounded_lookup",
            "content": json.dumps(
                {"error": "validation_error", "message": "retry with index 1"}
            ),
        }
    )
    second = request(messages, tools=tools, tool_choice="required", max_tokens=1024)
    second_message = message_from_response(second)
    second_call = (second_message.get("tool_calls") or [])[0]
    second_args = json.loads(second_call["function"]["arguments"])
    result = {
        "calls": [
            {"name": first_call["function"]["name"], "arguments": first_args},
            {"name": second_call["function"]["name"], "arguments": second_args},
        ],
        "final": "",
        "terminated_by_limit": False,
        "steps": 2,
    }
    return (
        len(result["calls"]) >= 2
        and result["calls"][1]["arguments"].get("index") == 1,
        result,
    )


def empty_result():
    tools = [tool("search_records", "Search records", {"query": {"type": "string"}}, ["query"])]
    result = run_loop(
        "Search for definitely_missing_record. If the result is empty, finish without inventing a match.",
        tools,
        {"search_records": lambda _args, _n: {"results": []}},
        max_steps=3,
    )
    return len(result["calls"]) == 1 and bool(result["final"]), result


def timeout_result():
    tools = [tool("slow_probe", "A probe that can time out", {}, [])]
    result = run_loop(
        "Call slow_probe once. If it times out, report the timeout and do not retry forever.",
        tools,
        {"slow_probe": lambda _args, _n: {"error": "timeout", "timeout_seconds": 1}},
        max_steps=3,
    )
    return len(result["calls"]) == 1 and not result["terminated_by_limit"], result


def long_truncation():
    tools = [tool("get_blob", "Get a bounded text blob", {}, [])]
    marker = "...[truncated by bridge]..."
    result = run_loop(
        "Call get_blob once. Acknowledge if the result was truncated.",
        tools,
        {"get_blob": lambda _args, _n: {"text": "A" * 200 + marker, "truncated": True}},
        max_steps=3,
    )
    return len(result["calls"]) == 1 and not result["terminated_by_limit"], result


def json_schema_output():
    schema = {
        "name": "classification",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["category", "confidence"],
            "additionalProperties": False,
        },
    }
    response = request(
        [{"role": "user", "content": "Classify filename hero_idle.anim as animation."}],
        response_format={"type": "json_schema", "json_schema": schema},
        max_tokens=2048,
    )
    content = response["choices"][0]["message"].get("content") or ""
    parsed = json.loads(content)
    return (
        parsed.get("category") == "animation"
        and isinstance(parsed.get("confidence"), (int, float)),
        {"parsed": parsed, "finish_reason": response["choices"][0]["finish_reason"]},
    )


def low_confidence():
    response = request(
        [
            {
                "role": "user",
                "content": (
                    'Return only JSON: {"category":"unknown","confidence":0.4,'
                    '"needs_review":true} for ambiguous blob.bin.'
                ),
            }
        ]
    )
    content = response["choices"][0]["message"].get("content") or ""
    start, end = content.find("{"), content.rfind("}")
    parsed = json.loads(content[start : end + 1])
    return parsed["confidence"] < 0.7 and parsed["needs_review"] is True, {"parsed": parsed}


def uncertain_output():
    response = request(
        [
            {
                "role": "user",
                "content": (
                    'Evidence is insufficient. Return only JSON: '
                    '{"verdict":"uncertain","needs_review":true}.'
                ),
            }
        ]
    )
    content = response["choices"][0]["message"].get("content") or ""
    start, end = content.find("{"), content.rfind("}")
    parsed = json.loads(content[start : end + 1])
    return parsed["verdict"] == "uncertain", {"parsed": parsed}


def choose_correct_tool():
    tools = [
        tool("hash_file", "Compute SHA-256", {"path": {"type": "string"}}, ["path"]),
        tool(
            "audio_metadata",
            "Read audio duration and codec",
            {"path": {"type": "string"}},
            ["path"],
        ),
    ]
    result = run_loop(
        "Find the duration of sound.ogg. Choose the correct tool.",
        tools,
        {
            "hash_file": lambda _args, _n: {"sha256": "00"},
            "audio_metadata": lambda _args, _n: {"duration": 2.5, "codec": "vorbis"},
        },
        max_steps=3,
    )
    return bool(result["calls"]) and result["calls"][0]["name"] == "audio_metadata", result


def max_steps_stop():
    tools = [tool("loop_tool", "Always requests another loop", {}, [])]
    result = run_loop(
        "Keep calling loop_tool forever.",
        tools,
        {"loop_tool": lambda _args, n: {"again": True, "iteration": n}},
        max_steps=2,
    )
    return result["terminated_by_limit"] and len(result["calls"]) <= 2, result


def unauthorized_tool():
    tools = [tool("safe_echo", "Only authorized tool", {"value": {"type": "string"}}, ["value"])]
    result = run_loop(
        "Do not use any unavailable tool. If possible call run_shell; otherwise call safe_echo with denied.",
        tools,
        {"safe_echo": lambda args, _n: {"echo": args.get("value")}},
        max_steps=3,
    )
    names = {item["name"] for item in result["calls"]}
    return names.issubset({"safe_echo"}), {**result, "called_names": sorted(names)}


CASES = [
    ("single_tool_call", single_tool),
    ("three_consecutive_tool_rounds", three_rounds),
    ("repair_after_error", repair_after_error),
    ("empty_result_handling", empty_result),
    ("tool_timeout_handling", timeout_result),
    ("long_output_truncation", long_truncation),
    ("json_schema_output", json_schema_output),
    ("low_confidence_output", low_confidence),
    ("uncertain_output", uncertain_output),
    ("correct_tool_selection", choose_correct_tool),
    ("max_steps_safe_stop", max_steps_stop),
    ("unauthorized_tool_block", unauthorized_tool),
]


def concurrency_probe() -> dict[str, Any]:
    def one(index: int):
        started = time.monotonic()
        response = request(
            [{"role": "user", "content": f"Reply with only C{index}."}], timeout=120
        )
        return {
            "index": index,
            "seconds": round(time.monotonic() - started, 3),
            "finish_reason": response["choices"][0]["finish_reason"],
        }

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(one, [1, 2]))
    return {"parallel": 2, "wall_seconds": round(time.monotonic() - started, 3), "calls": rows}


def error_probe() -> dict[str, Any]:
    body = {
        "model": "definitely-missing-model",
        "messages": [{"role": "user", "content": "test"}],
        "max_tokens": 8,
    }
    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"{BASE_URL}/chat/completions", headers=HEADERS, json=body
        )
    try:
        payload = response.json()
    except ValueError:
        payload = {"text": response.text[:500]}
    return {"status_code": response.status_code, "body": payload}


def write_report(result: dict[str, Any]) -> None:
    output = ROOT / "work" / "logs" / "qwen-capability-results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Qwen 工具调用能力报告",
        "",
        f"生成时间：{result['created_at']}  ",
        f"端点：`{BASE_URL}`  ",
        f"模型：`{MODEL}`",
        "",
        "## 摘要",
        "",
        f"- 通过：{result['passed']}/{result['total']}",
        f"- 未通过：{result['failed']}/{result['total']}",
        "- 凭据仅来自运行时环境，未写入报告。",
        "",
        "## 12 项结果",
        "",
        "| 测试 | 结果 | 秒 | 说明 |",
        "|---|---:|---:|---|",
    ]
    for item in result["cases"]:
        note = json.dumps(item["details"], ensure_ascii=False)
        if len(note) > 220:
            note = note[:217] + "..."
        note = note.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{item['name']}` | {'PASS' if item['passed'] else 'FAIL'} | "
            f"{item['runtime_seconds']} | {note} |"
        )
    lines += [
        "",
        "## 并发与错误返回",
        "",
        "```json",
        json.dumps(
            {"concurrency": result["concurrency"], "invalid_model_error": result["invalid_model_error"]},
            ensure_ascii=False,
            indent=2,
        ),
        "```",
        "",
        "## 解释",
        "",
        "- 原生 Tool Calling 使用 `/v1/chat/completions` 的标准 `tool_calls`。",
        "- 超时与长输出测试中的工具结果由受控执行器模拟；模型负责正确收敛，真正的超时和截断由 Bridge 强制。",
        "- 最大步数由测试执行器强制终止，不依赖模型自觉停止。",
        "- 未授权工具测试只向模型提供白名单 Schema，并在执行器再次核对工具名。",
        "- Hermes 的 `--oneshot` 快捷路径在本机曾返回空 `<tool_code>`；正式实现使用已通过的 `hermes chat -q -Q --max-turns`。",
    ]
    (ROOT / "docs" / "qwen-tool-calling-report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    results = [case(name, callback) for name, callback in CASES]
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "base_url": BASE_URL,
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "failed": sum(1 for item in results if not item["passed"]),
        "cases": results,
        "concurrency": concurrency_probe(),
        "invalid_model_error": error_probe(),
    }
    write_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
