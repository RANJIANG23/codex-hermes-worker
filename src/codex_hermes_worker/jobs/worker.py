from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import jsonschema
import yaml

from codex_hermes_worker.bridge.config import AppConfig
from codex_hermes_worker.bridge.hermes_client import HermesClient
from codex_hermes_worker.bridge.schemas import SemanticRecord, TaskRequest
from codex_hermes_worker.jobs.database import JobDatabase
from codex_hermes_worker.policies.filesystem import FilesystemPolicy
from codex_hermes_worker.worker_tools.deterministic import file_metadata


class LocalWorker:
    def __init__(self, config: AppConfig, database: JobDatabase, hermes: HermesClient):
        self.config = config
        self.database = database
        self.hermes = hermes
        self.policy = FilesystemPolicy(config)

    def _profile_text(self, name: str) -> str:
        if name not in self.config.profiles:
            raise ValueError(f"unknown profile: {name}")
        profile = yaml.safe_load(self.config.profiles[name].read_text(encoding="utf-8"))
        return str(profile["system"])

    def _validate_request(self, request: TaskRequest) -> None:
        if request.profile not in self.config.profiles:
            raise ValueError(f"unknown profile: {request.profile}")
        if request.output_schema not in self.config.schemas:
            raise ValueError(f"unknown output schema: {request.output_schema}")
        if request.max_steps > self.config.agent.max_steps:
            raise ValueError("max_steps exceeds configured agent limit")
        for value in request.input_paths:
            self.policy.resolve_read(value)

    def _load_records(self, request: TaskRequest) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for value in request.input_paths:
            path = self.policy.resolve_read(value)
            if path.suffix.lower() == ".jsonl":
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        rows.append(json.loads(line))
            elif path.is_file():
                rows.append(file_metadata(self.policy, value))
        return rows

    def _semantic_prompt(self, request: TaskRequest, row: dict[str, Any]) -> str:
        schema = json.loads(self.config.schemas[request.output_schema].read_text(encoding="utf-8"))
        return (
            f"{self._profile_text(request.profile)}\n\n"
            f"Task instructions: {request.instructions}\n"
            "Analyze exactly one record below. Use only the evidence in the record. "
            "Keep summary under 300 characters. Return one JSON object only, with no "
            "Markdown or commentary, matching this JSON Schema:\n"
            f"{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Record:\n{json.dumps(row, ensure_ascii=False)}"
        )

    def _semantic_batch_prompt(
        self, request: TaskRequest, rows: list[dict[str, Any]]
    ) -> str:
        schema = json.loads(
            self.config.schemas[request.output_schema].read_text(encoding="utf-8")
        )
        indexed = [{"source_index": index, "record": row} for index, row in enumerate(rows)]
        return (
            f"{self._profile_text(request.profile)}\n\n"
            f"Task instructions: {request.instructions}\n"
            f"Analyze all {len(rows)} records independently. Use only supplied evidence. "
            "Keep every summary under 300 characters. Return only one JSON object with "
            'the shape {"results":[...]}. Every result must include source_index plus '
            "all fields required by the item JSON Schema below. Preserve each source_index "
            "exactly once and do not add Markdown.\n"
            f"Item JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Indexed records:\n{json.dumps(indexed, ensure_ascii=False)}"
        )

    def _store_semantic_result(
        self,
        request: TaskRequest,
        row: dict[str, Any],
        result: dict[str, Any],
        job_id: str,
    ) -> dict[str, Any]:
        source = str(
            row.get("path")
            or row.get("address")
            or row.get("source_path")
            or "unknown"
        )
        record = SemanticRecord(
            source_path=source,
            category=str(
                result.get("category")
                or result.get("subsystem")
                or result.get("verdict")
                or "unknown"
            ),
            summary=str(result["summary"]),
            confidence=float(result["confidence"]),
            evidence=list(result.get("evidence", [])),
            needs_review=bool(
                result.get("needs_review") or float(result["confidence"]) < 0.70
            ),
            worker_profile=request.profile,
            model=self.config.hermes.model,
        ).model_dump()
        self.database.add_classification(job_id, record)
        return record

    def execute(
        self,
        request: TaskRequest,
        *,
        job_id: str,
        progress: Callable[[int, int, float], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        self._validate_request(request)
        if request.task_type == "qwen_tool_test":
            result = self._tool_chain(request, job_id)
            if progress:
                progress(1, 0, 1.0)
            return [result]
        rows = self._load_records(request)
        results: list[dict[str, Any]] = []
        schema = json.loads(self.config.schemas[request.output_schema].read_text(encoding="utf-8"))
        processed = 0
        failed = 0
        batch_size = 5
        for batch_start in range(0, len(rows), batch_size):
            if cancelled and cancelled():
                break
            batch = rows[batch_start : batch_start + batch_size]
            batch_error: Exception | None = None
            try:
                response = self.hermes.run_json(
                    self._semantic_batch_prompt(request, batch),
                    timeout=min(self.config.hermes.max_runtime_seconds, 240),
                )
                candidates = response["json"].get("results")
                if not isinstance(candidates, list):
                    raise ValueError("batch response is missing results[]")
                by_index = {
                    int(item["source_index"]): item
                    for item in candidates
                    if isinstance(item, dict) and "source_index" in item
                }
            except Exception as exc:
                batch_error = exc
                by_index = {}
            for local_index, row in enumerate(batch):
                candidate = by_index.get(local_index)
                try:
                    if candidate is None:
                        suffix = f"; batch error: {batch_error}" if batch_error else ""
                        raise ValueError(f"missing source_index {local_index}{suffix}")
                    candidate = dict(candidate)
                    candidate.pop("source_index", None)
                    jsonschema.validate(candidate, schema)
                    results.append(
                        self._store_semantic_result(request, row, candidate, job_id)
                    )
                    processed += 1
                except Exception as first_error:
                    try:
                        repair = self.hermes.run_json(
                            self._semantic_prompt(request, row)
                            + "\nThe previous batch item failed validation. Be especially concise "
                            "and obey every enum, type, and length constraint.",
                            timeout=min(self.config.hermes.max_runtime_seconds, 180),
                        )["json"]
                        jsonschema.validate(repair, schema)
                        results.append(
                            self._store_semantic_result(request, row, repair, job_id)
                        )
                        processed += 1
                    except Exception as second_error:
                        failed += 1
                        source = str(
                            row.get("path")
                            or row.get("address")
                            or row.get("source_path")
                            or (batch_start + local_index)
                        )
                        self.database.add_unresolved(
                            job_id,
                            source,
                            f"schema failure after repair: {type(second_error).__name__}: "
                            f"{second_error}; first={type(first_error).__name__}: {first_error}",
                        )
                if progress:
                    done = processed + failed
                    progress(processed, failed, done / max(1, len(rows)))
        return results

    def _tool_chain(self, request: TaskRequest, job_id: str) -> dict[str, Any]:
        prompt = (
            f"{self._profile_text(request.profile)}\n"
            f"{request.instructions}\n"
            "You MUST first call list_workspace_files on testdata/tool_loop. "
            "Then call read_text_excerpt on testdata/tool_loop/evidence.txt. "
            "Do not use any other data source. After both calls, return only a JSON object "
            'inside <json> tags with keys: answer, tools_used, confidence, needs_review. '
            "tools_used must list the exact two tool names."
        )
        response = self.hermes.run_json(prompt, timeout=180)
        result = response["json"]
        schema = json.loads(self.config.schemas[request.output_schema].read_text(encoding="utf-8"))
        jsonschema.validate(result, schema)
        record = SemanticRecord(
            source_path="testdata/tool_loop/evidence.txt",
            category="tool_chain",
            summary=str(result["answer"]),
            confidence=float(result["confidence"]),
            evidence=[{"type": "tool_calls", "location": "audit", "value": result["tools_used"]}],
            needs_review=bool(result["needs_review"]),
            worker_profile=request.profile,
            model=self.config.hermes.model,
        ).model_dump()
        self.database.add_classification(job_id, record)
        return record
