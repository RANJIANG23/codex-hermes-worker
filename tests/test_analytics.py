from __future__ import annotations

import sqlite3
from pathlib import Path

from codex_hermes_worker.analytics import TokenAnalytics
from codex_hermes_worker.bridge.config import load_config


def _create_usage_database(
    directory: Path,
    rows: list[tuple[str, str, str, int, int, int, float, float | None, float]],
) -> None:
    directory.mkdir(parents=True)
    connection = sqlite3.connect(directory / "state.db")
    try:
        connection.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0
            );
            CREATE TABLE session_model_usage (
                session_id TEXT NOT NULL,
                model TEXT,
                api_call_count INTEGER,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cache_read_tokens INTEGER,
                cache_write_tokens INTEGER,
                reasoning_tokens INTEGER,
                estimated_cost_usd REAL,
                actual_cost_usd REAL,
                first_seen REAL,
                last_seen REAL
            );
            """
        )
        for (
            session_id,
            source,
            model,
            input_tokens,
            output_tokens,
            api_calls,
            estimated_cost,
            actual_cost,
            timestamp,
        ) in rows:
            connection.execute(
                "INSERT INTO sessions (id, source) VALUES (?, ?)",
                (session_id, source),
            )
            connection.execute(
                """INSERT INTO session_model_usage (
                    session_id, model, api_call_count, input_tokens,
                    output_tokens, cache_read_tokens, cache_write_tokens,
                    reasoning_tokens, estimated_cost_usd, actual_cost_usd,
                    first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    model,
                    api_calls,
                    input_tokens,
                    output_tokens,
                    10,
                    5,
                    2,
                    estimated_cost,
                    actual_cost,
                    timestamp,
                    timestamp,
                ),
            )
        connection.commit()
    finally:
        connection.close()


def test_token_analytics_merges_tool_sessions_and_excludes_cli(
    tmp_path: Path,
) -> None:
    restricted = tmp_path / "restricted"
    trusted = tmp_path / "trusted"
    _create_usage_database(
        restricted,
        [
            (
                "restricted-tool",
                "tool",
                "qwen-local",
                100,
                25,
                2,
                0.01,
                0.0,
                1_750_000_000,
            ),
            (
                "ignored-cli",
                "cli",
                "qwen-local",
                999,
                999,
                1,
                9.99,
                9.99,
                1_750_000_000,
            ),
        ],
    )
    _create_usage_database(
        trusted,
        [
            (
                "trusted-tool",
                "tool",
                "qwen-local",
                50,
                10,
                1,
                0.005,
                None,
                1_750_086_400,
            ),
        ],
    )
    config = load_config().model_copy(deep=True)
    config.hermes.home = restricted
    config.trusted_full.home = trusted

    summary = TokenAnalytics(config).summary()

    assert summary["available"] is True
    assert summary["total"]["runs"] == 2
    assert summary["total"]["api_calls"] == 3
    assert summary["total"]["input_tokens"] == 150
    assert summary["total"]["output_tokens"] == 35
    assert summary["total"]["total_tokens"] == 185
    assert summary["total"]["estimated_cost_usd"] == 0.015
    assert summary["total"]["actual_cost_usd"] == 0.0
    assert summary["total"]["actual_cost_available"] is True
    assert summary["total"]["gpt56_sol_estimated_cost_usd"] == 0.00468125
    assert summary["pricing"]["model"] == "gpt-5.6-sol"
    assert summary["pricing"]["input_usd_per_million"] == 5.0
    assert summary["pricing"]["output_usd_per_million"] == 30.0
    assert summary["pricing"]["usage_multiplier"] == 2.5
    assert summary["pricing"]["cost_breakdown"] == {
        "input_usd": 0.001875,
        "cached_input_usd": 0.000025,
        "cache_write_usd": 0.00015625,
        "output_usd": 0.002625,
        "total_usd": 0.00468125,
    }
    assert [mode["mode"] for mode in summary["modes"]] == [
        "restricted_batch",
        "trusted_full",
    ]
    assert len(summary["daily"]) == 2
    assert summary["models"][0]["model"] == "qwen-local"
    assert summary["models"][0]["runs"] == 2


def test_token_analytics_handles_missing_ledgers(tmp_path: Path) -> None:
    config = load_config().model_copy(deep=True)
    config.hermes.home = tmp_path / "missing-restricted"
    config.trusted_full.home = tmp_path / "missing-trusted"

    summary = TokenAnalytics(config).summary()

    assert summary["available"] is False
    assert summary["total"]["total_tokens"] == 0
    assert summary["total"]["gpt56_sol_estimated_cost_usd"] == 0.0
    assert summary["daily"] == []
