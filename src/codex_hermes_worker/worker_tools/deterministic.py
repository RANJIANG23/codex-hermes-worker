from __future__ import annotations

import hashlib
import json
import math
import mimetypes
import re
import subprocess
from collections import Counter
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from codex_hermes_worker.bridge.config import AppConfig
from codex_hermes_worker.policies.filesystem import FilesystemPolicy


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    total = len(data)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def file_metadata(policy: FilesystemPolicy, value: str) -> dict[str, Any]:
    path = policy.resolve_read(value)
    stat = path.stat()
    head = path.read_bytes()[:4096]
    return {
        "path": policy.relative_display(path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "extension": path.suffix.lower(),
        "mime_guess": mimetypes.guess_type(path.name)[0],
        "magic_hex": head[:16].hex(),
        "entropy_first_4k": round(entropy(head), 4),
        "sha256": sha256_file(path),
    }


def text_excerpt(
    policy: FilesystemPolicy,
    value: str,
    max_chars: int,
    offset_chars: int = 0,
) -> dict[str, Any]:
    if offset_chars < 0:
        raise ValueError("offset_chars must be >= 0")
    path = policy.resolve_read(value)
    limit = min(max_chars, policy.config.filesystem.maximum_text_chars)
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    excerpt = text[offset_chars : offset_chars + limit]
    next_offset = offset_chars + len(excerpt)
    return {
        "path": policy.relative_display(path),
        "text": excerpt,
        "offset_chars": offset_chars,
        "next_offset_chars": next_offset,
        "truncated": next_offset < len(text),
        "characters_read": len(excerpt),
        "total_characters": len(text),
    }


def binary_slice(
    policy: FilesystemPolicy, value: str, offset: int, length: int
) -> dict[str, Any]:
    if offset < 0 or length < 1:
        raise ValueError("offset must be >= 0 and length must be >= 1")
    length = min(length, policy.config.filesystem.maximum_binary_slice)
    path = policy.resolve_read(value)
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(length)
    return {
        "path": policy.relative_display(path),
        "offset": offset,
        "length": len(data),
        "hex": data.hex(),
    }


def printable_strings(policy: FilesystemPolicy, value: str, limit: int = 100) -> dict[str, Any]:
    path = policy.resolve_read(value)
    data = path.read_bytes()
    matches = [m.decode("ascii", errors="replace") for m in re.findall(rb"[\x20-\x7e]{4,}", data)]
    return {
        "path": policy.relative_display(path),
        "strings": matches[: min(limit, 500)],
        "truncated": len(matches) > min(limit, 500),
    }


def search_file_names(
    policy: FilesystemPolicy, root_value: str, query: str, limit: int = 100
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query cannot be empty")
    root = policy.resolve_read(root_value)
    if not root.is_dir():
        raise NotADirectoryError(root)
    cap = max(1, min(limit, 500))
    needle = query.casefold()
    uses_glob = any(character in query for character in "*?[]")
    matches: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        name = path.name.casefold()
        matched = fnmatch(name, needle) if uses_glob else needle in name
        if path.is_file() and matched:
            matches.append(
                {
                    "path": policy.relative_display(path),
                    "size": path.stat().st_size,
                    "extension": path.suffix.lower(),
                }
            )
            if len(matches) >= cap:
                break
    return {"matches": matches, "limit": cap, "truncated": len(matches) >= cap}


def search_text(
    policy: FilesystemPolicy, root_value: str, query: str, limit: int = 100
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query cannot be empty")
    root = policy.resolve_read(root_value)
    cap = max(1, min(limit, 500))
    needle = query.casefold()
    matches: list[dict[str, Any]] = []
    if root.is_file():
        paths = [root]
    elif root.is_dir():
        paths = sorted(root.rglob("*"))
    else:
        raise FileNotFoundError(root)
    for path in paths:
        if not path.is_file():
            continue
        if path.stat().st_size > policy.config.filesystem.maximum_input_file_size:
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if needle in line.casefold():
                matches.append(
                    {
                        "path": policy.relative_display(path),
                        "line": line_number,
                        "excerpt": line[:300],
                    }
                )
                if len(matches) >= cap:
                    return {"matches": matches, "limit": cap, "truncated": True}
    return {"matches": matches, "limit": cap, "truncated": False}


def ffprobe_metadata(config: AppConfig, policy: FilesystemPolicy, value: str) -> dict[str, Any]:
    path = policy.resolve_read(value)
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,format_name,size:stream=codec_name,codec_type,sample_rate,channels,width,height",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr[:1000] or "ffprobe failed")
    return json.loads(completed.stdout)
