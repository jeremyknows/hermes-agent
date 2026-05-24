from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE_PATH = REPO_ROOT / "plans/specs/2026-05-24-memory-seam-control-plane-v0.yaml"
FIXTURE_DIR = REPO_ROOT / "tests/fixtures/memory_seam"


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict), f"expected mapping in {path}"
    return data


def _load_control_plane() -> dict:
    return _load_yaml(CONTROL_PLANE_PATH)


def _load_fixture(name: str) -> dict:
    return _load_yaml(FIXTURE_DIR / name)


def _evaluate_wiki_fixture_access(
    control_plane: dict,
    *,
    subject: str,
    mode: str,
    family_enabled: bool = True,
    reportable_output_requested: bool = False,
    public_artifact_lock: bool = False,
) -> dict:
    family = control_plane["source_families"]["wiki_gbrain"]
    sax_grant = control_plane["grant_matrix"]["sax"]["wiki_gbrain"]

    if not family_enabled:
        return {
            "decision": "deny",
            "degraded_label": family["rollback_semantics"]["disable_label"],
        }

    if public_artifact_lock and reportable_output_requested:
        return {
            "decision": "deny",
            "degraded_label": control_plane["kill_switches"]["public_artifact_lock"]["degraded_label"],
        }

    if subject == "network_multi_user_multi_machine":
        return {"decision": "deny", "degraded_label": "verifier_required"}

    if subject != "sax":
        return {"decision": "deny", "degraded_label": "grant_missing"}

    if mode not in sax_grant["modes"]:
        return {"decision": "deny", "degraded_label": "grant_mode_denied"}

    return {
        "decision": "allow_metadata",
        "redaction_profile": family["redaction_profile"],
        "cache_namespace": family["rollback_semantics"]["cache_namespace"],
    }


def test_wiki_registry_fixture_matches_control_plane_source_family() -> None:
    control_plane = _load_control_plane()
    fixture = _load_fixture("wiki_gbrain_registry_fixture.yaml")

    family = control_plane["source_families"][fixture["family_id"]]

    assert family["owner"] == fixture["owner"]
    assert family["allowed_scopes"] == fixture["allowed_scopes"]
    assert family["private_class"] == fixture["private_class"]
    assert family["redaction_profile"] == fixture["redaction_profile"]
    assert family["allowed_posture"] == fixture["allowed_posture"]
    assert family["fallback_labels"] == fixture["fallback_labels"]
    assert family["public_artifact_policy"] == fixture["public_artifact_policy"]
    assert family["rollback_semantics"] == fixture["rollback_semantics"]


def test_wiki_grant_fixture_matches_sax_grant_row() -> None:
    control_plane = _load_control_plane()
    fixture = _load_fixture("wiki_gbrain_grant_fixture.yaml")

    grant = control_plane["grant_matrix"][fixture["subject"]][fixture["source_family"]]
    defaults = control_plane["defaults"]

    assert grant["decision"] == fixture["decision"]
    assert grant["modes"] == fixture["modes"]
    assert grant["denied_modes"] == fixture["denied_modes"]
    assert defaults["posture"] == fixture["posture"]

    allow_result = _evaluate_wiki_fixture_access(
        control_plane,
        subject=fixture["subject"],
        mode="supervised",
    )
    assert allow_result == fixture["expected_allow"]


def test_wiki_fail_closed_negative_fixtures_stay_denied() -> None:
    control_plane = _load_control_plane()
    fixture = _load_fixture("wiki_gbrain_grant_fixture.yaml")

    required_denies = {
        (
            case["subject"],
            case["source_family"],
            case["mode"],
        ): case["degraded_label"]
        for case in control_plane["evaluator_contract"]["required_deny_examples"]
        if case["source_family"] == "wiki_gbrain"
    }

    assert required_denies[("builder", "wiki_gbrain", "supervised")] == "grant_missing"
    assert (
        required_denies[("network_multi_user_multi_machine", "wiki_gbrain", "runtime")]
        == "verifier_required"
    )

    for case in fixture["fail_closed_cases"]:
        result = _evaluate_wiki_fixture_access(
            control_plane,
            subject=case["subject"],
            mode=case["mode"],
            family_enabled=case.get("family_enabled", True),
            reportable_output_requested=case.get("reportable_output_requested", False),
            public_artifact_lock=case.get("public_artifact_lock", False),
        )
        assert result["decision"] == "deny", case["case_id"]
        assert result["degraded_label"] == case["expected_degraded_label"], case["case_id"]

    acceptance_cases = control_plane["evaluator_contract"]["evaluator_only_acceptance_cases"]
    assert (
        acceptance_cases["source_family_kill_switch_deny"]["expected_degraded_label"]
        == "source_family_disabled"
    )
    assert (
        acceptance_cases["public_artifact_lock_deny"]["expected_degraded_label"]
        == "public_artifact_locked"
    )
