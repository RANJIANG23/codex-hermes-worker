from __future__ import annotations

import argparse
import json
import sys

from codex_hermes_worker.bridge.runtime import get_runtime
from codex_hermes_worker.bridge.schemas import TaskRequest


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the local Codex/Hermes worker.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    test = sub.add_parser("live-tool-test")
    test.add_argument("--instructions", default="Find the bridge readiness marker in the evidence file.")
    args = parser.parse_args()
    runtime = get_runtime()
    if args.command == "health":
        result = runtime.hermes.health()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit(1)
        return
    request = TaskRequest(
        task_type="qwen_tool_test",
        instructions=args.instructions,
        input_paths=["testdata/tool_loop/evidence.txt"],
        profile="verification_worker",
        output_schema="tool_chain_v1",
        max_steps=8,
    )
    result = runtime.manager.run_sync(request)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
