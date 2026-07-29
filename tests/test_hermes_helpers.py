from __future__ import annotations

import pytest

from codex_hermes_worker.bridge.hermes_client import extract_json
from codex_hermes_worker.policies.limits import bounded_limit, truncate_text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('{"ok":true}', {"ok": True}),
        ('<json>{"ok":true}</json>\nsession_id: x', {"ok": True}),
        ('```json\n{"ok": true}\n```', {"ok": True}),
        ('prefix {"ok":true} suffix', {"ok": True}),
    ],
)
def test_extract_json(value: str, expected: dict) -> None:
    assert extract_json(value) == expected


def test_extract_json_rejects_unstructured_text() -> None:
    with pytest.raises(ValueError):
        extract_json("not json")


def test_limits() -> None:
    value, truncated = truncate_text("abcdef", 5)
    assert truncated is True
    assert len(value) <= 31
    assert bounded_limit(500, 20, 100) == 100

