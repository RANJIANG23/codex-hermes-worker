from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_hermes_worker.bridge.config import AppConfig


_LOCK = threading.Lock()


def rotate_audit_log(path: Path, max_bytes: int) -> None:
    if not path.exists() or path.stat().st_size < max_bytes:
        return
    rotated = path.with_suffix(path.suffix + ".1")
    if rotated.exists():
        rotated.unlink()
    path.replace(rotated)


def append_audit(config: AppConfig, tool: str, arguments: dict[str, Any], status: str) -> None:
    path = config.project_root / "work" / "logs" / "tool-audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_args = {
        key: ("<redacted>" if any(x in key.lower() for x in ("key", "token", "secret")) else value)
        for key, value in arguments.items()
    }
    row = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "arguments": safe_args,
        "status": status,
    }
    with _LOCK:
        rotate_audit_log(path, config.bridge.audit_log_max_bytes)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
