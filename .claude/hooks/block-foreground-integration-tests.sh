#!/bin/bash
# PreToolUse hook: blocks foreground execution of integration tests.
#
# Integration tests can hang indefinitely. They MUST be run via the
# /run-integration-test skill, which uses background execution with timeout
# monitoring. This hook catches the common mistake of running them in
# the foreground.
#
# Stdin: JSON with tool_input.command and tool_input.run_in_background

INPUT=$(cat)

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
BACKGROUND=$(echo "$INPUT" | jq -r '.tool_input.run_in_background // false')

# Only block foreground calls
if [ "$BACKGROUND" = "true" ]; then
  exit 0
fi

# Check the first line only — heredoc/commit-message content on later lines
# should not trigger false positives.
FIRST_LINE=$(echo "$COMMAND" | head -1)
if echo "$FIRST_LINE" | grep -qE '(just test-integration|pytest.*sculptor/tests/integration)'; then
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: "BLOCKED: Integration tests must not run in the foreground — they can hang indefinitely. Use the /run-integration-test skill instead, which runs tests in the background with timeout monitoring. Invoke it with: Skill tool, skill=\"run-integration-test\""
    }
  }'
else
  exit 0
fi
