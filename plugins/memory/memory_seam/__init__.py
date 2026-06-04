"""Memory Seam memory plugin.

A tools-first, pull-based provider that exposes the Atlas Memory Seam v0
read surface through the existing local atlas-query CLI.  It intentionally
keeps automatic prefetch and turn/session lifecycle capture inert for v0.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider
from hermes_constants import get_default_hermes_root, get_hermes_home
from tools.registry import tool_error, tool_result

logger = logging.getLogger(__name__)

DEFAULT_ATLAS_QUERY_RELATIVE_PATH = Path(
    "projects/system-pipes/scripts/atlas-query/atlas-query.mcp.py"
)
DEFAULT_TIMEOUT_MS = 1500
MAX_TIMEOUT_MS = 10000


HEALTH_SCHEMA = {
    "name": "memory_seam_health",
    "description": "Inspect the local Atlas Memory Seam v0 status envelope.",
    "parameters": {
        "type": "object",
        "properties": {
            "timeout_ms": {
                "type": "integer",
                "description": "Local subprocess timeout in milliseconds (default 1500).",
            },
        },
        "required": [],
    },
}

CONTEXT_SCHEMA = {
    "name": "memory_seam_context",
    "description": "Pull a bounded Atlas Memory Seam context envelope via the local CLI.",
    "parameters": {
        "type": "object",
        "properties": {
            "include": {
                "description": "Include families/labels as a comma string or array.",
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ],
            },
            "mode": {
                "type": "string",
                "enum": ["startup", "turn"],
                "description": "Context mode.",
            },
            "agent": {"type": "string", "description": "Agent label, e.g. sax."},
            "timeout_ms": {
                "type": "integer",
                "description": "Local subprocess timeout in milliseconds (default 1500).",
            },
            "fixture_case": {
                "type": "string",
                "enum": [
                    "sax_project_doc_disabled_grant",
                    "sax_project_doc_granted",
                    "sax_project_doc_missing_grant",
                ],
                "description": "Default-off no-live fixture case.",
            },
            "read_receipt": {
                "type": "string",
                "enum": ["metadata_only"],
                "description": "Request metadata-only receipt output when supported.",
            },
        },
        "required": [],
    },
}

RECALL_SCHEMA = {
    "name": "memory_seam_recall",
    "description": "Pull a bounded Atlas Memory Seam recall envelope via the local CLI.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Recall query."},
            "scope": {
                "type": "string",
                "enum": ["wiki"],
                "description": "Recall scope. v0 provider skeleton permits wiki only.",
            },
            "agent": {"type": "string", "description": "Agent label, e.g. sax."},
            "n": {"type": "integer", "description": "Maximum results."},
            "timeout_ms": {
                "type": "integer",
                "description": "Local subprocess timeout in milliseconds (default 1500).",
            },
            "max_staleness": {
                "type": "integer",
                "description": "Maximum accepted staleness in seconds.",
            },
            "read_receipt": {
                "type": "string",
                "enum": ["metadata_only"],
                "description": "Request metadata-only receipt output when supported.",
            },
        },
        "required": ["query"],
    },
}


class MemorySeamMemoryProvider(MemoryProvider):
    """Atlas Memory Seam v0 as a tools-first Hermes memory provider."""

    def __init__(self, atlas_query_script: Optional[str] = None):
        explicit_script = atlas_query_script.strip() if isinstance(atlas_query_script, str) else atlas_query_script
        self._explicit_atlas_query_script = explicit_script or None
        self._atlas_query_script = (
            self._explicit_atlas_query_script
            or os.getenv("MEMORY_SEAM_ATLAS_QUERY_SCRIPT")
            or self._discover_atlas_query_script()
            or self._default_atlas_query_script_hint()
        )
        self._session_id = ""
        self._hermes_home = ""
        self._platform = ""
        self._agent_identity = ""
        self._timeout_ms = DEFAULT_TIMEOUT_MS
        self._auto_prefetch = False

    @property
    def name(self) -> str:
        return "memory_seam"

    def is_available(self) -> bool:
        self._load_profile_config()
        return Path(self._atlas_query_script).is_file()

    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id
        self._hermes_home = str(kwargs.get("hermes_home") or "")
        self._platform = str(kwargs.get("platform") or "")
        self._agent_identity = str(kwargs.get("agent_identity") or "")
        self._load_profile_config()

    def _load_profile_config(self) -> None:
        config_path = self._config_path()
        if not config_path.is_file():
            return
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("Failed to read Memory Seam provider config: %s", exc)
            return

        script = data.get("atlas_query_script")
        if (
            self._explicit_atlas_query_script is None
            and isinstance(script, str)
            and script.strip()
        ):
            self._atlas_query_script = script.strip()
        timeout = data.get("default_timeout_ms")
        if isinstance(timeout, int) and timeout > 0:
            self._timeout_ms = min(timeout, MAX_TIMEOUT_MS)
        self._auto_prefetch = bool(data.get("auto_prefetch", False))

    def save_config(self, values: Dict[str, Any], hermes_home: str) -> None:
        config_path = self._config_path(hermes_home)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        data: Dict[str, Any] = {}
        if config_path.is_file():
            try:
                existing = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    data = existing
            except Exception as exc:
                logger.debug("Failed to read existing Memory Seam provider config: %s", exc)

        script = values.get("atlas_query_script")
        if script is not None and str(script).strip():
            data["atlas_query_script"] = str(script).strip()

        timeout = values.get("default_timeout_ms")
        if timeout is not None and timeout != "":
            data["default_timeout_ms"] = self._coerce_positive_config_int(
                timeout,
                "default_timeout_ms",
            )

        config_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        # v0 is pull-based.  This remains inert even if config accidentally sets
        # auto_prefetch until a future guarded mode is explicitly implemented.
        return ""

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        return None

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        return None

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        return None

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
        rewound: bool = False,
        **kwargs,
    ) -> None:
        self._session_id = new_session_id

    def shutdown(self) -> None:
        return None

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [HEALTH_SCHEMA, CONTEXT_SCHEMA, RECALL_SCHEMA]

    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": "atlas_query_script",
                "description": "Path to atlas-query.mcp.py for local Memory Seam calls",
                "required": False,
                "default": self._atlas_query_script,
            },
            {
                "key": "default_timeout_ms",
                "description": "Local subprocess timeout in milliseconds",
                "required": False,
                "default": DEFAULT_TIMEOUT_MS,
            },
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        if tool_name == "memory_seam_health":
            return self._call_cli("memory_seam.health", [], args)
        if tool_name == "memory_seam_context":
            try:
                cli_args = self._context_args(args)
            except ValueError as exc:
                return tool_error(str(exc))
            return self._call_cli("memory_seam.context", cli_args, args)
        if tool_name == "memory_seam_recall":
            query = args.get("query")
            if not isinstance(query, str) or not query.strip():
                return tool_error("memory_seam_recall requires a non-empty query")
            try:
                cli_args = self._recall_args(args)
            except ValueError as exc:
                return tool_error(str(exc))
            return self._call_cli("memory_seam.recall", cli_args, args)
        return tool_error(f"Unsupported Memory Seam tool '{tool_name}'")

    def _call_cli(self, subcommand: str, cli_args: List[str], raw_args: Dict[str, Any]) -> str:
        try:
            timeout_ms = self._validated_timeout_ms(raw_args.get("timeout_ms"))
        except ValueError as exc:
            return tool_error(str(exc))
        timeout_seconds = timeout_ms / 1000
        cmd = [sys.executable, self._atlas_query_script, subcommand, *cli_args]
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return tool_error(f"Memory Seam CLI timed out after {timeout_ms}ms")
        except Exception as exc:
            return tool_error(f"Memory Seam CLI failed to start: {exc}")

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            return tool_error(
                "Memory Seam CLI returned non-zero exit status",
                returncode=completed.returncode,
                detail=detail,
            )

        stdout = (completed.stdout or "").strip()
        if not stdout:
            return tool_error("Memory Seam CLI returned empty output")
        try:
            return tool_result(json.loads(stdout))
        except json.JSONDecodeError as exc:
            return tool_error("Memory Seam CLI returned invalid JSON", detail=str(exc))

    def _context_args(self, args: Dict[str, Any]) -> List[str]:
        cli_args: List[str] = []
        include = self._join_string_or_list(args.get("include"))
        self._append_optional(cli_args, "--include", include)
        self._append_optional(cli_args, "--mode", args.get("mode"))
        self._append_optional(cli_args, "--agent", args.get("agent"))
        fixture_case = args.get("fixture_case")
        if fixture_case in {
            "sax_project_doc_disabled_grant",
            "sax_project_doc_granted",
            "sax_project_doc_missing_grant",
            "sax_source_card_deck_granted",
            "sax_source_card_safe_detail_all_granted",
            "sax_source_card_safe_detail_v1_granted",
            "sax_source_card_safe_detail_v2_granted",
        }:
            # Do not forward caller-supplied authority labels. The only v0
            # trusted-authority shape this bundled provider rehearses is the
            # process-owned Sax project/source-card fixture surface from
            # system-pipes.
            self._append_optional(cli_args, "--token-subject", "agent:sax")
            self._append_optional(cli_args, "--allowed-scopes", "project")
        self._append_optional_int(cli_args, "--timeout-ms", args.get("timeout_ms"))
        self._append_optional(cli_args, "--fixture-case", fixture_case)
        self._append_optional(cli_args, "--read-receipt", args.get("read_receipt"))
        return cli_args

    def _recall_args(self, args: Dict[str, Any]) -> List[str]:
        cli_args = ["--query", str(args["query"])]
        self._append_optional(cli_args, "--scope", "wiki")
        self._append_optional(cli_args, "--agent", args.get("agent"))
        self._append_optional_int(cli_args, "--n", args.get("n"))
        self._append_optional_int(cli_args, "--timeout-ms", args.get("timeout_ms"))
        self._append_optional_int(cli_args, "--max-staleness", args.get("max_staleness"))
        self._append_optional(cli_args, "--read-receipt", args.get("read_receipt"))
        return cli_args

    @staticmethod
    def _join_string_or_list(value: Any) -> Optional[str]:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return ",".join(str(item) for item in value if str(item))
        return None

    @staticmethod
    def _append_optional(cli_args: List[str], flag: str, value: Any) -> None:
        if value is None or value == "":
            return
        cli_args.extend([flag, str(value)])

    @staticmethod
    def _append_optional_int(cli_args: List[str], flag: str, value: Any) -> None:
        if value is None or value == "":
            return
        cli_args.extend([flag, str(MemorySeamMemoryProvider._coerce_int_arg(value, flag))])

    @staticmethod
    def _coerce_int_arg(value: Any, label: str) -> int:
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid integer for {label}")
        if coerced < 0:
            raise ValueError(f"Invalid integer for {label}")
        if label == "--timeout-ms":
            return min(coerced, MAX_TIMEOUT_MS)
        return coerced

    @staticmethod
    def _coerce_positive_int(value: Any, default: int) -> int:
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            return default
        if coerced <= 0:
            return default
        return min(coerced, MAX_TIMEOUT_MS)

    def _validated_timeout_ms(self, value: Any) -> int:
        if value is None or value == "":
            return min(self._timeout_ms, MAX_TIMEOUT_MS)
        return self._coerce_int_arg(value, "--timeout-ms")

    @staticmethod
    def _default_atlas_query_script_hint() -> str:
        return str(get_default_hermes_root().parent / DEFAULT_ATLAS_QUERY_RELATIVE_PATH)

    @staticmethod
    def _discover_atlas_query_script() -> Optional[str]:
        candidates = [
            get_default_hermes_root().parent / DEFAULT_ATLAS_QUERY_RELATIVE_PATH,
            Path.home() / DEFAULT_ATLAS_QUERY_RELATIVE_PATH,
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return None

    def _config_path(self, hermes_home: Optional[str] = None) -> Path:
        home = hermes_home or self._hermes_home or str(get_hermes_home())
        return Path(home) / "memory_seam.json"

    @staticmethod
    def _coerce_positive_config_int(value: Any, label: str) -> int:
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid integer for {label}")
        if coerced <= 0:
            raise ValueError(f"Invalid integer for {label}")
        return min(coerced, MAX_TIMEOUT_MS)


def register(ctx) -> None:
    ctx.register_memory_provider(MemorySeamMemoryProvider())
