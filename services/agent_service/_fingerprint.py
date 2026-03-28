from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_agent_fingerprint(
    config_dict: dict[str, Any],
    canonical_prompt_v2: list[tuple[str, str]],
    knowledge_snapshot_id: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Compute deterministic fingerprints for an agent configuration.

    Args:
        config_dict: Serializable representation of the agent configuration.
        canonical_prompt_v2: Ordered list of (title, text) prompt sections.
        knowledge_snapshot_id: Optional identifier for the knowledge snapshot.

    Returns:
        Tuple of (agent_fingerprint, prompt_fingerprint, config_dict).
        Both fingerprints are SHA-256 hex digests.
    """
    # Hash prompt content
    canonical_text = "\n".join(f"{title}:{text}" for title, text in canonical_prompt_v2)
    prompt_fingerprint = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()

    # Build fingerprint payload
    payload: dict[str, Any] = {
        "config": config_dict,
        "prompt_fingerprint": prompt_fingerprint,
    }
    if knowledge_snapshot_id is not None:
        payload["knowledge_snapshot_id"] = knowledge_snapshot_id

    agent_fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    return agent_fingerprint, prompt_fingerprint, config_dict
