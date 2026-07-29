from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

from codex_hermes_worker.bridge.config import load_config
from codex_hermes_worker.console.server import (
    ConsoleHTTPServer,
    ConsoleService,
    run_console,
)


class FakeManager:
    def __init__(self) -> None:
        self.request: Any = None

    def submit(self, request: Any) -> dict[str, Any]:
        self.request = request
        return {"job_id": "test-job", "status": "queued", "accepted": True}


class FakeRuntime:
    def __init__(self) -> None:
        self.manager = FakeManager()


class StubHTTPService:
    def ping(self) -> dict[str, Any]:
        return {"ok": True, "version": "1.1.0"}

    def overview(self) -> dict[str, Any]:
        return {"version": "1.1.0", "metrics": {}, "recent_jobs": []}

    def analytics(self) -> dict[str, Any]:
        return {
            "jobs": {"total": 2},
            "tokens": {"available": True, "total": {"input_tokens": 120}},
        }

    def health(self) -> dict[str, Any]:
        return {"ok": True}

    def list_jobs(self, *, status: str | None, limit: int) -> dict[str, Any]:
        return {"count": 0, "jobs": [], "status": status, "limit": limit}

    def job_detail(self, job_id: str) -> dict[str, Any]:
        return {"job_id": job_id}

    def submit_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"accepted": True, **payload}

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        return {"job_id": job_id, "cancel_requested": True}

    def run_trusted(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload


def test_console_service_submits_validated_restricted_job(tmp_path: Path) -> None:
    config = load_config().model_copy(deep=True)
    config.jobs.database = tmp_path / "jobs.db"
    config.jobs.result_jsonl_dir = tmp_path / "results"
    config.jobs.review_dir = tmp_path / "review"
    runtime = FakeRuntime()
    service = ConsoleService(config, runtime_factory=lambda: runtime)  # type: ignore[arg-type]

    result = service.submit_job(
        {
            "task_type": "asset_classification",
            "instructions": "Classify the test records.",
            "input_paths": ["testdata/assets.jsonl"],
            "profile": "asset_worker",
            "output_schema": "asset_classification_v1",
            "max_steps": 8,
        }
    )

    assert result["accepted"] is True
    assert runtime.manager.request.profile == "asset_worker"
    assert runtime.manager.request.max_steps == 8


def test_console_http_requires_token_and_sets_security_headers() -> None:
    server = ConsoleHTTPServer(
        ("127.0.0.1", 0),
        StubHTTPService(),  # type: ignore[arg-type]
        token="unit-test-token",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with httpx.Client(base_url=base_url, timeout=5) as client:
            page = client.get("/")
            assert page.status_code == 200
            assert 'content="unit-test-token"' in page.text
            assert page.headers["x-frame-options"] == "DENY"
            assert "default-src 'self'" in page.headers["content-security-policy"]

            denied = client.get("/api/overview")
            assert denied.status_code == 403

            allowed = client.get(
                "/api/overview",
                headers={"X-Console-Token": "unit-test-token"},
            )
            assert allowed.status_code == 200
            assert allowed.json()["version"] == "1.1.0"

            analytics = client.get(
                "/api/analytics",
                headers={"X-Console-Token": "unit-test-token"},
            )
            assert analytics.status_code == 200
            assert analytics.json()["tokens"]["total"]["input_tokens"] == 120

            foreign_origin = client.post(
                "/api/jobs",
                headers={
                    "X-Console-Token": "unit-test-token",
                    "Origin": "https://example.com",
                },
                json={"task_type": "asset_classification"},
            )
            assert foreign_origin.status_code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_console_rejects_non_loopback_binding() -> None:
    with pytest.raises(ValueError, match="loopback"):
        run_console(host="0.0.0.0", open_browser=False)
