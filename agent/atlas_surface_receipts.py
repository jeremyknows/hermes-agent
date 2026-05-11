#!/usr/bin/env python3
"""Best-effort Atlas bus receipts for Hermes durable surface mutations.

This module is intentionally optional and fail-open. Hermes must continue to
work outside Atlas, so the helpers silently no-op when the Atlas bus emitter is
absent and never raise into caller mutation paths.
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from hermes_constants import get_hermes_home
from hermes_cli.config import cfg_get

logger = logging.getLogger(__name__)


def originating_profile_name() -> str:
    """Return the active Hermes profile name for receipt metadata."""
    explicit = os.getenv("HERMES_PROFILE_NAME") or os.getenv("HERMES_PROFILE")
    if explicit:
        return explicit
    home = get_hermes_home()
    if home.parent.name == "profiles":
        return home.name
    return "default"


def atlas_affected_agent_name() -> str:
    """Return the Atlas agent/profile whose operating surface changed."""
    env_name = os.getenv("HERMES_ATLAS_AGENT") or os.getenv("ATLAS_AGENT")
    if env_name:
        return env_name
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        configured = cfg_get(cfg, "atlas", "agent_name")
        if configured:
            return str(configured)
    except Exception:
        pass
    profile = originating_profile_name()
    return profile if profile != "default" else "hermes"


def atlas_actor_name() -> str:
    """Return the actor that performed the mutation.

    Defaults to the affected agent for foreground calls. Background systems can
    set HERMES_ATLAS_ACTOR / ATLAS_ACTOR to preserve actor truth while keeping
    affected_agent pointed at the profile whose surface changed.
    """
    return (
        os.getenv("HERMES_ATLAS_ACTOR")
        or os.getenv("ATLAS_ACTOR")
        or atlas_affected_agent_name()
    )


def emit_agent_surface_mutated(
    *,
    mutation_kind: str,
    artifact_kind: str,
    artifact_id: str,
    summary: str,
    outcome: str = "succeeded",
    actor: Optional[str] = None,
    affected_agent: Optional[str] = None,
    originating_profile: Optional[str] = None,
    topic: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit an Atlas `agent_surface_mutated` receipt, best-effort/fail-open."""
    try:
        emit_path = Path(os.path.expanduser("~/projects/system-pipes/scripts/bus/emit-event.sh"))
        if not emit_path.exists():
            return

        actor_name = actor or atlas_actor_name()
        affected = affected_agent or atlas_affected_agent_name()
        profile = originating_profile or originating_profile_name()
        event_topic = topic or f"agent:{affected}"
        data: Dict[str, Any] = {
            "schema_version": "0.1",
            "runtime": "hermes",
            "mutation_kind": mutation_kind,
            "outcome": outcome,
            "affected_agent": affected,
            "originating_profile": profile,
            "artifact_kind": artifact_kind,
            "artifact_id": artifact_id,
            "summary": summary,
            "visibility": "safe_summary_only",
        }
        if extra:
            data.update({k: v for k, v in extra.items() if v is not None})

        message = f"{actor_name} surface mutation: {mutation_kind} {outcome} for {artifact_id}"
        subprocess.run(
            [
                "bash",
                str(emit_path),
                actor_name,
                "agent_surface_mutated",
                message,
                json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                event_topic,
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        logger.debug("agent_surface_mutated emit failed", exc_info=True)
