from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import yaml

from codex_hermes_worker.bridge.config import AppConfig
from codex_hermes_worker.policies.limits import truncate_text
from codex_hermes_worker.worker_tools.audit import rotate_audit_log


class HermesUnavailable(RuntimeError):
    pass


def extract_json(text: str) -> Any:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    candidates = [fenced.group(1)] if fenced else []
    tagged = re.search(r"<json>\s*(.*?)\s*</json>", text, re.DOTALL | re.IGNORECASE)
    if tagged:
        candidates.insert(0, tagged.group(1))
    candidates.append(text)
    decoder = json.JSONDecoder()
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        for index, char in enumerate(candidate):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(candidate[index:])
                return value
            except json.JSONDecodeError:
                continue
    raise ValueError("Hermes/Qwen response did not contain valid JSON")


class HermesClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self.executable = self._find_executable()
        self._audit_lock = threading.Lock()
        self._prepare_isolated_home(self.config.hermes.home, trusted=False)
        if self.config.trusted_full.enabled:
            self._prepare_isolated_home(self.config.trusted_full.home, trusted=True)

    def _find_executable(self) -> str:
        configured = self.config.hermes.executable
        if configured != "auto":
            if not Path(configured).exists():
                raise HermesUnavailable(f"Hermes executable not found: {configured}")
            return configured
        found = shutil.which("hermes")
        if not found:
            raise HermesUnavailable("hermes executable is not on PATH")
        return found

    def _prepare_isolated_home(self, home: Path, *, trusted: bool) -> None:
        home.mkdir(parents=True, exist_ok=True)
        for child in ("sessions", "logs", "skills", "memories", "cache"):
            (home / child).mkdir(exist_ok=True)
        # Hermes consults models.dev for generic provider metadata. Seed its
        # isolated cache from the installed Hermes cache so local worker runs do
        # not need an outbound metadata request.
        installed_cache = (
            Path(os.getenv("LOCALAPPDATA", ""))
            / "hermes"
            / "models_dev_cache.json"
        )
        isolated_cache = home / "models_dev_cache.json"
        if installed_cache.is_file():
            shutil.copyfile(installed_cache, isolated_cache)
            os.utime(isolated_cache, None)
        tool_env = {
            "CODEX_HERMES_CONFIG": str(self.config.project_root / "config" / "default.yaml"),
            "PYTHONPATH": str(self.config.project_root / "src"),
        }
        toolsets = (
            self.config.trusted_full.all_toolsets
            if trusted
            else ["codex_worker_tools"]
        )
        disabled_toolsets = [] if trusted else [
            "browser",
            "code_execution",
            "computer_use",
            "cronjob",
            "delegation",
            "file",
            "memory",
            "project",
            "terminal",
            "web",
        ]
        profile: dict[str, Any] = {
            "_config_version": 33,
            "model": {
                "default": self.config.hermes.model,
                "provider": self.config.hermes.provider,
                "base_url": self.config.hermes.base_url,
                "context_length": self.config.hermes.context_length,
            },
            "agent": {
                "max_turns": (
                    self.config.trusted_full.max_steps
                    if trusted
                    else self.config.hermes.max_steps
                ),
                "disabled_toolsets": disabled_toolsets,
                "verbose": False,
            },
            "display": {"show_reasoning": False, "streaming": False},
            "approvals": {"mode": "manual", "timeout": 30, "cron_mode": "deny"},
            "tool_output": {"max_chars": self.config.bridge.max_tool_output_chars},
            "mcp_servers": {
                "codex_worker_tools": {
                    "command": sys.executable,
                    "args": ["-m", "codex_hermes_worker.worker_tools.server"],
                    "cwd": str(self.config.project_root),
                    "env": tool_env,
                    "enabled": True,
                    "tool_timeout_sec": 60,
                }
            },
            "platform_toolsets": {"cli": toolsets},
            "toolsets": toolsets,
            "hooks_auto_accept": False,
        }
        if trusted:
            profile["terminal"] = {
                "backend": "local",
                "cwd": str(self.config.project_root),
                "timeout": 180,
                "home_mode": "profile",
                "env_passthrough": [],
            }
        path = home / "config.yaml"
        path.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8")
        self._scrub_request_dumps(home)

    def _environment(self, home: Path) -> dict[str, str]:
        key = os.getenv(self.config.hermes.api_key_env)
        if not key:
            raise HermesUnavailable(
                f"required runtime environment variable is missing: {self.config.hermes.api_key_env}"
            )
        env = dict(os.environ)
        # The bridge-specific source variable is not needed by Hermes itself.
        # Remove it before launching so terminal/code tools cannot inherit it.
        env.pop(self.config.hermes.api_key_env, None)
        env.update(
            {
                "HERMES_HOME": str(home),
                "OPENAI_API_KEY": key,
                "OPENAI_BASE_URL": self.config.hermes.base_url,
                "OPENROUTER_API_KEY": key,
                "OPENROUTER_BASE_URL": self.config.hermes.base_url,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            }
        )
        return env

    def _redact(self, value: str) -> str:
        key = os.getenv(self.config.hermes.api_key_env)
        return value.replace(key, "<redacted>") if key else value

    def health(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "executable": self.executable,
            "isolated_home": str(self.config.hermes.home),
            "model": self.config.hermes.model,
            "provider": self.config.hermes.provider,
            "base_url": self.config.hermes.base_url,
            "api_key_present": bool(os.getenv(self.config.hermes.api_key_env)),
        }
        try:
            version = subprocess.run(
                [self.executable, "--version"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
            )
            result["hermes_ok"] = version.returncode == 0
            result["hermes_version"] = (version.stdout or version.stderr).splitlines()[0]
        except Exception as exc:
            result["hermes_ok"] = False
            result["hermes_error"] = str(exc)
        try:
            headers = {"Authorization": f"Bearer {os.environ[self.config.hermes.api_key_env]}"}
            with httpx.Client(timeout=10) as client:
                response = client.get(f"{self.config.hermes.base_url.rstrip('/')}/models", headers=headers)
                response.raise_for_status()
                ids = [row.get("id") for row in response.json().get("data", [])]
            result["qwen_ok"] = self.config.hermes.model in ids
            result["available_model_ids"] = ids
        except Exception as exc:
            result["qwen_ok"] = False
            result["qwen_error"] = str(exc)
        result["ok"] = bool(result.get("hermes_ok") and result.get("qwen_ok"))
        return result

    def run(
        self,
        prompt: str,
        *,
        toolsets: list[str] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        return self._run(
            prompt,
            home=self.config.hermes.home,
            cwd=self.config.project_root,
            toolsets=toolsets or ["codex_worker_tools"],
            max_steps=self.config.hermes.max_steps,
            timeout=timeout or self.config.hermes.max_runtime_seconds,
            max_output_chars=self.config.hermes.max_output_chars,
            yolo=False,
            checkpoints=False,
            ignore_rules=True,
        )

    def _run(
        self,
        prompt: str,
        *,
        home: Path,
        cwd: Path,
        toolsets: list[str],
        max_steps: int,
        timeout: int,
        max_output_chars: int,
        yolo: bool,
        checkpoints: bool,
        ignore_rules: bool,
    ) -> dict[str, Any]:
        command = [
            self.executable,
            "chat",
            "--query",
            prompt,
            "--quiet",
            "--model",
            self.config.hermes.model,
            "--toolsets",
            ",".join(toolsets),
            "--max-turns",
            str(max_steps),
            "--source",
            "tool",
        ]
        if ignore_rules:
            command.append("--ignore-rules")
        if yolo:
            command.append("--yolo")
        if checkpoints:
            command.append("--checkpoints")
        if self.config.hermes.provider != "auto":
            command.extend(["--provider", self.config.hermes.provider])
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=self._environment(home),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        finally:
            self._scrub_request_dumps(home)
        safe_stdout = self._redact(completed.stdout)
        safe_stderr = self._redact(completed.stderr)
        stdout, stdout_truncated = truncate_text(
            safe_stdout, max_output_chars
        )
        stderr, stderr_truncated = truncate_text(
            safe_stderr, max_output_chars
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Hermes exited {completed.returncode}: {stderr[-2000:] or stdout[-2000:]}"
            )
        return {
            "text": stdout.strip(),
            "stderr": stderr.strip(),
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "runtime_seconds": round(time.monotonic() - started, 3),
            "model": self.config.hermes.model,
        }

    def run_trusted(
        self,
        prompt: str,
        *,
        working_directory: str,
        requested_toolsets: list[str],
        allow_network: bool,
        include_optional_tools: bool,
        max_steps: int,
        timeout: int,
        authorization: str,
    ) -> dict[str, Any]:
        settings = self.config.trusted_full
        if not settings.enabled:
            raise PermissionError("trusted_full mode is disabled")
        if authorization != settings.required_authorization:
            raise PermissionError(
                "trusted_full requires the exact explicit authorization value"
            )

        cwd = Path(working_directory)
        if not cwd.is_absolute():
            cwd = self.config.project_root / cwd
        cwd = cwd.resolve()
        if not cwd.is_dir():
            raise ValueError(f"working_directory is not an existing directory: {cwd}")
        if not any(cwd == root or root in cwd.parents for root in settings.working_roots):
            raise PermissionError(
                f"working_directory is outside configured trusted roots: {cwd}"
            )

        if requested_toolsets:
            unknown = sorted(set(requested_toolsets) - set(settings.all_toolsets))
            if unknown:
                raise ValueError(f"unconfigured Hermes toolsets: {', '.join(unknown)}")
            tools = list(requested_toolsets)
        else:
            tools = list(settings.local_toolsets)
            if allow_network:
                tools.extend(settings.network_toolsets)
            if include_optional_tools:
                tools.extend(settings.optional_toolsets)
        tools = list(dict.fromkeys(tools))

        gated = set(settings.network_toolsets + settings.optional_toolsets)
        requested_gated = sorted(set(tools) & gated)
        if requested_gated and not allow_network:
            raise PermissionError(
                "network/optional toolsets require allow_network=true: "
                + ", ".join(requested_gated)
            )
        if max_steps > settings.max_steps:
            raise ValueError(f"max_steps exceeds trusted_full limit {settings.max_steps}")
        if timeout > settings.max_runtime_seconds:
            raise ValueError(
                "timeout_seconds exceeds trusted_full limit "
                f"{settings.max_runtime_seconds}"
            )

        task_id = str(uuid4())
        started_at = datetime.now(timezone.utc).isoformat()
        self._write_trusted_audit(
            {
                "event": "trusted_full_started",
                "task_id": task_id,
                "started_at": started_at,
                "working_directory": str(cwd),
                "toolsets": tools,
                "allow_network": allow_network,
                "max_steps": max_steps,
                "timeout_seconds": timeout,
                "instructions_sha256": hashlib.sha256(
                    prompt.encode("utf-8")
                ).hexdigest(),
            }
        )
        try:
            response = self._run(
                prompt,
                home=settings.home,
                cwd=cwd,
                toolsets=tools,
                max_steps=max_steps,
                timeout=timeout,
                max_output_chars=settings.max_output_chars,
                yolo=True,
                checkpoints=settings.checkpoints,
                ignore_rules=False,
            )
        except Exception as exc:
            self._write_trusted_audit(
                {
                    "event": "trusted_full_failed",
                    "task_id": task_id,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "error": self._redact(str(exc))[:2000],
                }
            )
            raise
        self._write_trusted_audit(
            {
                "event": "trusted_full_completed",
                "task_id": task_id,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "runtime_seconds": response["runtime_seconds"],
            }
        )
        response.update(
            {
                "task_id": task_id,
                "execution_mode": "trusted_full",
                "working_directory": str(cwd),
                "toolsets": tools,
                "allow_network": allow_network,
                "audit_log": str(
                    self.config.project_root / "work" / "logs" / "trusted-full-audit.jsonl"
                ),
            }
        )
        return response

    def _write_trusted_audit(self, event: dict[str, Any]) -> None:
        path = self.config.project_root / "work" / "logs" / "trusted-full-audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with self._audit_lock:
            rotate_audit_log(path, self.config.bridge.audit_log_max_bytes)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)

    def _scrub_request_dumps(self, home: Path) -> None:
        """Remove even masked authorization values from Hermes error dumps."""
        sessions = home / "sessions"
        if not sessions.is_dir():
            return
        for path in sessions.glob("request_dump_*.json"):
            try:
                text = path.read_text(encoding="utf-8")
                scrubbed = re.sub(
                    r'("Authorization"\s*:\s*)"[^"]*"',
                    r'\1"<redacted>"',
                    self._redact(text),
                )
                if scrubbed != text:
                    path.write_text(scrubbed, encoding="utf-8")
            except OSError:
                continue

    def run_json(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        response = self.run(prompt, **kwargs)
        parsed = extract_json(response["text"])
        if not isinstance(parsed, dict):
            raise ValueError("expected a JSON object from Hermes/Qwen")
        response["json"] = parsed
        return response
