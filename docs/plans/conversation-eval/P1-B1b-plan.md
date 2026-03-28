# P1-B1b: Add build_with_hash() and build_with_fingerprint()

**Task:** https://www.notion.so/3318c0822e498118851bede678959938
**Type:** CODE
**Est. Hours:** 3
**Blocked by:** None (but integrates with P1-B1a at test time)

---

## Background

`PromptFactoryV2.build()` returns `list[tuple[str, str]]` (title, instructions pairs). We need a `build_with_hash()` that also returns a deterministic hash of the prompt content.

`RawConfig.build()` returns `AgentConfig`. We need a `build_with_fingerprint()` that also returns fingerprint data. CRITICAL: Do NOT change existing `build()` signatures — add new methods only.

---

## Implementation Steps

- [ ] **Step 1: Add `build_with_hash()` to PromptFactoryV2**

  File: `services/prompt_service/prompts_v2.py`

  ```python
  async def build_with_hash(
      self,
      agent_id: UUID,
      channel: Optional[Channel] = None,
      session: Optional[AsyncSession] = None,
  ) -> tuple[list[tuple[str, str]], str]:
      """Returns (prompts, prompt_hash)."""
      prompts = await self.build(agent_id, channel, session)
      # Canonicalize: join all prompt text in order
      canonical = "\n".join(f"{title}:{text}" for title, text in prompts)
      prompt_hash = hashlib.sha256(canonical.encode()).hexdigest()
      return prompts, prompt_hash
  ```

  Keep `build()` completely unchanged.

- [ ] **Step 2: Add `build_with_fingerprint()` to RawConfig**

  File: `services/agent_service/_raw_config.py`

  ```python
  async def build_with_fingerprint(
      self, session: Optional[AsyncSession] = None
  ) -> tuple[AgentConfig, str, str, dict]:
      """Returns (config, agent_fingerprint, prompt_fingerprint, config_dict)."""
      config = await self.build(session)
      # Get prompt hash from PromptFactoryV2
      # Call compute_agent_fingerprint() with config + prompt hash
      return config, agent_fp, prompt_fp, config_dict
  ```

  Import `compute_agent_fingerprint` from `services.agent_service._fingerprint`.

- [ ] **Step 3: Write tests**

  File: `tests/services/test_prompt_v2_hash.py` and/or extend existing prompt tests:
  - `build_with_hash()` returns same hash for same input
  - `build()` still works unchanged (regression test)
  - `build_with_fingerprint()` returns tuple with correct types

---

## Validation

```bash
uv run pytest tests/services/ -k "fingerprint or hash" -v
./scripts/validate.sh
```

---

## Risks & Open Questions

- `build_with_fingerprint()` needs access to PromptFactoryV2 — check how RawConfig currently accesses prompt building. It may need the prompt hash passed in rather than calling PromptFactoryV2 directly.
- Verify that `build()` calls within `build_with_fingerprint()` don't cause double work — the existing `build()` already calls prompt building internally.
