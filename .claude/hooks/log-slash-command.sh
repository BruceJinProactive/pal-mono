#!/bin/bash
# Runs on user-prompt-submit to capture /slash-command invocations
# that get auto-expanded without going through the Skill tool

payload=$(cat)
input=$(jq -r '.user_prompt' <<< "$payload")
session_id=$(jq -r '.session_id // "unknown"' <<< "$payload")

if [[ "$input" =~ ^/([a-zA-Z][a-zA-Z0-9_:-]*)([[:space:]]+(.*))?$ ]]; then
  skill="${BASH_REMATCH[1]}"

  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  LOG_FILE="${SKILL_LOG_FILE:-$REPO_ROOT/.claude/skill-usage.log}"
  mkdir -p "$(dirname "$LOG_FILE")"
  printf '%s\t%s\t%s\t%s\t(slash-command)\n' "$(date -u +%s)" "${USER:-unknown}" "$session_id" "$skill" >> "$LOG_FILE"
fi
