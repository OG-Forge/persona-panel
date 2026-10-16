#!/bin/sh
# persona-panel PreToolUse hook launcher (POSIX sh; Git Bash's sh on Windows).
# Calls that don't come from a persona-panel agent (agent_type pp-* or persona-panel:pp-*) exit
# here without starting Python, so the hook costs the main session and other agents almost nothing.
input=$(cat)
case "$input" in
  *'"agent_type"'*pp-*) ;;
  *) exit 0 ;;
esac
dir=$(dirname "$0")
# Try each interpreter; one that is missing (or the Windows Store stub) fails and the next is tried.
# Output is captured so a failed attempt can't leave text in front of the JSON decision.
for py in python3 python py; do
  if out=$(printf '%s' "$input" | "$py" "$dir/pp_guard.py" 2>/dev/null); then
    printf '%s' "$out"
    exit 0
  fi
done
# No working Python 3: deny rather than let a persona-panel agent run unchecked.
printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"persona-panel guard: no Python 3 (python3, python or py) found to check this call"}}'
exit 0
