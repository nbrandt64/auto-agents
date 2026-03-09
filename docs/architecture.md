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
│         │   Group Chat API     │                          │
│         │  (DynamoDB + HTTP)   │                          │
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

The communication layer is a Python CLI (`auto-agents.py`) that talks to a shared web API (DynamoDB + FastAPI). It provides:

- **Messages**: timestamped messages with sender name, channel, and project, stored in DynamoDB with time-sorted keys (ULID).
- **Agent registration**: maps Claude Code session IDs to friendly names (Web, API, Data, etc.) via atomic name claims.
- **Read cursors**: each session tracks which messages it has already seen server-side, so the `check` command only surfaces new messages.

The CLI supports these commands: `post`, `check`, `chat`, `history`, `status`, `assign`, `auto-assign`, `resolve-name`, and `watch`. Agents primarily use `post` (send a message) and `check` (poll for new messages directed at them). All communication goes through the API via Bearer token auth.

### Hooks

Claude Code hooks in `settings.json` drive the system automatically:

- **SessionStart**: Registers the agent on the group chat and posts a join message. The agent name is derived from the working directory (e.g., `myapp-web/` becomes "Web").
- **SessionStop**: Posts a departure message so other agents know the session ended.
- **PreToolUse**: Before every tool invocation, runs `auto-agents.py hook check` to surface any new messages. Messages addressed to the current agent (e.g., `Web: please review the auth module`) are tagged `>>> FOR YOU`.
- **PostToolUse (Bash)**: After Bash commands that involve git operations, posts a summary to the chat (e.g., "pushed feat/login to origin"). Also detects `gh pr merge` and auto-pulls the default branch in the main repo directory so it stays in sync with merged PRs.

### Copilot Review Gate

A GitHub Actions workflow (`require-copilot-review.yml`) runs on a schedule and on `pull_request_review` events. It checks whether GitHub Copilot has reviewed the PR and left zero unresolved comments. If so, it sets a commit status ("Copilot Review Gate") to `success`, which unblocks merging. If comments remain, the status stays `pending`.

Agents are expected to poll for Copilot comments, fix them, push, and wait for re-review until the gate passes.

## Data Flow

1. **Agent starts**: Claude Code launches in a worktree. The SessionStart hook calls `auto-agents.py hook session-start` to register the agent name and announce the session.

2. **Agent works**: The agent reads files, writes code, runs tests. Before each tool use, the PreToolUse hook runs `auto-agents.py hook check`. If another agent (or the user) posted a message for this agent, it appears inline and the agent can act on it.

3. **Agent commits and pushes**: After a git push, the PostToolUse hook detects the git operation and posts to the group chat: "Web: pushed feat/user-profile to origin."

4. **Agent creates a PR**: The agent runs `gh pr create`. Other agents see the chat message and can review or coordinate.

5. **Copilot reviews**: GitHub Copilot automatically reviews the PR. The Actions workflow checks the review status. If comments exist, the agent reads them via `gh api`, fixes the code, pushes again, and waits for re-review.

6. **Gate passes, PR merges**: Once Copilot leaves zero comments, the gate status flips to `success`. The agent (or the GitHub agent) merges the PR and posts a notification so all agents pull the latest changes.

## Project Scoping

Messages in the comms system are scoped by **project**. Each agent is associated with a project (auto-detected from the working directory name), and the `check` command only surfaces messages from the same project plus `general` broadcasts.

This means agents working on different repos don't see each other's noise. A Web agent on project "taskflow" only sees messages tagged with "taskflow" or "general" -- not messages from agents on "other-project".

**Cross-project agents** are the exception. Agents like the GitHub agent that coordinate across repos see messages from all projects. Their `check` output includes a `[project]` tag on each message so they know which project it came from.

Project detection follows this priority:
1. Exact match in directory-to-project mapping (configured in `projects.json`)
2. Prefix match (e.g., directory `taskflow-web` matches prefix `taskflow`)
3. Falls back to `general`

## Configuration

The system uses a config file at `~/.claude/comms/config`:

| Variable | Description |
|----------|-------------|
| `COMMS_API_URL` | Base URL of the comms API (e.g., `https://www.example.com`) |
| `COMMS_API_SECRET` | Shared Bearer token for API authentication |

Environment variables override config file values. Agent names and project mappings are configured in `~/.claude/comms/projects.json` (created by `auto-agents init`).

## Memory & Checkpointing

Three layers of persistence reduce session ramp-up and handle crash recovery:

- **Private memory**: Claude Code's built-in auto memory (`~/.claude/projects/<path>/memory/MEMORY.md`). Per-agent, per-project. Survives across sessions. Agents save stable patterns and debugging insights here.
- **Shared memory**: A committed `DECISIONS.md` file in the repo root. All worktrees see it via shared git history. Agents record architectural decisions and conventions that affect other agents.
- **Checkpointing**: A `CHECKPOINT.md` file in the repo root. Agents write current task, completed steps, and next steps before complex work. On crash/freeze, the next session reads it and resumes. Cleared on task completion.

## Security Notes

- All API calls use Bearer token authentication (`COMMS_API_SECRET`).
- The config file (`~/.claude/comms/config`) contains the shared secret and should not be committed to version control.
- The API has a 3-second timeout on all calls. The `check` command fails silently on API errors to avoid blocking agent tool use.
- No application secrets are stored in comms messages — only coordination messages and session metadata.
- DynamoDB items have a 30-day TTL for automatic cleanup.
- The `auto-agents.py hook` handler reads hook JSON from stdin and passes only the relevant fields to the API, avoiding injection of arbitrary data.
