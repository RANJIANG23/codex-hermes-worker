from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from codex_hermes_worker.bridge.config import load_config
from codex_hermes_worker.bridge.schemas import TaskRequest
from codex_hermes_worker.jobs.database import JobDatabase
from codex_hermes_worker.jobs.manager import JobManager


class OverlapWorker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.maximum_active = 0
        self.both_started = threading.Event()
        self.release = threading.Event()

    def execute(
        self,
        request: TaskRequest,
        *,
        job_id: str,
        progress: Any,
        cancelled: Any,
    ) -> list[dict[str, Any]]:
        with self._lock:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            if self.active == 2:
                self.both_started.set()
        try:
            self.release.wait(timeout=5)
            if not cancelled():
                progress(1, 0, 1.0)
            return []
        finally:
            with self._lock:
                self.active -= 1


def test_two_submitted_jobs_can_run_at_the_same_time(tmp_path: Path) -> None:
    config = load_config().model_copy(deep=True)
    config.jobs.max_workers = 2
    config.jobs.database = tmp_path / "jobs.db"
    config.jobs.result_jsonl_dir = tmp_path / "results"
    config.jobs.review_dir = tmp_path / "review"
    database = JobDatabase(config.jobs.database)
    worker = OverlapWorker()
    manager = JobManager(
        config,
        database,
        worker,  # type: ignore[arg-type]
        recover_interrupted=False,
    )
    request = TaskRequest(
        task_type="verification",
        instructions="test controlled overlap",
        input_paths=["testdata/assets.jsonl"],
        profile="verification_worker",
        output_schema="verification_v1",
        max_steps=2,
    )

    try:
        first = manager.submit(request)["job_id"]
        second = manager.submit(request)["job_id"]
        assert worker.both_started.wait(timeout=2)
        assert worker.maximum_active == 2
        assert database.get_job(first)["status"] == "running"
        assert database.get_job(second)["status"] == "running"

        worker.release.set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            statuses = {
                database.get_job(first)["status"],
                database.get_job(second)["status"],
            }
            if statuses == {"completed"}:
                break
            time.sleep(0.02)
        assert database.get_job(first)["status"] == "completed"
        assert database.get_job(second)["status"] == "completed"
    finally:
        worker.release.set()
        manager.executor.shutdown(wait=True)
