#!/usr/bin/env bash
# Creates persistent git worktrees for each agent.
# Run from the root of your project repo.
#
# Usage:
#   cd /path/to/your-project
#   bash /path/to/setup-worktrees.sh
#
# This creates sibling directories like:
#   your-project-web/
#   your-project-api/
#   your-project-data/
#   your-project-sysadmin/

set -euo pipefail

REPO_DIR=$(pwd)
REPO_NAME=$(basename "$REPO_DIR")
PARENT_DIR=$(dirname "$REPO_DIR")
DEFAULT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "main")

# Agent names — customize these for your project
AGENTS=("web" "api" "data" "sysadmin")

echo "Project: $REPO_NAME"
echo "Default branch: $DEFAULT_BRANCH"
echo "Creating worktrees in: $PARENT_DIR/"
echo ""

for agent in "${AGENTS[@]}"; do
    WORKTREE_DIR="$PARENT_DIR/${REPO_NAME}-${agent}"
    BRANCH="agent/${agent}"

    if [ -d "$WORKTREE_DIR" ]; then
        echo "  [skip] $WORKTREE_DIR already exists"
        continue
    fi

    # Create the parking branch if it doesn't exist
    if ! git show-ref --verify --quiet "refs/heads/$BRANCH"; then
        git branch "$BRANCH" "$DEFAULT_BRANCH"
    fi

    git worktree add "$WORKTREE_DIR" "$BRANCH"
    echo "  [created] $WORKTREE_DIR -> $BRANCH"
done

echo ""
echo "Done. Each agent gets its own directory:"
for agent in "${AGENTS[@]}"; do
    echo "  ${REPO_NAME}-${agent}/ -> agent/${agent}"
done
echo ""
echo "Launch Claude Code in each directory to start agents."
echo "Run 'python3 comms.py watch' to see the group chat."
