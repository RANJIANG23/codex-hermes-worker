from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


JOB_STATUSES = {"queued", "running", "completed", "partial", "failed", "cancelled"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    profile TEXT NOT NULL,
    output_schema TEXT NOT NULL,
    request_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed','cancelled')),
    progress REAL NOT NULL DEFAULT 0,
    processed INTEGER NOT NULL DEFAULT 0,
    failed_items INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS job_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(job_id),
    source_path TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
    asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(job_id),
    source_path TEXT NOT NULL,
    asset_type TEXT,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS functions (
    function_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(job_id),
    address TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strings (
    string_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(job_id),
    source_path TEXT NOT NULL,
    location TEXT,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS classifications (
    record_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    source_path TEXT NOT NULL,
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_json TEXT NOT NULL,
    needs_review INTEGER NOT NULL,
    worker_profile TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    conflict INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL REFERENCES classifications(record_id),
    evidence_type TEXT,
    location TEXT,
    value TEXT
);
CREATE TABLE IF NOT EXISTS conflicts (
    conflict_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    record_id TEXT,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS unresolved_items (
    unresolved_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    record_id TEXT,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS worker_runs (
    run_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    profile TEXT NOT NULL,
    model TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    metrics_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_classifications_job ON classifications(job_id);
CREATE INDEX IF NOT EXISTS ix_classifications_review ON classifications(needs_review, confidence);
"""


class JobDatabase:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    def create_job(self, request: dict[str, Any]) -> str:
        job_id = str(uuid4())
        now = utc_now()
        with self.connection() as conn:
            with conn:
                conn.execute(
                    """INSERT INTO jobs
                    (job_id,task_type,profile,output_schema,request_json,status,created_at)
                    VALUES (?,?,?,?,?,'queued',?)""",
                    (
                        job_id,
                        request["task_type"],
                        request["profile"],
                        request["output_schema"],
                        json.dumps(request, ensure_ascii=False),
                        now,
                    ),
                )
                conn.execute(
                    "INSERT INTO job_events(job_id,event_type,message,created_at) VALUES (?,?,?,?)",
                    (job_id, "queued", "job accepted", now),
                )
        return job_id

    def mark_running(self, job_id: str) -> bool:
        now = utc_now()
        with self.connection() as conn:
            with conn:
                changed = conn.execute(
                    """UPDATE jobs SET status='running',started_at=?
                    WHERE job_id=? AND status='queued' AND cancel_requested=0""",
                    (now, job_id),
                ).rowcount
                if changed:
                    conn.execute(
                        "INSERT INTO job_events(job_id,event_type,message,created_at) VALUES (?,?,?,?)",
                        (job_id, "running", "worker started", now),
                    )
        return bool(changed)

    def update_progress(
        self, job_id: str, processed: int, failed: int, progress: float
    ) -> bool:
        with self.connection() as conn:
            with conn:
                changed = conn.execute(
                    """UPDATE jobs SET processed=?,failed_items=?,progress=?
                    WHERE job_id=? AND status='running'""",
                    (processed, failed, max(0, min(progress, 1)), job_id),
                ).rowcount
        return bool(changed)

    def complete(self, job_id: str) -> str | None:
        now = utc_now()
        with self.connection() as conn:
            with conn:
                row = conn.execute(
                    "SELECT failed_items FROM jobs WHERE job_id=? AND status='running'",
                    (job_id,),
                ).fetchone()
                if row is None:
                    return None
                public_status = "partial" if int(row["failed_items"] or 0) else "completed"
                changed = conn.execute(
                    """UPDATE jobs SET status='completed',progress=1,finished_at=?
                    WHERE job_id=? AND status='running'""",
                    (now, job_id),
                ).rowcount
                if changed:
                    message = (
                        "job completed with unresolved items"
                        if public_status == "partial"
                        else "job completed"
                    )
                    conn.execute(
                        """INSERT INTO job_events(job_id,event_type,message,created_at)
                        VALUES (?,?,?,?)""",
                        (job_id, public_status, message, now),
                    )
                    return public_status
        return None

    def fail(self, job_id: str, error: str) -> bool:
        now = utc_now()
        with self.connection() as conn:
            with conn:
                changed = conn.execute(
                    """UPDATE jobs SET status='failed',error=?,finished_at=?
                    WHERE job_id=? AND status='running'""",
                    (error[:2000], now, job_id),
                ).rowcount
                if changed:
                    conn.execute(
                        """INSERT INTO job_events(job_id,event_type,message,created_at)
                        VALUES (?,?,?,?)""",
                        (job_id, "failed", error[:1000], now),
                    )
        return bool(changed)

    def recover_interrupted(self) -> int:
        now = utc_now()
        with self.connection() as conn:
            with conn:
                rows = conn.execute("SELECT job_id FROM jobs WHERE status='running'").fetchall()
                for row in rows:
                    conn.execute(
                        """UPDATE jobs SET status='failed',error=?,finished_at=?
                        WHERE job_id=?""",
                        ("bridge restarted while job was running; partial results retained", now, row["job_id"]),
                    )
                    conn.execute(
                        "INSERT INTO job_events(job_id,event_type,message,created_at) VALUES (?,?,?,?)",
                        (row["job_id"], "recovered", "marked failed after bridge restart", now),
                    )
        return len(rows)

    def cancel(self, job_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.connection() as conn:
            with conn:
                row = conn.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
                if row is None:
                    raise KeyError(job_id)
                status = row["status"]
                if status == "queued":
                    conn.execute(
                        "UPDATE jobs SET cancel_requested=1,status='cancelled',finished_at=? WHERE job_id=?",
                        (now, job_id),
                    )
                    status = "cancelled"
                elif status == "running":
                    conn.execute("UPDATE jobs SET cancel_requested=1 WHERE job_id=?", (job_id,))
                conn.execute(
                    "INSERT INTO job_events(job_id,event_type,message,created_at) VALUES (?,?,?,?)",
                    (job_id, "cancel_requested", "cancellation requested", now),
                )
        return {"job_id": job_id, "status": status, "cancel_requested": True}

    def is_cancel_requested(self, job_id: str) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT cancel_requested FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def is_active(self, job_id: str) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT status,cancel_requested FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return bool(
            row
            and row["status"] == "running"
            and not bool(row["cancel_requested"])
        )

    def mark_cancelled(self, job_id: str) -> bool:
        now = utc_now()
        with self.connection() as conn:
            with conn:
                changed = conn.execute(
                    """UPDATE jobs SET status='cancelled',finished_at=?
                    WHERE job_id=? AND status='running' AND cancel_requested=1""",
                    (now, job_id),
                ).rowcount
                if changed:
                    conn.execute(
                        """INSERT INTO job_events(job_id,event_type,message,created_at)
                        VALUES (?,?,?,?)""",
                        (job_id, "cancelled", "job cancelled", now),
                    )
        return bool(changed)

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        result = dict(row)
        result.pop("request_json", None)
        result["cancel_requested"] = bool(result["cancel_requested"])
        result["status"] = self._public_status(
            result["status"], result["failed_items"]
        )
        return result

    def list_jobs(
        self, *, status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        if status is not None and status not in JOB_STATUSES:
            raise ValueError(f"invalid job status: {status}")
        actual_limit = max(1, min(int(limit), 200))
        params: list[Any] = []
        where = ""
        if status == "partial":
            where = " WHERE status='completed' AND failed_items>0"
        elif status == "completed":
            where = " WHERE status='completed' AND failed_items=0"
        elif status:
            where = " WHERE status=?"
            params.append(status)
        params.append(actual_limit)
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT job_id,task_type,profile,output_schema,status,progress,"
                "processed,failed_items,cancel_requested,error,created_at,started_at,"
                f"finished_at FROM jobs{where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["cancel_requested"] = bool(row["cancel_requested"])
            row["status"] = self._public_status(row["status"], row["failed_items"])
        return result

    def get_events(self, job_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        self.get_job(job_id)
        actual_limit = max(1, min(int(limit), 200))
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT event_id,event_type,message,created_at
                FROM job_events WHERE job_id=?
                ORDER BY event_id DESC LIMIT ?""",
                (job_id, actual_limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def dashboard_metrics(self) -> dict[str, int]:
        with self.connection() as conn:
            jobs = conn.execute(
                """SELECT
                COUNT(*) AS total_jobs,
                SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) AS queued_jobs,
                SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) AS running_jobs,
                SUM(CASE WHEN status='completed' AND failed_items=0 THEN 1 ELSE 0 END)
                    AS completed_jobs,
                SUM(CASE WHEN status='completed' AND failed_items>0 THEN 1 ELSE 0 END)
                    AS partial_jobs,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_jobs,
                SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) AS cancelled_jobs
                FROM jobs"""
            ).fetchone()
            results = conn.execute(
                """SELECT COUNT(*) AS total_results,
                SUM(needs_review) AS needs_review,
                COUNT(DISTINCT CASE WHEN needs_review=1 THEN job_id END) AS review_jobs,
                SUM(conflict) AS conflicts
                FROM classifications"""
            ).fetchone()
        return {
            key: int(value or 0)
            for row in (jobs, results)
            for key, value in dict(row).items()
        }

    def add_classification(self, job_id: str, record: dict[str, Any]) -> None:
        with self.connection() as conn:
            with conn:
                conn.execute(
                    """INSERT OR REPLACE INTO classifications
                    (record_id,job_id,source_path,category,summary,confidence,evidence_json,
                    needs_review,worker_profile,model,created_at,conflict)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        record["record_id"],
                        job_id,
                        record["source_path"],
                        record["category"],
                        record["summary"],
                        record["confidence"],
                        json.dumps(record.get("evidence", []), ensure_ascii=False),
                        int(record.get("needs_review", False)),
                        record["worker_profile"],
                        record["model"],
                        record["created_at"],
                        int(record.get("conflict", False)),
                    ),
                )
                for item in record.get("evidence", []):
                    conn.execute(
                        """INSERT INTO evidence(record_id,evidence_type,location,value)
                        VALUES (?,?,?,?)""",
                        (
                            record["record_id"],
                            item.get("type"),
                            str(item.get("location", "")),
                            str(item.get("value", ""))[:4000],
                        ),
                    )
                if record.get("needs_review"):
                    conn.execute(
                        """INSERT INTO unresolved_items(job_id,record_id,reason,created_at)
                        VALUES (?,?,?,?)""",
                        (job_id, record["record_id"], "needs_review", utc_now()),
                    )

    def add_unresolved(self, job_id: str, source_path: str, reason: str) -> None:
        with self.connection() as conn:
            with conn:
                conn.execute(
                    """INSERT INTO unresolved_items(job_id,record_id,reason,created_at)
                    VALUES (?,?,?,?)""",
                    (job_id, source_path, reason[:2000], utc_now()),
                )

    def query(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        mapping = {
            "job_id": "job_id",
            "needs_review": "needs_review",
            "conflict": "conflict",
        }
        for key, column in mapping.items():
            if filters.get(key) is not None:
                clauses.append(f"{column}=?")
                value = int(filters[key]) if isinstance(filters[key], bool) else filters[key]
                params.append(value)
        if filters.get("low_confidence"):
            clauses.append("confidence < 0.70")
        if filters.get("label"):
            clauses.append("category=?")
            params.append(filters["label"])
        if filters.get("path_contains"):
            clauses.append("source_path LIKE ?")
            params.append(f"%{filters['path_contains']}%")
        if filters.get("function_address"):
            clauses.append("source_path=?")
            params.append(filters["function_address"])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT * FROM classifications"
            + where
            + " ORDER BY needs_review DESC, confidence ASC, created_at ASC LIMIT ?"
        )
        params.append(limit)
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._classification_row(row) for row in rows]

    @staticmethod
    def _classification_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["needs_review"] = bool(item["needs_review"])
        item["conflict"] = bool(item["conflict"])
        item["evidence"] = json.loads(item.pop("evidence_json"))
        return item

    @staticmethod
    def _public_status(status: str, failed_items: int) -> str:
        if status == "completed" and int(failed_items or 0) > 0:
            return "partial"
        return status

    def iter_job_results(
        self, job_id: str, *, batch_size: int = 500
    ) -> Iterator[dict[str, Any]]:
        """Stream every result for durable export without the MCP query cap."""
        with self.connection() as conn:
            cursor = conn.execute(
                """SELECT * FROM classifications
                WHERE job_id=?
                ORDER BY created_at ASC, record_id ASC""",
                (job_id,),
            )
            while rows := cursor.fetchmany(batch_size):
                for row in rows:
                    yield self._classification_row(row)

    def summary(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        with self.connection() as conn:
            row = conn.execute(
                """SELECT COUNT(*) processed,
                SUM(CASE WHEN confidence >= 0.85 THEN 1 ELSE 0 END) high_confidence,
                SUM(CASE WHEN confidence < 0.70 THEN 1 ELSE 0 END) low_confidence,
                SUM(conflict) conflicts,
                SUM(needs_review) needs_review
                FROM classifications WHERE job_id=?""",
                (job_id,),
            ).fetchone()
        counts = {key: int(row[key] or 0) for key in row.keys()}
        return {**job, **counts}
