# P1-B1a: Implement compute_agent_fingerprint()

**Task:** https://www.notion.so/3318c0822e4981e29decc70f069ebbfc
**Type:** CODE
**Est. Hours:** 3
**Blocked by:** None

---

## Background

Agent fingerprinting enables tracking which exact agent configuration produced which eval results. The fingerprint is a deterministic hash of the agent's stable configuration — prompt content, model, tools, feature flags — excluding ephemeral runtime context like timestamps.

No existing hashing/fingerprinting utilities exist in the codebase. This is a new module in `services/agent_service/`.

---

## Implementation Steps

- [ ] **Step 1: Create `services/agent_service/_fingerprint.py`**

  ```python
  from __future__ import annotations
  import hashlib
  import json
  from typing import Any

  def compute_agent_fingerprint(
      agent_config: Any,
      canonical_prompt_v2: list[tuple[str, str]],
      knowledge_snapshot_id: str | None = None,
  ) -> tuple[str, str, dict]:
      """Returns (agent_fingerprint, prompt_fingerprint, config_dict)."""
  ```

  - Build `config_dict` from stable agent_config fields: model, tools, feature flags, capability actions
  - Exclude ephemeral fields: current timestamp, additional_context derived from time
  - Compute `prompt_fingerprint` = SHA-256 of canonicalized prompt text (sorted, joined)
  - Compute `agent_fingerprint` = SHA-256 of `config_dict` + `prompt_fingerprint` + optional `knowledge_snapshot_id`
  - Use `json.dumps(config_dict, sort_keys=True)` for deterministic serialization

- [ ] **Step 2: Write unit tests in `tests/services/agent_service/test_fingerprint.py`**

  Test cases:
  - Same input → same fingerprint (determinism)
  - Different prompt text → different prompt_fingerprint
  - Different model → different agent_fingerprint
  - Different tool config → different agent_fingerprint
  - Ephemeral context excluded (changing timestamp doesn't change fingerprint)
  - knowledge_snapshot_id included when provided

---

## Validation

```bash
uv run pytest tests/services/agent_service/test_fingerprint.py -v
./scripts/validate.sh
```

---

## Risks & Open Questions

- Need to inspect `AgentConfig` class (from pal-agents) to know which fields are stable vs ephemeral — verify at implementation time by reading the import
- Canonicalization of prompt text: join all (title, instructions) pairs sorted by title, or preserve order? Order-preserving is safer since prompt order matters semantically.
