#!/bin/bash
# start-agents.sh — Launch all agents + group chat windows in one command.
# Copy to your project and set PROJECT_DIR below.

## CONFIGURE
PROJECT_DIR="/path/to/your/project"   # e.g. /Users/you/dev/myapp (no trailing slash)

AGENTS=(
  "${PROJECT_DIR}-web"
  "${PROJECT_DIR}-api"
  "${PROJECT_DIR}-data"
  "${PROJECT_DIR}-github"
)

# Prompt: dangerously-skip-permissions
read -r -p "Skip permissions prompts? (--dangerously-skip-permissions) [y/N] " skip_perms
if [[ "$skip_perms" =~ ^[Yy]$ ]]; then
  PERMS_FLAG="--dangerously-skip-permissions"
else
  PERMS_FLAG=""
fi

# Prompt: /begin-work startup prompt
read -r -p "Run /begin-work automatically on startup? [y/N] " run_begin_work
if [[ "$run_begin_work" =~ ^[Yy]$ ]]; then
  STARTUP_PROMPT="'/begin-work'"
else
  STARTUP_PROMPT=""
fi

CLAUDE_CMD="claude ${PERMS_FLAG} ${STARTUP_PROMPT}"
CLAUDE_CMD="${CLAUDE_CMD%"${CLAUDE_CMD##*[! ]}"}"  # trim trailing spaces

# Open first tab: first agent
osascript <<EOF
tell application "Terminal"
  activate
  do script "cd '${AGENTS[0]}' && ${CLAUDE_CMD}"
end tell
EOF

sleep 1

# Open remaining tabs — separate osascript calls avoid nested-tell focus issues
open_tab() {
  local cmd="$1"
  osascript <<EOF
tell application "System Events"
  tell process "Terminal"
    keystroke "t" using command down
  end tell
end tell
delay 0.5
tell application "Terminal"
  do script "$cmd" in front window
end tell
EOF
}

open_tab "cd '${AGENTS[1]}' && ${CLAUDE_CMD}"
open_tab "cd '${AGENTS[2]}' && ${CLAUDE_CMD}"
open_tab "cd '${AGENTS[3]}' && ${CLAUDE_CMD}"
open_tab "auto-agents watch"
open_tab "auto-agents chat"
