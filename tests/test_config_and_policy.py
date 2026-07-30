from __future__ import annotations

from pathlib import Path

import pytest

from codex_hermes_worker.bridge.config import load_config
from codex_hermes_worker.bridge.hermes_client import HermesClient
from codex_hermes_worker.policies.filesystem import FilesystemPolicy, PolicyViolation
from codex_hermes_worker.worker_tools.deterministic import (
    file_metadata,
    search_file_names,
    search_text,
    text_excerpt,
)
from codex_hermes_worker.worker_tools.audit import rotate_audit_log


def test_config_paths_are_absolute() -> None:
    config = load_config()
    assert config.project_root.is_absolute()
    assert all(path.is_absolute() for path in config.filesystem.readable_roots)
    assert all(path.is_absolute() for path in config.filesystem.writable_roots)


def test_allowed_read_and_deterministic_metadata() -> None:
    config = load_config()
    policy = FilesystemPolicy(config)
    metadata = file_metadata(policy, "testdata/tool_loop/evidence.txt")
    assert metadata["sha256"]
    assert metadata["size"] > 0
    excerpt = text_excerpt(policy, "testdata/tool_loop/evidence.txt", 32)
    assert excerpt["truncated"] is True
    continued = text_excerpt(
        policy,
        "testdata/tool_loop/evidence.txt",
        32,
        excerpt["next_offset_chars"],
    )
    assert continued["offset_chars"] == 32
    assert continued["text"] != excerpt["text"]


def test_read_outside_roots_is_blocked() -> None:
    policy = FilesystemPolicy(load_config())
    with pytest.raises(PolicyViolation):
        policy.resolve_read(Path.home() / ".ssh" / "id_rsa", must_exist=False)


def test_write_outside_roots_is_blocked() -> None:
    policy = FilesystemPolicy(load_config())
    with pytest.raises(PolicyViolation):
        policy.resolve_write(Path.home() / "blocked-output.txt")


def test_binary_slice_limit_is_enforced() -> None:
    policy = FilesystemPolicy(load_config())
    from codex_hermes_worker.worker_tools.deterministic import binary_slice

    result = binary_slice(
        policy,
        "testdata/tool_loop/evidence.txt",
        0,
        policy.config.filesystem.maximum_binary_slice * 2,
    )
    assert result["length"] <= policy.config.filesystem.maximum_binary_slice


def test_bounded_filename_and_text_search() -> None:
    policy = FilesystemPolicy(load_config())
    names = search_file_names(policy, "testdata/tool_loop", "evidence", 10)
    assert names["matches"][0]["path"].endswith("evidence.txt")
    glob_names = search_file_names(policy, "testdata/tool_loop", "*.txt", 10)
    assert glob_names["matches"][0]["path"].endswith("evidence.txt")
    content = search_text(policy, "testdata/tool_loop", "QWEN_TWO_TOOL_CHAIN_OK", 10)
    assert content["matches"][0]["line"] >= 1
    single_file = search_text(
        policy,
        "testdata/tool_loop/evidence.txt",
        "QWEN_TWO_TOOL_CHAIN_OK",
        10,
    )
    assert single_file["matches"][0]["path"].endswith("evidence.txt")


def test_audit_log_rotates_at_configured_limit(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text("x" * 32, encoding="utf-8")
    rotate_audit_log(path, 16)
    assert not path.exists()
    assert path.with_suffix(".jsonl.1").read_text(encoding="utf-8") == "x" * 32


def test_trusted_full_requires_explicit_authorization() -> None:
    config = load_config()
    client = HermesClient(config)
    with pytest.raises(PermissionError, match="explicit authorization"):
        client.run_trusted(
            "Do nothing.",
            working_directory=str(config.project_root),
            requested_toolsets=["terminal"],
            allow_network=False,
            include_optional_tools=False,
            max_steps=1,
            timeout=5,
            authorization="not_authorized",
        )


def test_trusted_full_network_tools_require_separate_opt_in() -> None:
    config = load_config()
    client = HermesClient(config)
    with pytest.raises(PermissionError, match="allow_network=true"):
        client.run_trusted(
            "Do nothing.",
            working_directory=str(config.project_root),
            requested_toolsets=["web"],
            allow_network=False,
            include_optional_tools=False,
            max_steps=1,
            timeout=5,
            authorization="explicit_user_authorized",
        )


def test_inference_key_source_is_not_inherited_by_hermes_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LMSTUDIO_API_KEY", "unit-test-secret")
    config = load_config()
    client = HermesClient(config)
    env = client._environment(config.trusted_full.home)
    assert "LMSTUDIO_API_KEY" not in env
    assert env["OPENAI_API_KEY"] == "unit-test-secret"
    assert env["OPENROUTER_API_KEY"] == "unit-test-secret"
