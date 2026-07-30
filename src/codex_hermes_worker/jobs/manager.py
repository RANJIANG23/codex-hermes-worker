from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from codex_hermes_worker.bridge.config import AppConfig
from codex_hermes_worker.bridge.schemas import TaskRequest
from codex_hermes_worker.jobs.database import JobDatabase
from codex_hermes_worker.jobs.worker import LocalWorker


class JobManager:
    def __init__(
        self,
        config: AppConfig,
        database: JobDatabase,
        worker: LocalWorker,
        *,
        recover_interrupted: bool = True,
    ):
        self.config = config
        self.database = database
        self.worker = worker
        self.executor = ThreadPoolExecutor(
            max_workers=config.jobs.max_workers, thread_name_prefix="local-worker"
        )
        self.recovered_jobs = (
            database.recover_interrupted() if recover_interrupted else 0
        )
        self._lock = threading.Lock()

    def submit(self, request: TaskRequest) -> dict[str, Any]:
        job_id = self.database.create_job(request.model_dump())
        self.executor.submit(self._run, job_id, request)
        return {"job_id": job_id, "status": "queued", "accepted": True}

    def run_sync(self, request: TaskRequest) -> dict[str, Any]:
        job_id = self.database.create_job(request.model_dump())
        self._run(job_id, request)
        return {
            "job_id": job_id,
            "status": self.database.get_job(job_id)["status"],
            "summary": self.database.summary(job_id),
        }

    def _run(self, job_id: str, request: TaskRequest) -> None:
        if not self.database.mark_running(job_id):
            return
        try:
            self.worker.execute(
                request,
                job_id=job_id,
                progress=lambda processed, failed, pct: self.database.update_progress(
                    job_id, processed, failed, pct
                ),
                cancelled=lambda: not self.database.is_active(job_id),
            )
            if self.database.is_cancel_requested(job_id):
                self.database.mark_cancelled(job_id)
            else:
                self.database.complete(job_id)
            self._write_artifacts(job_id)
        except Exception as exc:
            self.database.fail(job_id, f"{type(exc).__name__}: {exc}")
            self._write_artifacts(job_id)

    def _write_artifacts(self, job_id: str) -> None:
        result_path = self.config.jobs.result_jsonl_dir / f"{job_id}.jsonl"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        review_path = self.config.jobs.review_dir / f"{job_id}.jsonl"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        with (
            result_path.open("w", encoding="utf-8", newline="\n") as result_handle,
            review_path.open("w", encoding="utf-8", newline="\n") as review_handle,
        ):
            for row in self.database.iter_job_results(job_id):
                result_handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                if row["needs_review"] or row["conflict"]:
                    review_handle.write(json.dumps(row, ensure_ascii=False) + "\n")
