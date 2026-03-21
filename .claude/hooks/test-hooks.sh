#!/bin/bash
# Tests for Claude Code hook scripts
# Calls the real scripts with SKILL_LOG_FILE override to avoid corrupting the actual log.
# Usage: .claude/hooks/test-hooks.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$(mktemp)"
PASS=0
FAIL=0

cleanup() { rm -f "$LOG_FILE"; }
trap cleanup EXIT

reset_log() { : > "$LOG_FILE"; }

assert_eq() {
  local test_name="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    echo "  PASS: $test_name"
    ((PASS++))
  else
    echo "  FAIL: $test_name"
    echo "    expected: $expected"
    echo "    actual:   $actual"
    ((FAIL++))
  fi
}

assert_match() {
  local test_name="$1" pattern="$2" actual="$3"
  if [[ "$actual" =~ $pattern ]]; then
    echo "  PASS: $test_name"
    ((PASS++))
  else
    echo "  FAIL: $test_name"
    echo "    pattern:  $pattern"
    echo "    actual:   $actual"
    ((FAIL++))
  fi
}

line_count() { [[ -s "$LOG_FILE" ]] && wc -l < "$LOG_FILE" | tr -d ' ' || echo 0; }
field() { cut -f"$1" < "$LOG_FILE" | tail -1; }
decode_args() { field 4 | base64 -d 2>/dev/null; }

# ── log-skill.sh tests ──────────────────────────────────────────────

echo "=== log-skill.sh ==="

# Test 1: Logs skill name and base64-encoded args (tab-separated)
reset_log
echo '{"tool_input": {"skill": "docs-auditor", "args": "--verbose"}}' \
  | SKILL_LOG_FILE="$LOG_FILE" "$SCRIPT_DIR/log-skill.sh"
assert_eq "line count after skill log" "1" "$(line_count)"
assert_match "contains skill name" "docs-auditor" "$(field 3)"
assert_match "decoded args contain value" "--verbose" "$(decode_args)"

# Test 2: Logs skill with no args
reset_log
echo '{"tool_input": {"skill": "commit"}}' \
  | SKILL_LOG_FILE="$LOG_FILE" "$SCRIPT_DIR/log-skill.sh"
assert_match "contains skill name (no args)" "commit" "$(field 3)"

# Test 3: Appends to existing log (doesn't overwrite)
echo '{"tool_input": {"skill": "second-skill", "args": ""}}' \
  | SKILL_LOG_FILE="$LOG_FILE" "$SCRIPT_DIR/log-skill.sh"
assert_eq "appends (2 lines)" "2" "$(line_count)"

# Test 4: Log uses tab separators
reset_log
echo '{"tool_input": {"skill": "test-skill", "args": "a"}}' \
  | SKILL_LOG_FILE="$LOG_FILE" "$SCRIPT_DIR/log-skill.sh"
TAB_COUNT=$(awk -F'\t' '{print NF-1}' < "$LOG_FILE" | tail -1)
assert_eq "tab-separated (3 tabs)" "3" "$TAB_COUNT"

# ── log-slash-command.sh tests ───────────────────────────────────────

echo ""
echo "=== log-slash-command.sh ==="

# Test 5: Captures slash command with base64-encoded args
reset_log
echo '{"user_prompt": "/pr-workflow create draft"}' \
  | SKILL_LOG_FILE="$LOG_FILE" "$SCRIPT_DIR/log-slash-command.sh"
assert_eq "line count after slash command" "1" "$(line_count)"
assert_match "contains skill name" "pr-workflow" "$(field 3)"
assert_match "decoded args contain value" "create draft" "$(decode_args)"
assert_match "tagged as slash-command" "slash-command" "$(cat "$LOG_FILE")"

# Test 6: Captures slash command without args
reset_log
echo '{"user_prompt": "/commit"}' \
  | SKILL_LOG_FILE="$LOG_FILE" "$SCRIPT_DIR/log-slash-command.sh"
assert_eq "line count for no-arg slash" "1" "$(line_count)"
assert_match "contains skill name" "commit" "$(field 3)"

# Test 7: Captures namespaced skill (colon-separated)
reset_log
echo '{"user_prompt": "/oh-my-claudecode:autopilot"}' \
  | SKILL_LOG_FILE="$LOG_FILE" "$SCRIPT_DIR/log-slash-command.sh"
assert_eq "line count for namespaced skill" "1" "$(line_count)"
assert_match "contains namespaced skill" "oh-my-claudecode:autopilot" "$(field 3)"

# Test 8: Ignores non-slash input (with exit status check)
reset_log
echo '{"user_prompt": "just a normal message"}' \
  | SKILL_LOG_FILE="$LOG_FILE" "$SCRIPT_DIR/log-slash-command.sh"
status=$?
assert_eq "exits successfully for normal message" "0" "$status"
assert_eq "no log for normal message" "0" "$(line_count)"

# Test 9: Ignores empty input (with exit status check)
reset_log
echo '{"user_prompt": ""}' \
  | SKILL_LOG_FILE="$LOG_FILE" "$SCRIPT_DIR/log-slash-command.sh"
status=$?
assert_eq "exits successfully for empty input" "0" "$status"
assert_eq "no log for empty input" "0" "$(line_count)"

# Test 10: Bare slash is not a command (with exit status check)
reset_log
echo '{"user_prompt": "/ not a command"}' \
  | SKILL_LOG_FILE="$LOG_FILE" "$SCRIPT_DIR/log-slash-command.sh"
status=$?
assert_eq "exits successfully for bare slash" "0" "$status"
assert_eq "no log for bare slash" "0" "$(line_count)"

# Test 11: Partial token like /foo.bar is rejected
reset_log
echo '{"user_prompt": "/foo.bar"}' \
  | SKILL_LOG_FILE="$LOG_FILE" "$SCRIPT_DIR/log-slash-command.sh"
assert_eq "no log for partial token /foo.bar" "0" "$(line_count)"

# ── log-session-usage.sh tests ─────────────────────────────────────

echo ""
echo "=== log-session-usage.sh ==="

# Test 12: Logs token usage from project transcript (live data)
reset_log
SESSION_LOG_FILE="$LOG_FILE" "$SCRIPT_DIR/log-session-usage.sh"
if [[ "$(line_count)" -ge 1 ]]; then
  assert_eq "session: logs one line" "1" "$(line_count)"
  assert_match "session: has model" "claude" "$(field 4)"
  # output_tokens should be > 0
  OUTPUT_TOKENS=$(field 6)
  if [[ "$OUTPUT_TOKENS" =~ ^[0-9]+$ ]] && [[ "$OUTPUT_TOKENS" -gt 0 ]]; then
    echo "  PASS: session: output tokens > 0 ($OUTPUT_TOKENS)"
    ((PASS++))
  else
    echo "  FAIL: session: output tokens > 0 (got $OUTPUT_TOKENS)"
    ((FAIL++))
  fi
  # Tab count: 8 tabs = 9 fields
  TAB_COUNT=$(awk -F'\t' '{print NF-1}' < "$LOG_FILE" | tail -1)
  assert_eq "session: tab-separated (8 tabs)" "8" "$TAB_COUNT"
else
  echo "  SKIP: no project transcript available"
fi

# Test 13: Dedup — running again with same data should not add a line
BEFORE=$(line_count)
SESSION_LOG_FILE="$LOG_FILE" "$SCRIPT_DIR/log-session-usage.sh"
assert_eq "session: dedup prevents duplicate" "$BEFORE" "$(line_count)"

# ── Summary ──────────────────────────────────────────────────────────

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
