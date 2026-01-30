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
        # Auto-pull main repo after gh pr merge
        if echo "$CMD" | grep -qE '\bgh\s+pr\s+merge\b'; then
            CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
            MAIN_REPO=$(cd "$CWD" && git worktree list --porcelain 2>/dev/null | head -1 | sed 's/^worktree //')
            if [ -n "$MAIN_REPO" ] && [ -d "$MAIN_REPO" ]; then
                DEFAULT_BRANCH=$(cd "$MAIN_REPO" && git symbolic-ref --short HEAD 2>/dev/null || echo "")
                if [ -n "$DEFAULT_BRANCH" ]; then
                    (cd "$MAIN_REPO" && git pull origin "$DEFAULT_BRANCH" 2>/dev/null) &
                    python3 "$COMMS" post -s "$SENDER" "auto-pulled $DEFAULT_BRANCH in $(basename "$MAIN_REPO")/"
                fi
            fi
        fi
        ;;
esac

exit 0
