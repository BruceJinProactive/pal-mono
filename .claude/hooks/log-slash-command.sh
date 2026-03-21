#!/bin/bash
# Runs on user-prompt-submit to capture /slash-command invocations
# that get auto-expanded without going through the Skill tool

payload=$(cat)
input=$(jq -r '.user_prompt' <<< "$payload")

# Check if input starts with a slash command (e.g., /docs-auditor, /pr-workflow)
if [[ "$input" =~ ^/([a-zA-Z][a-zA-Z0-9_:-]*)([[:space:]]+(.*))?$ ]]; then
  skill="${BASH_REMATCH[1]}"
  args="${BASH_REMATCH[3]}"

  # Base64-encode args to prevent log injection and secret leakage
  args_b64=$(printf '%s' "$args" | base64 | tr -d '\n')

  # Log to repo-level .claude/ directory (override with SKILL_LOG_FILE for testing)
  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  LOG_FILE="${SKILL_LOG_FILE:-$REPO_ROOT/.claude/skill-usage.log}"
  mkdir -p "$(dirname "$LOG_FILE")"
  printf '%s\t%s\t%s\t%s\t(slash-command)\n' "$(date -u +%s)" "${USER:-unknown}" "$skill" "$args_b64" >> "$LOG_FILE"
fi
