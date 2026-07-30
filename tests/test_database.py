from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

from codex_hermes_worker.jobs.database import JobDatabase


REQUEST = {
    "task_type": "asset_classification",
    "instructions": "classify",
    "input_paths": ["testdata/assets.jsonl"],
    "profile": "asset_worker",
    "output_schema": "asset_classification_v1",
    "max_steps": 8,
}


def test_job_lifecycle_and_summary(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    job_id = db.create_job(REQUEST)
    assert db.mark_running(job_id)
    db.update_progress(job_id, 3, 0, 0.5)
    db.complete(job_id)
    row = db.get_job(job_id)
    assert row["status"] == "completed"
    assert row["progress"] == 1


def test_interrupted_job_is_recovered_without_losing_database(tmp_path: Path) -> None:
    path = tmp_path / "jobs.db"
    db = JobDatabase(path)
    job_id = db.create_job(REQUEST)
    assert db.mark_running(job_id)
    reopened = JobDatabase(path)
    assert reopened.recover_interrupted() == 1
    row = reopened.get_job(job_id)
    assert row["status"] == "failed"
    assert "partial results retained" in row["error"]


def test_recovered_job_cannot_be_overwritten_by_stale_worker(tmp_path: Path) -> None:
    path = tmp_path / "jobs.db"
    db = JobDatabase(path)
    job_id = db.create_job(REQUEST)
    assert db.mark_running(job_id)
    assert db.update_progress(job_id, 1, 0, 0.2)
    assert db.recover_interrupted() == 1

    assert db.update_progress(job_id, 5, 0, 1.0) is False
    assert db.complete(job_id) is None
    assert db.fail(job_id, "late stale error") is False

    row = db.get_job(job_id)
    assert row["status"] == "failed"
    assert row["processed"] == 1
    assert "partial results retained" in row["error"]
    assert [event["event_type"] for event in db.get_events(job_id)] == [
        "queued",
        "running",
        "recovered",
    ]


def test_completed_job_with_failed_items_is_reported_as_partial(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    job_id = db.create_job(REQUEST)
    assert db.mark_running(job_id)
    assert db.update_progress(job_id, 2, 1, 1.0)
    assert db.complete(job_id) == "partial"

    assert db.get_job(job_id)["status"] == "partial"
    assert [job["job_id"] for job in db.list_jobs(status="partial")] == [job_id]
    assert db.list_jobs(status="completed") == []
    assert db.get_events(job_id)[-1]["event_type"] == "partial"
    metrics = db.dashboard_metrics()
    assert metrics["partial_jobs"] == 1
    assert metrics["completed_jobs"] == 0


def test_cancel_queued_job_is_consistent(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    job_id = db.create_job(REQUEST)
    result = db.cancel(job_id)
    assert result["status"] == "cancelled"
    assert db.get_job(job_id)["status"] == "cancelled"


def test_durable_export_is_not_limited_by_mcp_query_cap(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    job_id = db.create_job(REQUEST)
    for index in range(125):
        db.add_classification(
            job_id,
            {
                "record_id": f"record-{index:03d}",
                "source_path": f"item-{index:03d}",
                "category": "test",
                "summary": "bounded",
                "confidence": 0.9,
                "evidence": [],
                "needs_review": False,
                "worker_profile": "asset_worker",
                "model": "test-model",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    assert len(db.query({"job_id": job_id}, 100)) == 100
    assert len(list(db.iter_job_results(job_id))) == 125
    summary = db.summary(job_id)
    assert summary["processed"] == 125
    assert "source_path" not in summary
    assert "evidence" not in summary


def test_dashboard_job_listing_and_events_are_bounded(tmp_path: Path) -> None:
    db = JobDatabase(tmp_path / "jobs.db")
    first = db.create_job(REQUEST)
    second = db.create_job(REQUEST)
    assert db.mark_running(first)
    db.complete(first)

    jobs = db.list_jobs(limit=1)
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == second
    assert "request_json" not in jobs[0]

    completed = db.list_jobs(status="completed")
    assert [job["job_id"] for job in completed] == [first]
    events = db.get_events(first)
    assert [event["event_type"] for event in events] == [
        "queued",
        "running",
        "completed",
    ]

    metrics = db.dashboard_metrics()
    assert metrics["total_jobs"] == 2
    assert metrics["queued_jobs"] == 1
    assert metrics["completed_jobs"] == 1
    assert metrics["partial_jobs"] == 0
    assert metrics["total_results"] == 0
