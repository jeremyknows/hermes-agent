from __future__ import annotations

from pathlib import Path
import re

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE_PATH = REPO_ROOT / "plans/specs/2026-05-24-memory-seam-control-plane-v0.yaml"
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/memory_seam/read_receipt_v0_compat_fixture.yaml"
EXPECTED_RECEIPT_CLASSES = {
    "allowed_receipt",
    "denied_before_read_receipt",
    "degraded_not_useful_receipt",
    "no_authority_no_source_read_posture",
}
FORBIDDEN_VALUE_PATTERNS = [
    re.compile("/" + "Users/"),
    re.compile("op" + "://"),
    re.compile("sk" + r"-[A-Za-z0-9]"),
    re.compile(r"\b\d{8,}\b"),
]


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict), f"expected mapping in {path}"
    return data


def _load_control_plane() -> dict:
    return _load_yaml(CONTROL_PLANE_PATH)


def _load_fixture() -> dict:
    return _load_yaml(FIXTURE_PATH)


def _iter_scalar_strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_scalar_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_scalar_strings(item)
    elif isinstance(value, str):
        yield value


def test_read_receipt_fixture_covers_required_receipt_classes() -> None:
    fixture = _load_fixture()

    assert fixture["fixture_version"] == "memory_seam_read_receipt_v0_fixture"

    receipts = fixture["receipts"]
    assert len(receipts) == 4
    assert {receipt["receipt_class"] for receipt in receipts} == EXPECTED_RECEIPT_CLASSES


def test_read_receipt_fixture_matches_control_plane_schema() -> None:
    control_plane = _load_control_plane()
    fixture = _load_fixture()

    schema = control_plane["sanitized_receipt_schema"]
    required_fields = schema["required_fields"]
    examples = schema["examples"]

    for receipt in fixture["receipts"]:
        assert set(required_fields).issubset(receipt)
        assert receipt["receipt_version"] == examples["metadata_only_deny"]["receipt_version"]
        assert receipt["decision"] in required_fields["decision"]["allowed_values"]
        assert receipt["latency_bucket"] in required_fields["latency_bucket"]["allowed_values"]
        assert receipt["cache_action"] in required_fields["cache_action"]["allowed_values"]
        assert isinstance(receipt["byte_counts"]["before"], int)
        assert isinstance(receipt["byte_counts"]["after"], int)
        assert isinstance(receipt["byte_counts"]["truncated"], bool)
        if receipt["decision"] in {"deny", "degrade_metadata_only"}:
            assert isinstance(receipt["degraded_label"], str)
        else:
            assert receipt["degraded_label"] is None


def test_read_receipt_fixture_preserves_static_receipt_semantics() -> None:
    fixture = _load_fixture()
    receipts = {receipt["case_id"]: receipt for receipt in fixture["receipts"]}

    assert receipts["allow_metadata_receipt"]["backend_callback_count"] == 1
    assert receipts["allow_metadata_receipt"]["decision"] == "allow_metadata"

    assert receipts["denied_before_read_receipt"]["decision"] == "deny"
    assert receipts["denied_before_read_receipt"]["backend_callback_count"] == 0
    assert receipts["denied_before_read_receipt"]["byte_counts"] == {
        "before": 0,
        "after": 0,
        "truncated": False,
    }

    assert receipts["degraded_not_useful_receipt"]["decision"] == "degrade_metadata_only"
    assert receipts["degraded_not_useful_receipt"]["degraded_label"] == "not_useful_enough"

    assert receipts["no_authority_no_source_read_receipt"]["decision"] == "deny"
    assert receipts["no_authority_no_source_read_receipt"]["degraded_label"] == "no_authority"
    assert receipts["no_authority_no_source_read_receipt"]["backend_callback_count"] == 0


def test_read_receipt_fixture_is_metadata_only_and_scanner_clean() -> None:
    control_plane = _load_control_plane()
    fixture = _load_fixture()

    forbidden_fields = set(control_plane["audit_receipts"]["forbidden"])
    for receipt in fixture["receipts"]:
        assert forbidden_fields.isdisjoint(receipt.keys())

    for value in _iter_scalar_strings(fixture):
        for pattern in FORBIDDEN_VALUE_PATTERNS:
            assert not pattern.search(value), value
