#!/usr/bin/env bash
# DEPRECATED: This file is superseded by auto-agents.py.
# Use 'auto-agents' CLI instead. See README.md for details.
# Kept for backward compatibility only.
#
# Agent comms hook wrapper — reads stdin JSON from Claude Code hooks
set -euo pipefail

# Load comms API config (URL + secret)
[ -f "$HOME/.claude/comms/config" ] && source "$HOME/.claude/comms/config"
export COMMS_API_URL COMMS_API_SECRET

COMMS="$HOME/.claude/scripts/comms.py"
MODE="${1:-}"

# If no mode argument, pass everything to comms.py directly (manual use)
if [ -z "$MODE" ]; then
    shift 0 2>/dev/null || true
    exec python3 "$COMMS" "$@"
fi

# Hook mode — read stdin JSON
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')

if [ -z "$SESSION_ID" ]; then
    exit 0
fi

# Derive project from CWD using comms.py detect-project (single source of truth)
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
PROJECT=$(python3 "$COMMS" detect-project "$CWD" 2>/dev/null || echo "general")

# Only managed projects participate in comms — skip unknown directories
if [ "$PROJECT" = "general" ]; then
    exit 0
fi

case "$MODE" in
    session-start)
        DIR_NAME=$(basename "$CWD")
        # auto-assign registers the agent and returns the name
        SENDER=$(python3 "$COMMS" auto-assign "$SESSION_ID" "$CWD" 2>/dev/null | tail -1)
        [ -z "$SENDER" ] && SENDER="agent-${SESSION_ID:0:8}"
        python3 "$COMMS" post -s "$SENDER" -p "$PROJECT" "Session started in $DIR_NAME"
        ;;
    session-end)
        SENDER=$(python3 "$COMMS" resolve-name "$SESSION_ID" 2>/dev/null || echo "agent-${SESSION_ID:0:8}")
        python3 "$COMMS" post -s "$SENDER" -p "$PROJECT" "Session ended"
        ;;
    check)
        python3 "$COMMS" check "$SESSION_ID"
        ;;
    git-detect)
        SENDER=$(python3 "$COMMS" resolve-name "$SESSION_ID" 2>/dev/null || echo "agent-${SESSION_ID:0:8}")
        CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
        if echo "$CMD" | grep -qE '\bgit\s+(checkout|switch|branch|merge|rebase|push|pull|worktree)\b'; then
            python3 "$COMMS" post -s "$SENDER" -p "$PROJECT" "git: $CMD"
        fi
        # Auto-pull main repo after gh pr merge
        if echo "$CMD" | grep -qE '\bgh\s+pr\s+merge\b'; then
            MAIN_REPO=$(cd "$CWD" && git worktree list --porcelain 2>/dev/null | head -1 | sed 's/^worktree //')
            if [ -n "$MAIN_REPO" ] && [ -d "$MAIN_REPO" ]; then
                DEFAULT_BRANCH=$(cd "$MAIN_REPO" && git symbolic-ref --short HEAD 2>/dev/null || echo "")
                if [ -n "$DEFAULT_BRANCH" ]; then
                    (cd "$MAIN_REPO" && git pull origin "$DEFAULT_BRANCH" 2>/dev/null) &
                    python3 "$COMMS" post -s "$SENDER" -p "$PROJECT" "auto-pulled $DEFAULT_BRANCH in $(basename "$MAIN_REPO")/"
                fi
            fi
        fi
        ;;
esac

exit 0
