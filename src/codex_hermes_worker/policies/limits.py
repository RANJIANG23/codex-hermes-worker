from __future__ import annotations


def truncate_text(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    marker = "\n...[truncated by bridge]..."
    return value[: max(0, limit - len(marker))] + marker, True


def bounded_limit(requested: int | None, default: int, maximum: int) -> int:
    if requested is None:
        return default
    return max(1, min(int(requested), maximum))

