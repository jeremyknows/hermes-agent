from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import wiki_include_tool as wiki
from tools.tool_result_storage import maybe_persist_tool_result


def _cfg(
    root: Path,
    path: Path,
    *,
    source: str = "atlas-wiki",
    subject: str = "atlas-overview",
    title: str = "Atlas Overview",
    why_included: str | None = None,
    open_hint: str | None = None,
):
    descriptor = {
        "id": "atlas-public-overview",
        "family": "wiki",
        "subject": subject,
        "path": str(path),
        "source": source,
        "privacy": "least_sensitive",
        "title": title,
    }
    if why_included is not None:
        descriptor["why_included"] = why_included
    if open_hint is not None:
        descriptor["open_hint"] = open_hint
    return {
        "enabled": True,
        "allowed_roots": [str(root)],
        "allowlist": [descriptor],
    }


def test_allowed_wiki_read_succeeds_with_labels_and_safe_path(tmp_path):
    root = tmp_path / "wiki"
    root.mkdir()
    page = root / "atlas-overview.md"
    page.write_text("Atlas public overview\n", encoding="utf-8")

    result = wiki.read_wiki_include(
        "atlas-public-overview",
        "atlas-overview",
        config=_cfg(root, page),
    )

    assert result["success"] is True
    assert result["source"] == "atlas-wiki"
    assert result["privacy"] == "least_sensitive"
    assert result["freshness"].endswith("Z")
    assert result["degraded"] is False
    assert result["degraded_reason"] is None
    assert result["path"] == "wiki:atlas-overview.md"
    assert result["content"] == "Atlas public overview\n"
    assert str(tmp_path) not in result["path"]

    card = result["source_card"]
    assert card == {
        "family": "wiki",
        "title": "Atlas Overview",
        "display_path": "wiki:atlas-overview.md",
        "locator": "wiki-include:atlas-public-overview",
        "freshness": result["freshness"],
        "privacy": "least_sensitive",
        "confidence": "high",
        "degraded": False,
        "why_included": "Allowlisted wiki include 'atlas-public-overview' matched subject 'atlas-overview' exactly",
        "open_hint": 'wiki_include_read(include_id="atlas-public-overview", subject="atlas-overview")',
    }
    assert result["source_card_compact"].startswith("[wiki] Atlas Overview · wiki:atlas-overview.md")
    assert "confidence=high" in result["source_card_compact"]
    assert result["source_card_compact"].endswith("· ok")


def test_include_subject_mismatch_rejects_before_read_and_leaks_no_card(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    root.mkdir()
    page = root / "atlas-overview.md"
    cfg = _cfg(root, page)

    def fail_read(*args, **kwargs):  # pragma: no cover - failure path assertion
        raise AssertionError("read_text should not be called")

    monkeypatch.setattr(Path, "read_text", fail_read)
    monkeypatch.setattr(wiki, "_load_memory_seam_wiki_config", lambda: cfg)

    payload = json.loads(
        wiki.handle_wiki_include(
            {
                "include_id": "atlas-public-overview",
                "subject": "wrong-subject",
            }
        )
    )
    assert payload["success"] is False
    assert payload["degraded_reason"] == "policy_rejected_before_read"
    assert "source_card" not in payload
    assert "path" not in payload
    assert "wrong-subject" not in payload["error"]

    with pytest.raises(wiki.WikiIncludeError, match="include/subject mismatch"):
        wiki.read_wiki_include(
            "atlas-public-overview",
            "wrong-subject",
            config=_cfg(root, page),
        )


def test_protected_private_path_rejects_before_read_and_leaks_no_private_path(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    protected = root / "private" / "atlas-overview.md"
    cfg = _cfg(root, protected)

    def fail_read(*args, **kwargs):  # pragma: no cover - failure path assertion
        raise AssertionError("read_text should not be called")

    monkeypatch.setattr(Path, "read_text", fail_read)
    monkeypatch.setattr(wiki, "_load_memory_seam_wiki_config", lambda: cfg)

    payload = json.loads(
        wiki.handle_wiki_include(
            {
                "include_id": "atlas-public-overview",
                "subject": "atlas-overview",
            }
        )
    )
    assert payload["success"] is False
    assert payload["degraded_reason"] == "policy_rejected_before_read"
    assert "source_card" not in payload
    assert "path" not in payload
    assert str(tmp_path) not in payload["error"]

    with pytest.raises(wiki.WikiIncludeError, match="protected/private path"):
        wiki.read_wiki_include(
            "atlas-public-overview",
            "atlas-overview",
            config=_cfg(root, protected),
        )


def test_output_redacts_obvious_sensitive_values_and_keeps_source_card(tmp_path):
    root = tmp_path / "wiki"
    root.mkdir()
    page = root / "public.md"
    page.write_text(
        "Contact owner@example.com\n"
        "api_key=sk-live-test\n"
        "Authorization: Bearer abcdefghijk\n",
        encoding="utf-8",
    )

    result = wiki.read_wiki_include(
        "atlas-public-overview",
        "atlas-overview",
        config=_cfg(root, page, title="Public Note"),
    )

    assert "owner@example.com" not in result["content"]
    assert "sk-live-test" not in result["content"]
    assert "abcdefghijk" not in result["content"]
    assert "[REDACTED_EMAIL]" in result["content"]
    assert "[REDACTED]" in result["content"]
    assert str(tmp_path) not in result["path"]
    assert result["source_card"]["title"] == "Public Note"
    assert result["source_card"]["display_path"] == "wiki:public.md"


def test_source_card_survives_tool_result_truncation(tmp_path):
    root = tmp_path / "wiki"
    root.mkdir()
    page = root / "atlas-overview.md"
    page.write_text("Header\n" + ("body line\n" * 600), encoding="utf-8")

    result = wiki.read_wiki_include(
        "atlas-public-overview",
        "atlas-overview",
        config=_cfg(root, page, title="Atlas Overview"),
    )
    serialized = json.dumps(result, ensure_ascii=False)
    persisted = maybe_persist_tool_result(
        serialized,
        tool_name="wiki_include_read",
        tool_use_id="wiki-source-card-preview",
        env=None,
        threshold=250,
    )

    assert '"source_card"' in persisted
    assert '"display_path": "wiki:atlas-overview.md"' in persisted
    assert '"content"' not in persisted or persisted.index('"source_card"') < persisted.index('"content"')
    assert str(tmp_path) not in persisted


def test_missing_source_label_marks_card_degraded(tmp_path):
    root = tmp_path / "wiki"
    root.mkdir()
    page = root / "public.md"
    page.write_text("Public atlas note\n", encoding="utf-8")

    result = wiki.read_wiki_include(
        "atlas-public-overview",
        "atlas-overview",
        config=_cfg(root, page, source=""),
    )

    assert result["success"] is True
    assert result["source"] == "wiki:no_source_label"
    assert result["degraded"] is True
    assert result["degraded_reason"] == "descriptor missing source label"
    assert result["source_card"]["degraded"] is True
    assert result["source_card"]["confidence"] == "low"
    assert result["source_card_compact"].endswith("· degraded")


def test_disabled_or_missing_source_returns_degraded_no_read(tmp_path, monkeypatch):
    page = tmp_path / "wiki" / "missing.md"

    def fail_read(*args, **kwargs):  # pragma: no cover - failure path assertion
        raise AssertionError("read_text should not be called")

    monkeypatch.setattr(Path, "read_text", fail_read)

    disabled = wiki.read_wiki_include("anything", "anything", config={"enabled": False})
    assert disabled["success"] is False
    assert disabled["degraded"] is True
    assert disabled["degraded_reason"] == "memory_seam.wiki disabled"
    assert "source_card" not in disabled

    missing = wiki.read_wiki_include(
        "atlas-public-overview",
        "atlas-overview",
        config=_cfg(tmp_path / "wiki", page),
    )
    assert missing["success"] is False
    assert missing["degraded"] is True
    assert missing["degraded_reason"] == "allowlisted wiki source is missing"
    assert missing["path"] == "wiki:missing.md"
    assert missing["source_card"]["degraded"] is True
    assert missing["source_card"]["confidence"] == "medium"
    assert missing["source_card_compact"].startswith("[wiki] Atlas Overview · wiki:missing.md")


def test_compact_source_card_renderer_is_docs_friendly():
    compact = wiki.format_source_card_compact(
        {
            "family": "wiki",
            "title": "Atlas Overview",
            "display_path": "wiki:atlas-overview.md",
            "freshness": "2026-05-23T12:00:00Z",
            "privacy": "least_sensitive",
            "confidence": "high",
            "degraded": False,
        }
    )

    assert compact == (
        "[wiki] Atlas Overview · wiki:atlas-overview.md · least_sensitive"
        " · 2026-05-23T12:00:00Z · confidence=high · ok"
    )
