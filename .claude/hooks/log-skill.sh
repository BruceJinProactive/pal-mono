#!/bin/bash
# stdin is the hook payload: { tool_name, tool_input: { skill, args }, session_id, ... }
# matcher already filtered to Skill, so no tool_name check needed

payload=$(cat)
skill=$(jq -r '.tool_input.skill' <<< "$payload")
args_json=$(jq -c '.tool_input.args // {}' <<< "$payload")
args_b64=$(printf '%s' "$args_json" | base64 | tr -d '\n')

# Log to repo-level .claude/ directory (override with SKILL_LOG_FILE for testing)
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
LOG_FILE="${SKILL_LOG_FILE:-$REPO_ROOT/.claude/skill-usage.log}"
mkdir -p "$(dirname "$LOG_FILE")"
printf '%s\t%s\t%s\t%s\n' "$(date -u +%s)" "${USER:-unknown}" "$skill" "$args_b64" >> "$LOG_FILE"
