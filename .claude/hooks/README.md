# Claude Code Hooks

Hook scripts that run automatically during Claude Code sessions via `.claude/settings.json`.

## Hooks

### log-skill.sh
**Event:** `PreToolUse` (matcher: `Skill`)

Logs every Skill tool invocation. Captures session ID and skill name.

### log-slash-command.sh
**Event:** `UserPromptSubmit`

Captures `/slash-command` invocations (e.g. `/pr-workflow create draft`). Validates command syntax with regex.

### log-session-usage.sh
**Event:** `Stop`

Logs per-session token usage by reading the project-level transcript at `~/.claude/projects/<project>/<session>.jsonl`. Sums `input_tokens`, `output_tokens`, `cache_read_input_tokens`, and `cache_creation_input_tokens` from all assistant messages. Includes dedup logic to avoid duplicate entries when the hook fires multiple times within a session.

## Log Files

| File | Format | Contents |
|------|--------|----------|
| `.claude/skill-usage.log` | TSV | `timestamp user session_id skill [tag]` |
| `.claude/session-usage.log` | TSV | `timestamp user session_id model input output cache_read cache_write msg_count` |

Both logs use tab-separated values.

## Testing

```bash
.claude/hooks/test-hooks.sh
```

All hooks support env var overrides for testing:
- `SKILL_LOG_FILE` — override skill/slash-command log path
- `SESSION_LOG_FILE` — override session usage log path
