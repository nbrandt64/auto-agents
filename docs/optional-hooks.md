# Optional Hooks

The core auto-agents system uses four hooks (SessionStart, Stop, PreToolUse, PostToolUse) for communication. Beyond these, you can add optional hooks to enforce code quality and prevent common agent mistakes.

These hooks are project-specific -- add the ones that make sense for your workflow.

## Write Validator

Agents sometimes create unnecessary documentation files (.md) or write files outside their designated sector. A Write hook can block this.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/scripts/write-validator.sh"
          }
        ]
      }
    ]
  }
}
```

Example `write-validator.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Block creation of .md files outside docs/
if [[ "$FILE_PATH" == *.md ]] && [[ "$FILE_PATH" != */docs/* ]] && [[ "$FILE_PATH" != */CLAUDE.md ]]; then
    echo '{"decision": "block", "reason": "Only create .md files in docs/ directory. Use docs/ for documentation."}'
    exit 0
fi

# Allow everything else
exit 0
```

This prevents agents from scattering README files, changelog files, or other markdown throughout the codebase.

## Console.log Detection

Block commits that contain leftover debug logging.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/scripts/check-console-log.sh"
          }
        ]
      }
    ]
  }
}
```

Example `check-console-log.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only check git commit commands
if ! echo "$CMD" | grep -qE '\bgit\s+commit\b'; then
    exit 0
fi

# Check staged files for console.log
if git diff --cached --name-only | xargs grep -l 'console\.log' 2>/dev/null; then
    echo '{"decision": "block", "reason": "Staged files contain console.log statements. Remove them before committing."}'
    exit 0
fi

exit 0
```

## Sector Enforcement

If you're using sector ownership (agent Web only modifies `frontend/`, agent API only modifies `api/`), a hook can enforce this at write time.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/scripts/sector-check.sh"
          }
        ]
      }
    ]
  }
}
```

Example `sector-check.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')

COMMS="${COMMS_SCRIPT:-$HOME/.claude/scripts/comms.py}"
AGENT_NAME=$(python3 "$COMMS" resolve-name "$SESSION_ID" 2>/dev/null || echo "unknown")

# Define sector boundaries (customize for your project)
case "$AGENT_NAME" in
    Web)
        if [[ "$FILE_PATH" != */frontend/* ]] && [[ "$FILE_PATH" != */shared/* ]]; then
            echo "{\"decision\": \"block\", \"reason\": \"Web agent can only modify frontend/ and shared/. File: $FILE_PATH\"}"
            exit 0
        fi
        ;;
    API)
        if [[ "$FILE_PATH" != */api/* ]] && [[ "$FILE_PATH" != */shared/* ]]; then
            echo "{\"decision\": \"block\", \"reason\": \"API agent can only modify api/ and shared/. File: $FILE_PATH\"}"
            exit 0
        fi
        ;;
    Data)
        if [[ "$FILE_PATH" != */data/* ]] && [[ "$FILE_PATH" != */shared/* ]]; then
            echo "{\"decision\": \"block\", \"reason\": \"Data agent can only modify data/ and shared/. File: $FILE_PATH\"}"
            exit 0
        fi
        ;;
esac

exit 0
```

## Type Checking on Commit

Run type checking before allowing commits (TypeScript example).

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/scripts/typecheck-on-commit.sh"
          }
        ]
      }
    ]
  }
}
```

Example `typecheck-on-commit.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only check git commit commands
if ! echo "$CMD" | grep -qE '\bgit\s+commit\b'; then
    exit 0
fi

# Run type check
if ! npx tsc --noEmit 2>/dev/null; then
    echo '{"decision": "block", "reason": "TypeScript type errors detected. Fix them before committing."}'
    exit 0
fi

exit 0
```

## Combining Hooks

Multiple hooks of the same type run in order. Put the comms `check` hook first so agents always see new messages, then add quality hooks after:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/scripts/comms.sh check"
          }
        ]
      },
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/scripts/sector-check.sh"
          }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/scripts/write-validator.sh"
          }
        ]
      }
    ]
  }
}
```

Matcher groups with a `matcher` only run for matching tool names. Groups without a matcher run for every tool use.
