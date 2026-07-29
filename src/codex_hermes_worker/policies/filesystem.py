from __future__ import annotations

import os
from pathlib import Path

from codex_hermes_worker.bridge.config import AppConfig


class PolicyViolation(PermissionError):
    """Raised when a path crosses an enforced filesystem boundary."""


def _is_within(path: Path, roots: list[Path]) -> bool:
    resolved = path.resolve(strict=False)
    for root in roots:
        try:
            if os.path.commonpath([str(resolved), str(root.resolve())]) == str(root.resolve()):
                return True
        except ValueError:
            continue
    return False


class FilesystemPolicy:
    def __init__(self, config: AppConfig):
        self.config = config

    def resolve_read(self, value: str | Path, *, must_exist: bool = True) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.config.project_root / path
        path = path.resolve(strict=False)
        if not _is_within(path, self.config.filesystem.readable_roots):
            raise PolicyViolation(f"read denied outside configured roots: {value}")
        if must_exist and not path.exists():
            raise FileNotFoundError(path)
        if path.is_file() and path.stat().st_size > self.config.filesystem.maximum_input_file_size:
            raise PolicyViolation(
                f"input exceeds {self.config.filesystem.maximum_input_file_size} bytes: {value}"
            )
        return path

    def resolve_write(self, value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.config.project_root / path
        path = path.resolve(strict=False)
        if not _is_within(path, self.config.filesystem.writable_roots):
            raise PolicyViolation(f"write denied outside configured roots: {value}")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def relative_display(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.config.project_root).as_posix()
        except ValueError:
            return str(path.resolve())

