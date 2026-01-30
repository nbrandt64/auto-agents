# Architecture

## Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Git Repository                        │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Worktree  │  │ Worktree  │  │ Worktree  │  ...       │
│  │ agent-web │  │ agent-api │  │ agent-data│              │
│  │           │  │           │  │           │              │
│  │ Claude CC │  │ Claude CC │  │ Claude CC │              │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘            │
│        │               │               │                  │
│        └───────────┬───┴───────────────┘                  │
│                    │                                      │
│         ┌──────────▼──────────┐                           │
│         │   SQLite Group Chat  │                          │
│         │   (messages.db)      │                          │
│         └──────────┬──────────┘                           │
│                    │                                      │
│         ┌──────────▼──────────┐                           │
│         │   Claude Code Hooks  │                          │
│         │   (settings.json)    │                          │
│         └─────────────────────┘                           │
└─────────────────────────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │   GitHub Actions       │
         │   Copilot Review Gate  │
         └───────────────────────┘
```

## Components

### Worktrees

Each agent operates in a dedicated git worktree -- a separate checkout of the same repository. All worktrees share the same `.git` directory, so branches, commits, and history are visible to all agents. This eliminates merge conflicts from simultaneous checkouts and allows each agent to have its own branch.

Worktrees are created with `git worktree add` and typically follow a naming pattern: `project-agentname/` (e.g., `myapp-web/`, `myapp-api/`). Each worktree has its own `CLAUDE.md` defining that agent's identity, scope, and responsibilities.

### Comms System

The communication layer is a single Python script (`comms.py`) backed by a SQLite database. It provides:

- **Messages table**: timestamped messages with sender name and channel.
- **Agents table**: maps Claude Code session IDs to friendly names (Web, API, Data, etc.).
- **Last-read tracking**: each session tracks which messages it has already seen, so the `check` command only surfaces new messages.

The script supports these commands: `post`, `check`, `chat`, `history`, `status`, `assign`, `auto-assign`, and `resolve-name`. Agents primarily use `post` (send a message) and `check` (poll for new messages directed at them).

### Hooks

Claude Code hooks in `settings.json` drive the system automatically:

- **SessionStart**: Registers the agent on the group chat and posts a join message. The agent name is derived from the working directory (e.g., `myapp-web/` becomes "Web").
- **SessionStop**: Posts a departure message so other agents know the session ended.
- **PreToolUse**: Before every tool invocation, runs `comms.py check` to surface any new messages. Messages addressed to the current agent (e.g., `Web: please review the auth module`) are tagged `>>> FOR YOU`.
- **PostToolUse (Bash)**: After Bash commands that involve git operations, posts a summary to the chat (e.g., "pushed feat/login to origin"). Also detects `gh pr merge` and auto-pulls the default branch in the main repo directory so it stays in sync with merged PRs.

### Copilot Review Gate

A GitHub Actions workflow (`require-copilot-review.yml`) runs on a schedule and on `pull_request_review` events. It checks whether GitHub Copilot has reviewed the PR and left zero unresolved comments. If so, it sets a commit status ("Copilot Review Gate") to `success`, which unblocks merging. If comments remain, the status stays `pending`.

Agents are expected to poll for Copilot comments, fix them, push, and wait for re-review until the gate passes.

## Data Flow

1. **Agent starts**: Claude Code launches in a worktree. The SessionStart hook calls `comms.py auto-assign` to register the agent name, then `comms.py post` to announce the session.

2. **Agent works**: The agent reads files, writes code, runs tests. Before each tool use, the PreToolUse hook runs `comms.py check`. If another agent (or Nick) posted a message for this agent, it appears inline and the agent can act on it.

3. **Agent commits and pushes**: After a git push, the PostToolUse hook detects the git operation and posts to the group chat: "Web: pushed feat/user-profile to origin."

4. **Agent creates a PR**: The agent runs `gh pr create`. Other agents see the chat message and can review or coordinate.

5. **Copilot reviews**: GitHub Copilot automatically reviews the PR. The Actions workflow checks the review status. If comments exist, the agent reads them via `gh api`, fixes the code, pushes again, and waits for re-review.

6. **Gate passes, PR merges**: Once Copilot leaves zero comments, the gate status flips to `success`. The agent (or a sysadmin agent) merges the PR and posts a notification so all agents pull the latest changes.

## Configuration

The system uses three environment variables (all optional, with sensible defaults):

| Variable | Default | Description |
|----------|---------|-------------|
| `COMMS_DB_PATH` | `~/.claude/comms/messages.db` | Path to the SQLite database file. |
| `COMMS_AGENT_NAMES` | `Sysadmin,Web,Integr,App,Misc` | Comma-separated list of valid agent names for auto-assignment. |
| `COMMS_DIR_MAP` | Derived from directory name | Explicit mapping of directory names to agent names (e.g., `myapp-web:Web,myapp-api:API`). |

## Security Notes

- The SQLite database is local-only. It never leaves the developer's machine and requires no network access.
- No authentication is needed. All agents run under the same OS user on the same machine, so file-system permissions are sufficient.
- The database uses WAL mode and busy timeouts to handle concurrent writes from multiple agent processes safely.
- No secrets are stored in the comms database. It contains only coordination messages and session metadata.
- The `comms.sh` wrapper reads hook JSON from stdin and passes only the relevant fields to `comms.py`, avoiding injection of arbitrary data.
