#!/bin/bash
# Logs per-session token usage by summing usage from the project-level transcript.
#
# Hooked to Stop event — fires each time Claude pauses for input or session ends.
# Reads assistant message usage fields from ~/.claude/projects/<project>/<session>.jsonl
#
# Log format (TSV): timestamp user session_id model input_tokens output_tokens cache_read cache_write msg_count
# Override log path with SESSION_LOG_FILE env var.

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
LOG_FILE="${SESSION_LOG_FILE:-$REPO_ROOT/.claude/session-usage.log}"
mkdir -p "$(dirname "$LOG_FILE")"

# ── Resolve project transcript directory ──────────────────────────────
# Claude Code stores transcripts at ~/.claude/projects/<mangled-cwd>/<session>.jsonl
# The mangled path replaces / and . with - (leading dash is kept)
CWD="$(pwd)"
MANGLED=$(echo "$CWD" | tr '/.' '-')
PROJECT_DIR="$HOME/.claude/projects/$MANGLED"

if [[ ! -d "$PROJECT_DIR" ]]; then
  exit 0
fi

# Find the most recently modified transcript (current session)
TRANSCRIPT=$(ls -t "$PROJECT_DIR"/*.jsonl 2>/dev/null | head -1)
if [[ -z "$TRANSCRIPT" ]]; then
  exit 0
fi

SESSION_ID=$(basename "$TRANSCRIPT" .jsonl)

# ── Sum token usage from all assistant messages ──────────────────────
IFS=$'\t' read -r INPUT OUTPUT CACHE_READ CACHE_WRITE MSG_COUNT MODEL < <(python3 -c "
import json, sys

totals = {'input': 0, 'output': 0, 'cache_read': 0, 'cache_write': 0}
msg_count = 0
model = 'unknown'

with open(sys.argv[1]) as f:
    for line in f:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = obj.get('message', {})
        usage = msg.get('usage', {})
        if usage:
            msg_count += 1
            totals['input'] += usage.get('input_tokens', 0)
            totals['output'] += usage.get('output_tokens', 0)
            totals['cache_read'] += usage.get('cache_read_input_tokens', 0)
            totals['cache_write'] += usage.get('cache_creation_input_tokens', 0)
            m = msg.get('model', '')
            if m:
                model = m

print(f\"{totals['input']}\t{totals['output']}\t{totals['cache_read']}\t{totals['cache_write']}\t{msg_count}\t{model}\")
" "$TRANSCRIPT")

# Default to 0 if parsing failed
MSG_COUNT="${MSG_COUNT:-0}"

# Skip if no usage data found
if [[ "$MSG_COUNT" -eq 0 ]]; then
  exit 0
fi

# ── Dedup: don't re-log if last entry is same session with same msg count ──
if [[ -f "$LOG_FILE" ]]; then
  LAST_LINE=$(tail -1 "$LOG_FILE" 2>/dev/null || true)
  LAST_SESSION=$(echo "$LAST_LINE" | cut -f3)
  LAST_MSG_COUNT=$(echo "$LAST_LINE" | cut -f9)
  if [[ "$LAST_SESSION" == "$SESSION_ID" && "$LAST_MSG_COUNT" == "$MSG_COUNT" ]]; then
    exit 0
  fi
fi

printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
  "$(date -u +%s)" "${USER:-unknown}" "$SESSION_ID" "$MODEL" \
  "$INPUT" "$OUTPUT" "$CACHE_READ" "$CACHE_WRITE" "$MSG_COUNT" >> "$LOG_FILE"
