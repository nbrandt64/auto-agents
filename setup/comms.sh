#!/usr/bin/env bash
# Agent comms hook wrapper — reads stdin JSON from Claude Code hooks.
# Place this at ~/.claude/scripts/comms.sh and make it executable.
set -euo pipefail

COMMS="${COMMS_SCRIPT:-$HOME/.claude/scripts/comms.py}"
MODE="${1:-}"

# If no mode argument, pass everything to comms.py directly (manual use)
if [ -z "$MODE" ]; then
    shift 0 2>/dev/null || true
    exec python3 "$COMMS" "$@"
fi

# Hook mode — read stdin JSON
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
SENDER=$(python3 "$COMMS" resolve-name "$SESSION_ID")

if [ -z "$SESSION_ID" ]; then
    exit 0
fi

case "$MODE" in
    session-start)
        CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
        DIR_NAME=$(basename "$CWD")
        python3 "$COMMS" auto-assign "$SESSION_ID" "$CWD"
        SENDER=$(python3 "$COMMS" resolve-name "$SESSION_ID")
        python3 "$COMMS" post -s "$SENDER" "Session started in $DIR_NAME"
        ;;
    session-end)
        python3 "$COMMS" post -s "$SENDER" "Session ended"
        ;;
    check)
        python3 "$COMMS" check "$SESSION_ID"
        ;;
    git-detect)
        CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
        if echo "$CMD" | grep -qE '\bgit\s+(checkout|switch|branch|merge|rebase|push|pull|worktree)\b'; then
            python3 "$COMMS" post -s "$SENDER" "git: $CMD"
        fi
        ;;
esac

exit 0
