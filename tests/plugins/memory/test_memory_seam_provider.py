import json
import subprocess
import sys

from plugins.memory import load_memory_provider
from plugins.memory.memory_seam import MemorySeamMemoryProvider


def _script(tmp_path):
    path = tmp_path / "atlas-query.mcp.py"
    path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    return path


def test_memory_seam_provider_loads_from_plugin_discovery():
    provider = load_memory_provider("memory_seam")

    assert isinstance(provider, MemorySeamMemoryProvider)
    assert provider.name == "memory_seam"


def test_memory_seam_provider_is_local_only_available(tmp_path):
    script = _script(tmp_path)
    provider = MemorySeamMemoryProvider(atlas_query_script=str(script))

    assert provider.is_available() is True

    missing = MemorySeamMemoryProvider(atlas_query_script=str(tmp_path / "missing.py"))
    assert missing.is_available() is False


def test_memory_seam_provider_persists_native_config(tmp_path):
    script = _script(tmp_path)
    provider = MemorySeamMemoryProvider()

    provider.save_config(
        {
            "atlas_query_script": str(script),
            "default_timeout_ms": "2500",
        },
        str(tmp_path),
    )

    saved = json.loads((tmp_path / "memory_seam.json").read_text(encoding="utf-8"))
    assert saved == {
        "atlas_query_script": str(script),
        "default_timeout_ms": 2500,
    }


def test_memory_seam_provider_is_available_uses_effective_profile_config_pre_initialize(tmp_path, monkeypatch):
    script = _script(tmp_path)
    (tmp_path / "memory_seam.json").write_text(
        json.dumps({"atlas_query_script": str(script)}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    provider = MemorySeamMemoryProvider(atlas_query_script=str(tmp_path / "missing.py"))

    assert provider.is_available() is True
    assert provider._atlas_query_script == str(script)


def test_memory_seam_provider_exposes_only_read_only_tools(tmp_path):
    provider = MemorySeamMemoryProvider(atlas_query_script=str(_script(tmp_path)))
    schemas = provider.get_tool_schemas()

    assert [schema["name"] for schema in schemas] == [
        "memory_seam_health",
        "memory_seam_context",
        "memory_seam_recall",
    ]
    schema_text = json.dumps(schemas)
    assert "write" not in schema_text.lower()
    assert "reindex" not in schema_text.lower()
    assert "publish" not in schema_text.lower()


def test_memory_seam_provider_pull_mode_lifecycle_is_inert(tmp_path):
    provider = MemorySeamMemoryProvider(atlas_query_script=str(_script(tmp_path)))
    provider.initialize("session-1", hermes_home=str(tmp_path), platform="cli", agent_identity="sax")

    assert provider.prefetch("where are we?") == ""
    assert provider.queue_prefetch("where are we?") is None
    assert provider.sync_turn("remember this", "no write", session_id="session-1") is None
    assert provider.on_session_end([{"role": "user", "content": "secret"}]) is None

    provider.on_session_switch("session-2", reset=True)
    assert provider._session_id == "session-2"


def test_memory_seam_health_routes_to_local_cli_subprocess(tmp_path, monkeypatch):
    script = _script(tmp_path)
    provider = MemorySeamMemoryProvider(atlas_query_script=str(script))
    provider.initialize("session-1", hermes_home=str(tmp_path), platform="cli")
    calls = []

    def fake_run(cmd, *, capture_output, text, timeout, check):
        calls.append(cmd)
        assert capture_output is True
        assert text is True
        assert check is False
        assert timeout == 1.5
        return subprocess.CompletedProcess(cmd, 0, stdout='{"status":"degraded"}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = json.loads(provider.handle_tool_call("memory_seam_health", {}))

    assert result == {"status": "degraded"}
    assert calls == [[sys.executable, str(script), "memory_seam.health"]]


def test_memory_seam_context_builds_safe_no_live_cli_args(tmp_path, monkeypatch):
    script = _script(tmp_path)
    provider = MemorySeamMemoryProvider(atlas_query_script=str(script))
    provider.initialize("session-1", hermes_home=str(tmp_path), platform="cli")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"endpoint":"context","items":[]}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = json.loads(provider.handle_tool_call(
        "memory_seam_context",
        {
            "include": ["project"],
            "mode": "startup",
            "agent": "sax",
            "token_subject": "agent:admin",
            "allowed_scopes": "diary,session",
            "timeout_ms": 1500,
            "fixture_case": "sax_project_doc_granted",
            "read_receipt": "metadata_only",
        },
    ))

    assert result["endpoint"] == "context"
    assert calls == [[
        sys.executable,
        str(script),
        "memory_seam.context",
        "--include",
        "project",
        "--mode",
        "startup",
        "--agent",
        "sax",
        "--token-subject",
        "agent:sax",
        "--allowed-scopes",
        "project",
        "--timeout-ms",
        "1500",
        "--fixture-case",
        "sax_project_doc_granted",
        "--read-receipt",
        "metadata_only",
    ]]


def test_memory_seam_recall_builds_safe_cli_args(tmp_path, monkeypatch):
    script = _script(tmp_path)
    provider = MemorySeamMemoryProvider(atlas_query_script=str(script))
    provider.initialize("session-1", hermes_home=str(tmp_path), platform="cli")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"endpoint":"recall","items":[]}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = json.loads(provider.handle_tool_call(
        "memory_seam_recall",
        {
            "query": "memory seam boundary",
            "scope": "diary",
            "agent": "sax",
            "token_subject": "agent:admin",
            "allowed_scopes": "diary,session",
            "n": 3,
            "timeout_ms": 1200,
            "max_staleness": 86400,
            "read_receipt": "metadata_only",
        },
    ))

    assert result["endpoint"] == "recall"
    assert calls == [[
        sys.executable,
        str(script),
        "memory_seam.recall",
        "--query",
        "memory seam boundary",
        "--scope",
        "wiki",
        "--agent",
        "sax",
        "--n",
        "3",
        "--timeout-ms",
        "1200",
        "--max-staleness",
        "86400",
        "--read-receipt",
        "metadata_only",
    ]]


def test_memory_seam_provider_rejects_unknown_or_write_like_tools(tmp_path):
    provider = MemorySeamMemoryProvider(atlas_query_script=str(_script(tmp_path)))

    result = json.loads(provider.handle_tool_call("memory_seam_write", {"content": "nope"}))

    assert "error" in result
    assert "Unsupported" in result["error"]


def test_memory_seam_provider_returns_error_for_bad_integer_args(tmp_path, monkeypatch):
    provider = MemorySeamMemoryProvider(atlas_query_script=str(_script(tmp_path)))
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = json.loads(provider.handle_tool_call(
        "memory_seam_recall",
        {"query": "memory seam", "n": "not-an-int"},
    ))

    assert "error" in result
    assert "Invalid integer" in result["error"]
    assert calls == []


def test_memory_seam_provider_clamps_timeout_for_cli_and_subprocess(tmp_path, monkeypatch):
    script = _script(tmp_path)
    provider = MemorySeamMemoryProvider(atlas_query_script=str(script))
    calls = []
    timeouts = []

    def fake_run(cmd, *, timeout, **kwargs):
        calls.append(cmd)
        timeouts.append(timeout)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"status":"degraded"}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = json.loads(provider.handle_tool_call(
        "memory_seam_health",
        {"timeout_ms": 999999999},
    ))

    assert result["status"] == "degraded"
    assert timeouts == [10.0]

    json.loads(provider.handle_tool_call(
        "memory_seam_context",
        {"timeout_ms": 999999999},
    ))
    assert calls[-1] == [
        sys.executable,
        str(script),
        "memory_seam.context",
        "--timeout-ms",
        "10000",
    ]


def test_memory_seam_provider_rejects_bad_health_timeout(tmp_path, monkeypatch):
    provider = MemorySeamMemoryProvider(atlas_query_script=str(_script(tmp_path)))
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = json.loads(provider.handle_tool_call(
        "memory_seam_health",
        {"timeout_ms": "bad"},
    ))

    assert "error" in result
    assert "Invalid integer" in result["error"]
    assert calls == []


def test_memory_seam_provider_reports_cli_non_zero_exit(tmp_path, monkeypatch):
    provider = MemorySeamMemoryProvider(atlas_query_script=str(_script(tmp_path)))

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 7, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = json.loads(provider.handle_tool_call("memory_seam_health", {}))

    assert result["error"] == "Memory Seam CLI returned non-zero exit status"
    assert result["returncode"] == 7
    assert result["detail"] == "boom"


def test_memory_seam_provider_reports_cli_empty_output(tmp_path, monkeypatch):
    provider = MemorySeamMemoryProvider(atlas_query_script=str(_script(tmp_path)))

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="   ", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = json.loads(provider.handle_tool_call("memory_seam_health", {}))

    assert result["error"] == "Memory Seam CLI returned empty output"


def test_memory_seam_provider_reports_cli_invalid_json(tmp_path, monkeypatch):
    provider = MemorySeamMemoryProvider(atlas_query_script=str(_script(tmp_path)))

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="not-json", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = json.loads(provider.handle_tool_call("memory_seam_health", {}))

    assert result["error"] == "Memory Seam CLI returned invalid JSON"
    assert "Expecting value" in result["detail"]


def test_memory_seam_provider_clamps_configured_default_timeout(tmp_path, monkeypatch):
    script = _script(tmp_path)
    (tmp_path / "memory_seam.json").write_text(
        json.dumps({"default_timeout_ms": 999999999}),
        encoding="utf-8",
    )
    provider = MemorySeamMemoryProvider(atlas_query_script=str(script))
    provider.initialize("session-1", hermes_home=str(tmp_path), platform="cli")
    timeouts = []

    def fake_run(cmd, *, timeout, **kwargs):
        timeouts.append(timeout)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"status":"degraded"}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = json.loads(provider.handle_tool_call("memory_seam_health", {}))

    assert result["status"] == "degraded"
    assert timeouts == [10.0]
