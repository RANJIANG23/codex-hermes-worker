from __future__ import annotations

import argparse
import json
import logging
import re
import secrets
import sqlite3
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from pydantic import ValidationError

from codex_hermes_worker import __version__
from codex_hermes_worker.analytics import TokenAnalytics
from codex_hermes_worker.bridge.config import AppConfig, load_config
from codex_hermes_worker.bridge.runtime import Runtime
from codex_hermes_worker.bridge.schemas import TaskRequest, TrustedFullTaskRequest
from codex_hermes_worker.jobs.database import JOB_STATUSES, JobDatabase
from codex_hermes_worker.policies.filesystem import FilesystemPolicy


LOGGER = logging.getLogger("codex_hermes_worker.console")
MAX_REQUEST_BYTES = 64 * 1024
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
ASSET_TYPES = {
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "favicon.svg": "image/svg+xml",
}
TASK_PRESETS = {
    "asset_classification": {
        "label": "资产分类",
        "profile": "asset_worker",
        "output_schema": "asset_classification_v1",
    },
    "audio_asset_classification": {
        "label": "音频资产分类",
        "profile": "audio_asset_worker",
        "output_schema": "asset_classification_v1",
    },
    "disassembly_triage": {
        "label": "反汇编初筛",
        "profile": "disassembly_triage_worker",
        "output_schema": "disassembly_triage_v1",
    },
    "verification": {
        "label": "独立复核",
        "profile": "verification_worker",
        "output_schema": "verification_v1",
    },
    "qwen_tool_test": {
        "label": "工具链测试",
        "profile": "verification_worker",
        "output_schema": "tool_chain_v1",
    },
}


class ConsoleService:
    """Application layer shared by the HTTP console and unit tests."""

    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        runtime_factory: Callable[[], Runtime] | None = None,
    ):
        self.config = config or load_config()
        self.database = JobDatabase(self.config.jobs.database)
        self.token_analytics = TokenAnalytics(self.config)
        self._runtime_factory = runtime_factory or (
            lambda: Runtime(self.config, recover_interrupted=False)
        )
        self._runtime_instance: Runtime | None = None
        self._runtime_lock = threading.Lock()

    def _runtime(self) -> Runtime:
        if self._runtime_instance is None:
            with self._runtime_lock:
                if self._runtime_instance is None:
                    self._runtime_instance = self._runtime_factory()
        return self._runtime_instance

    def ping(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": "codex-hermes-console",
            "version": __version__,
        }

    def health(self) -> dict[str, Any]:
        database_ok = False
        sqlite_version: str | None = None
        try:
            with self.database.connection() as conn:
                sqlite_version = str(
                    conn.execute("select sqlite_version()").fetchone()[0]
                )
            database_ok = True
        except sqlite3.Error:
            pass

        try:
            hermes = self._runtime().hermes.health()
        except Exception as exc:
            hermes = {
                "ok": False,
                "hermes_ok": False,
                "qwen_ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {
            "ok": bool(database_ok and hermes.get("ok")),
            "bridge": {"status": "ready", "name": self.config.bridge.name},
            "hermes": hermes,
            "database": {
                "ok": database_ok,
                "sqlite_version": sqlite_version,
                "path": str(self.config.jobs.database),
            },
            "security": {
                "default_execution_mode": "restricted_batch",
                "allow_network": self.config.agent.allow_network,
                "trusted_full_enabled": self.config.trusted_full.enabled,
                "trusted_full_requires_authorization": True,
                "host_shell_is_not_sandboxed": True,
            },
        }

    def overview(self) -> dict[str, Any]:
        return {
            "version": __version__,
            "metrics": self.database.dashboard_metrics(),
            "recent_jobs": self.database.list_jobs(limit=8),
            "presets": TASK_PRESETS,
            "configuration": {
                "model": self.config.hermes.model,
                "base_url": self.config.hermes.base_url,
                "profiles": sorted(self.config.profiles),
                "schemas": sorted(self.config.schemas),
                "readable_roots": [
                    str(path) for path in self.config.filesystem.readable_roots
                ],
                "work_directory": str(self.config.project_root / "work"),
                "max_workers": self.config.jobs.max_workers,
                "trusted_full_enabled": self.config.trusted_full.enabled,
                "trusted_toolsets": self.config.trusted_full.local_toolsets,
                "network_toolsets": self.config.trusted_full.network_toolsets,
            },
        }

    def list_jobs(
        self, *, status: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        jobs = self.database.list_jobs(status=status, limit=limit)
        return {"count": len(jobs), "jobs": jobs}

    def analytics(self) -> dict[str, Any]:
        return {
            "jobs": self.database.dashboard_metrics(),
            "tokens": self.token_analytics.summary(),
        }

    def job_detail(self, job_id: str) -> dict[str, Any]:
        summary = self.database.summary(job_id)
        return {
            "summary": summary,
            "events": self.database.get_events(job_id),
            "results": self.database.query({"job_id": job_id}, 50),
            "artifacts": {
                "result_jsonl": str(
                    self.config.jobs.result_jsonl_dir / f"{job_id}.jsonl"
                ),
                "review_manifest": str(
                    self.config.jobs.review_dir / f"{job_id}.jsonl"
                ),
            },
        }

    def submit_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = TaskRequest.model_validate(payload)
        if request.profile not in self.config.profiles:
            raise ValueError(f"unknown profile: {request.profile}")
        if request.output_schema not in self.config.schemas:
            raise ValueError(f"unknown output schema: {request.output_schema}")
        policy = FilesystemPolicy(self.config)
        for path in request.input_paths:
            policy.resolve_read(path)
        return self._runtime().manager.submit(request)

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        return self.database.cancel(job_id)

    def run_trusted(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.config.trusted_full.enabled:
            raise PermissionError("trusted_full is disabled")
        payload = dict(payload)
        if payload.pop("risk_acknowledgement", None) != "trusted_full":
            raise PermissionError("trusted_full risk acknowledgement is required")
        request = TrustedFullTaskRequest.model_validate(payload)
        response = self._runtime().hermes.run_trusted(
            request.instructions,
            working_directory=request.working_directory,
            requested_toolsets=request.toolsets,
            allow_network=request.allow_network,
            include_optional_tools=request.include_optional_tools,
            max_steps=request.max_steps,
            timeout=request.timeout_seconds,
            authorization=request.authorization,
        )
        return {
            "status": "completed",
            "task_id": response["task_id"],
            "execution_mode": response["execution_mode"],
            "working_directory": response["working_directory"],
            "toolsets": response["toolsets"],
            "allow_network": response["allow_network"],
            "result": response["text"],
            "runtime_seconds": response["runtime_seconds"],
            "output_truncated": response["stdout_truncated"],
            "audit_log": response["audit_log"],
            "model": response["model"],
        }


class ConsoleHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        service: ConsoleService,
        *,
        token: str | None = None,
    ):
        self.service = service
        self.console_token = token or secrets.token_urlsafe(32)
        super().__init__(address, ConsoleRequestHandler)


class ConsoleRequestHandler(BaseHTTPRequestHandler):
    server: ConsoleHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.address_string(), format % args)

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'",
        )
        self.send_header("Cache-Control", "no-store")

    def _send_bytes(
        self, status: int, body: bytes, content_type: str
    ) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, value: Any) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _is_local_host_header(self) -> bool:
        host = self.headers.get("Host", "")
        try:
            parsed = urlsplit(f"//{host}")
            return (parsed.hostname or "").lower() in LOOPBACK_HOSTS
        except ValueError:
            return False

    def _authorized(self) -> bool:
        if not self._is_local_host_header():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "local host required"})
            return False
        if self.headers.get("X-Console-Token") != self.server.console_token:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid console token"})
            return False
        origin = self.headers.get("Origin")
        if origin:
            try:
                parsed = urlsplit(origin)
                if (parsed.hostname or "").lower() not in LOOPBACK_HOSTS:
                    raise ValueError
                if parsed.port not in (None, self.server.server_port):
                    raise ValueError
            except ValueError:
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid origin"})
                return False
        return True

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request body must be between 1 byte and 64 KiB")
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise ValueError("Content-Type must be application/json")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, ValidationError):
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "validation failed", "details": json.loads(exc.json())},
            )
        elif isinstance(exc, KeyError):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "job not found"})
        elif isinstance(exc, PermissionError):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
        elif isinstance(exc, (ValueError, json.JSONDecodeError)):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        else:
            LOGGER.exception("console request failed")
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": f"{type(exc).__name__}: {exc}"},
            )

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/api/ping":
            self._send_json(HTTPStatus.OK, self.server.service.ping())
            return
        if path.startswith("/api/"):
            if not self._authorized():
                return
            try:
                if path == "/api/health":
                    result = self.server.service.health()
                elif path == "/api/overview":
                    result = self.server.service.overview()
                elif path == "/api/analytics":
                    result = self.server.service.analytics()
                elif path == "/api/jobs":
                    query = parse_qs(parsed.query)
                    status = query.get("status", [None])[0] or None
                    if status is not None and status not in JOB_STATUSES:
                        raise ValueError("invalid job status")
                    limit = int(query.get("limit", ["50"])[0])
                    result = self.server.service.list_jobs(
                        status=status, limit=limit
                    )
                elif match := re.fullmatch(r"/api/jobs/([^/]+)", path):
                    result = self.server.service.job_detail(match.group(1))
                else:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                self._send_json(HTTPStatus.OK, result)
            except Exception as exc:
                self._handle_error(exc)
            return
        self._serve_asset(path)

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if not parsed.path.startswith("/api/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not self._authorized():
            return
        try:
            payload = self._read_json()
            if parsed.path == "/api/jobs":
                result = self.server.service.submit_job(payload)
                status = HTTPStatus.ACCEPTED
            elif match := re.fullmatch(r"/api/jobs/([^/]+)/cancel", parsed.path):
                result = self.server.service.cancel_job(match.group(1))
                status = HTTPStatus.OK
            elif parsed.path == "/api/trusted-tasks":
                result = self.server.service.run_trusted(payload)
                status = HTTPStatus.OK
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            self._send_json(status, result)
        except Exception as exc:
            self._handle_error(exc)

    def _serve_asset(self, path: str) -> None:
        name = "index.html" if path in ("/", "/index.html") else path.removeprefix("/")
        if name == "favicon.ico":
            name = "favicon.svg"
        if name not in {"index.html", *ASSET_TYPES}:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        resource = files("codex_hermes_worker.console.static").joinpath(name)
        body = resource.read_bytes()
        if name == "index.html":
            text = body.decode("utf-8")
            text = text.replace("__CONSOLE_TOKEN__", self.server.console_token)
            text = text.replace("__APP_VERSION__", __version__)
            body = text.encode("utf-8")
            content_type = "text/html; charset=utf-8"
        else:
            content_type = ASSET_TYPES[name]
        self._send_bytes(HTTPStatus.OK, body, content_type)


def run_console(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    service: ConsoleService | None = None,
) -> None:
    if host.lower() not in LOOPBACK_HOSTS:
        raise ValueError("the console may only bind to a loopback address")
    server = ConsoleHTTPServer((host, port), service or ConsoleService())
    url = f"http://{host}:{server.server_port}/"
    print(f"Codex Hermes Console {__version__}: {url}", flush=True)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Codex Hermes Console.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_console(
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
    )


if __name__ == "__main__":
    main()
