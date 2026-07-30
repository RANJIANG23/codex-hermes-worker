from __future__ import annotations

from codex_hermes_worker.jobs.worker import LocalWorker


def test_summary_is_fitted_to_schema_without_another_model_call() -> None:
    candidate = {"summary": "A" * 20, "confidence": 0.9}
    schema = {
        "properties": {
            "summary": {
                "type": "string",
                "maxLength": 10,
            }
        }
    }

    fitted = LocalWorker._fit_summary_to_schema(candidate, schema)

    assert fitted["summary"] == "A" * 9 + "…"
    assert candidate["summary"] == "A" * 20


def test_summary_fitting_leaves_valid_candidate_unchanged() -> None:
    candidate = {"summary": "short"}
    schema = {"properties": {"summary": {"maxLength": 10}}}

    assert LocalWorker._fit_summary_to_schema(candidate, schema) is candidate
