from __future__ import annotations

import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_hermes_worker.bridge.config import AppConfig


TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)

GPT56_SOL_PRICING = {
    "model": "gpt-5.6-sol",
    "service_tier": "standard",
    "context_band": "short_context",
    "currency": "USD",
    "unit_tokens": 1_000_000,
    "input_usd_per_million": 5.0,
    "cached_input_usd_per_million": 0.5,
    "cache_write_usd_per_million": 6.25,
    "output_usd_per_million": 30.0,
    "source_url": "https://developers.openai.com/api/docs/pricing",
}
GPT56_SOL_USAGE_MULTIPLIER = 2.5


def _empty_usage(mode: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "runs": 0,
        "api_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "actual_cost_usd": 0.0,
        "estimated_cost_available": False,
        "actual_cost_available": False,
        "gpt56_sol_estimated_cost_usd": 0.0,
    }


def _gpt56_sol_cost_breakdown(usage: dict[str, Any]) -> dict[str, float]:
    unit = float(GPT56_SOL_PRICING["unit_tokens"])
    input_cost = GPT56_SOL_USAGE_MULTIPLIER * (
        usage["input_tokens"]
        * GPT56_SOL_PRICING["input_usd_per_million"]
        / unit
    )
    cached_input_cost = GPT56_SOL_USAGE_MULTIPLIER * (
        usage["cache_read_tokens"]
        * GPT56_SOL_PRICING["cached_input_usd_per_million"]
        / unit
    )
    cache_write_cost = GPT56_SOL_USAGE_MULTIPLIER * (
        usage["cache_write_tokens"]
        * GPT56_SOL_PRICING["cache_write_usd_per_million"]
        / unit
    )
    output_cost = GPT56_SOL_USAGE_MULTIPLIER * (
        usage["output_tokens"]
        * GPT56_SOL_PRICING["output_usd_per_million"]
        / unit
    )
    return {
        "input_usd": round(input_cost, 8),
        "cached_input_usd": round(cached_input_cost, 8),
        "cache_write_usd": round(cache_write_cost, 8),
        "output_usd": round(output_cost, 8),
        "total_usd": round(
            input_cost + cached_input_cost + cache_write_cost + output_cost,
            8,
        ),
    }


class TokenAnalytics:
    """Read Hermes usage ledgers without writing to Hermes state databases."""

    def __init__(self, config: AppConfig):
        self.sources = (
            ("restricted_batch", config.hermes.home / "state.db"),
            ("trusted_full", config.trusted_full.home / "state.db"),
        )

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        uri = path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _has_usage_schema(connection: sqlite3.Connection) -> bool:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        return {"sessions", "session_model_usage"}.issubset(tables)

    def _read_source(self, mode: str, path: Path) -> dict[str, Any]:
        usage = _empty_usage(mode)
        usage["database"] = str(path)
        usage["available"] = False
        usage["daily"] = []
        usage["models"] = []
        usage["first_seen"] = None
        usage["last_seen"] = None
        if not path.is_file():
            return usage

        try:
            with closing(self._connect(path)) as connection:
                if not self._has_usage_schema(connection):
                    return usage
                row = connection.execute(
                    """SELECT
                    COUNT(DISTINCT u.session_id) AS runs,
                    COALESCE(SUM(u.api_call_count), 0) AS api_calls,
                    COALESCE(SUM(u.input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(u.output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(u.cache_read_tokens), 0) AS cache_read_tokens,
                    COALESCE(SUM(u.cache_write_tokens), 0) AS cache_write_tokens,
                    COALESCE(SUM(u.reasoning_tokens), 0) AS reasoning_tokens,
                    COALESCE(SUM(u.estimated_cost_usd), 0) AS estimated_cost_usd,
                    COALESCE(SUM(u.actual_cost_usd), 0) AS actual_cost_usd,
                    COUNT(u.estimated_cost_usd) AS estimated_cost_rows,
                    COUNT(u.actual_cost_usd) AS actual_cost_rows,
                    MIN(u.first_seen) AS first_seen,
                    MAX(u.last_seen) AS last_seen
                    FROM session_model_usage u
                    JOIN sessions s ON s.id=u.session_id
                    WHERE s.source='tool'"""
                ).fetchone()
                if row is None:
                    return usage
                for field in ("runs", "api_calls", *TOKEN_FIELDS):
                    usage[field] = int(row[field] or 0)
                usage["total_tokens"] = (
                    usage["input_tokens"] + usage["output_tokens"]
                )
                usage["gpt56_sol_estimated_cost_usd"] = (
                    _gpt56_sol_cost_breakdown(usage)["total_usd"]
                )
                usage["estimated_cost_usd"] = round(
                    float(row["estimated_cost_usd"] or 0), 8
                )
                usage["actual_cost_usd"] = round(
                    float(row["actual_cost_usd"] or 0), 8
                )
                usage["estimated_cost_available"] = bool(
                    row["estimated_cost_rows"]
                )
                usage["actual_cost_available"] = bool(row["actual_cost_rows"])
                usage["first_seen"] = self._timestamp(row["first_seen"])
                usage["last_seen"] = self._timestamp(row["last_seen"])
                usage["daily"] = [
                    {
                        "date": item["day"],
                        "input_tokens": int(item["input_tokens"] or 0),
                        "output_tokens": int(item["output_tokens"] or 0),
                    }
                    for item in connection.execute(
                        """SELECT date(u.last_seen, 'unixepoch') AS day,
                        COALESCE(SUM(u.input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(u.output_tokens), 0) AS output_tokens
                        FROM session_model_usage u
                        JOIN sessions s ON s.id=u.session_id
                        WHERE s.source='tool'
                        GROUP BY day ORDER BY day DESC LIMIT 14"""
                    ).fetchall()[::-1]
                ]
                usage["models"] = [
                    {
                        "model": item["model"] or "unknown",
                        "runs": int(item["runs"] or 0),
                        "input_tokens": int(item["input_tokens"] or 0),
                        "output_tokens": int(item["output_tokens"] or 0),
                        "estimated_cost_usd": round(
                            float(item["estimated_cost_usd"] or 0), 8
                        ),
                    }
                    for item in connection.execute(
                        """SELECT u.model, COUNT(DISTINCT u.session_id) AS runs,
                        COALESCE(SUM(u.input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(u.output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(u.input_tokens), 0) +
                            COALESCE(SUM(u.output_tokens), 0) AS total_tokens,
                        COALESCE(SUM(u.estimated_cost_usd), 0) AS estimated_cost_usd
                        FROM session_model_usage u
                        JOIN sessions s ON s.id=u.session_id
                        WHERE s.source='tool'
                        GROUP BY u.model ORDER BY total_tokens DESC"""
                    )
                ]
                usage["available"] = True
        except sqlite3.Error as exc:
            usage["error"] = f"{type(exc).__name__}: {exc}"
        return usage

    @staticmethod
    def _timestamp(value: Any) -> str | None:
        if value is None:
            return None
        try:
            return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            return str(value)

    def summary(self) -> dict[str, Any]:
        modes = [
            self._read_source(mode, path)
            for mode, path in self.sources
        ]
        total = _empty_usage("all")
        total["available"] = any(mode["available"] for mode in modes)
        total["estimated_cost_available"] = any(
            mode["estimated_cost_available"] for mode in modes
        )
        total["actual_cost_available"] = any(
            mode["actual_cost_available"] for mode in modes
        )
        for mode in modes:
            for field in ("runs", "api_calls", *TOKEN_FIELDS):
                total[field] += mode[field]
            total["estimated_cost_usd"] += mode["estimated_cost_usd"]
            total["actual_cost_usd"] += mode["actual_cost_usd"]
        total["total_tokens"] = total["input_tokens"] + total["output_tokens"]
        gpt56_sol_cost = _gpt56_sol_cost_breakdown(total)
        total["gpt56_sol_estimated_cost_usd"] = gpt56_sol_cost["total_usd"]
        total["estimated_cost_usd"] = round(total["estimated_cost_usd"], 8)
        total["actual_cost_usd"] = round(total["actual_cost_usd"], 8)

        daily: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"input_tokens": 0, "output_tokens": 0}
        )
        models: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "runs": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_usd": 0.0,
            }
        )
        for mode in modes:
            for item in mode["daily"]:
                daily[item["date"]]["input_tokens"] += item["input_tokens"]
                daily[item["date"]]["output_tokens"] += item["output_tokens"]
            for item in mode["models"]:
                model = models[item["model"]]
                model["runs"] += item["runs"]
                model["input_tokens"] += item["input_tokens"]
                model["output_tokens"] += item["output_tokens"]
                model["estimated_cost_usd"] += item["estimated_cost_usd"]

        first_seen = min(
            (mode["first_seen"] for mode in modes if mode["first_seen"]),
            default=None,
        )
        last_seen = max(
            (mode["last_seen"] for mode in modes if mode["last_seen"]),
            default=None,
        )
        return {
            "available": total["available"],
            "measurement_source": "Hermes state.db / session_model_usage",
            "scope": "source=tool in project-isolated Hermes profiles",
            "currency": "USD",
            "pricing": {
                **GPT56_SOL_PRICING,
                "usage_multiplier": GPT56_SOL_USAGE_MULTIPLIER,
                "cost_breakdown": gpt56_sol_cost,
            },
            "estimate_scope": {
                "kind": "fixed_multiplier_estimate",
                "coverage": "Hermes source=tool sessions only",
                "interpretation": "experience_adjusted_gpt56_sol_equivalent",
            },
            "total": total,
            "modes": modes,
            "daily": [
                {"date": date, **values}
                for date, values in sorted(daily.items())[-14:]
            ],
            "models": [
                {
                    "model": name,
                    **values,
                    "estimated_cost_usd": round(
                        values["estimated_cost_usd"], 8
                    ),
                }
                for name, values in sorted(
                    models.items(),
                    key=lambda item: (
                        item[1]["input_tokens"] + item[1]["output_tokens"]
                    ),
                    reverse=True,
                )
            ],
            "period": {"first_seen": first_seen, "last_seen": last_seen},
            "cost_note": (
                "GPT-5.6 Sol equivalent cost uses OpenAI standard short-context "
                "rates: $5/M input, $0.50/M cached input, $6.25/M cache writes, "
                "and $30/M output, with a fixed 2.5 usage multiplier. Reasoning "
                "tokens are a subset of output tokens and are not double-counted. "
                "Local inference normally has no API charge; actual_cost_usd is "
                "shown separately."
            ),
        }
