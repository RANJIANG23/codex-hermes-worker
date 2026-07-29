from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class BridgeSettings(BaseModel):
    name: str = "codex-hermes-worker"
    sync_timeout_seconds: int = Field(180, ge=1, le=3600)
    max_query_limit: int = Field(100, ge=1, le=1000)
    default_query_limit: int = Field(20, ge=1, le=100)
    max_tool_output_chars: int = Field(30000, ge=1000, le=200000)
    audit_log_max_bytes: int = Field(5242880, ge=65536, le=104857600)


class HermesSettings(BaseModel):
    executable: str = "auto"
    home: Path = Path("work/hermes-profile")
    base_url: str = "http://127.0.0.1:1234/v1"
    api_key_env: str = "LMSTUDIO_API_KEY"
    provider: str = "openrouter"
    model: str = "qwen3.6-27b"
    max_steps: int = Field(12, ge=1, le=50)
    max_runtime_seconds: int = Field(600, ge=5, le=3600)
    max_output_chars: int = Field(30000, ge=1000, le=200000)
    context_length: int = Field(65536, ge=8192, le=262144)


class FilesystemSettings(BaseModel):
    readable_roots: list[Path]
    writable_roots: list[Path]
    maximum_input_file_size: int = Field(10485760, ge=1)
    maximum_text_chars: int = Field(30000, ge=256, le=1000000)
    maximum_binary_slice: int = Field(65536, ge=1, le=1048576)


class AgentSettings(BaseModel):
    allow_network: bool = False
    allow_unrestricted_shell: bool = False
    max_steps: int = Field(12, ge=1, le=50)
    max_tool_calls: int = Field(30, ge=1, le=100)
    max_runtime_seconds: int = Field(600, ge=5, le=3600)


class TrustedFullSettings(BaseModel):
    enabled: bool = True
    home: Path = Path("work/hermes-profile-trusted")
    required_authorization: str = Field(
        "explicit_user_authorized", min_length=8, max_length=128
    )
    working_roots: list[Path] = Field(default_factory=lambda: [Path("..")])
    local_toolsets: list[str] = Field(
        default_factory=lambda: [
            "terminal",
            "file",
            "code_execution",
            "vision",
            "skills",
            "todo",
            "memory",
            "context_engine",
            "session_search",
            "clarify",
            "delegation",
            "cronjob",
            "computer_use",
            "codex_worker_tools",
        ]
    )
    network_toolsets: list[str] = Field(
        default_factory=lambda: ["web", "browser", "x_search"]
    )
    optional_toolsets: list[str] = Field(
        default_factory=lambda: [
            "video",
            "image_gen",
            "video_gen",
            "tts",
            "stt",
            "homeassistant",
            "spotify",
            "yuanbao",
        ]
    )
    max_steps: int = Field(30, ge=1, le=50)
    max_runtime_seconds: int = Field(1800, ge=5, le=3600)
    max_output_chars: int = Field(60000, ge=1000, le=200000)
    checkpoints: bool = True

    @property
    def all_toolsets(self) -> list[str]:
        return list(
            dict.fromkeys(
                self.local_toolsets + self.network_toolsets + self.optional_toolsets
            )
        )


class JobSettings(BaseModel):
    database: Path = Path("work/database/jobs.db")
    max_workers: int = Field(1, ge=1, le=4)
    result_jsonl_dir: Path = Path("work/results")
    review_dir: Path = Path("work/review")


class AppConfig(BaseModel):
    project_root: Path = PROJECT_ROOT
    bridge: BridgeSettings
    hermes: HermesSettings
    filesystem: FilesystemSettings
    agent: AgentSettings
    trusted_full: TrustedFullSettings
    jobs: JobSettings
    profiles: dict[str, Path]
    schemas: dict[str, Path]

    @model_validator(mode="after")
    def resolve_paths(self) -> "AppConfig":
        root = self.project_root.resolve()

        def absolute(path: Path) -> Path:
            return path.resolve() if path.is_absolute() else (root / path).resolve()

        self.hermes.home = absolute(self.hermes.home)
        self.trusted_full.home = absolute(self.trusted_full.home)
        self.trusted_full.working_roots = [
            absolute(path) for path in self.trusted_full.working_roots
        ]
        self.filesystem.readable_roots = [absolute(p) for p in self.filesystem.readable_roots]
        self.filesystem.writable_roots = [absolute(p) for p in self.filesystem.writable_roots]
        self.jobs.database = absolute(self.jobs.database)
        self.jobs.result_jsonl_dir = absolute(self.jobs.result_jsonl_dir)
        self.jobs.review_dir = absolute(self.jobs.review_dir)
        self.profiles = {k: absolute(v) for k, v in self.profiles.items()}
        self.schemas = {k: absolute(v) for k, v in self.schemas.items()}
        return self


def _merge(base: dict, overlay: dict) -> dict:
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(
        path or os.getenv("CODEX_HERMES_CONFIG") or PROJECT_ROOT / "config" / "default.yaml"
    ).resolve()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    local_path = PROJECT_ROOT / "config" / "local.yaml"
    if local_path.exists() and local_path.resolve() != config_path:
        raw = _merge(raw, yaml.safe_load(local_path.read_text(encoding="utf-8")) or {})
    return AppConfig(project_root=PROJECT_ROOT, **raw)


TaskType = Literal[
    "asset_classification",
    "audio_asset_classification",
    "disassembly_triage",
    "verification",
    "qwen_tool_test",
]
