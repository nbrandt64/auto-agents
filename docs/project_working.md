# How auto-agents Works — A Complete Guide

This document explains every aspect of the auto-agents system from the ground up. No prior knowledge assumed.

---

## Table of Contents

1. [The Problem](#the-problem)
2. [The Solution — In One Sentence](#the-solution)
3. [The Big Picture](#the-big-picture)
4. [Core Concepts](#core-concepts)
   - [Git Worktrees](#1-git-worktrees--isolated-workspaces)
   - [Sector Ownership](#2-sector-ownership--who-owns-what)
   - [Group Chat](#3-group-chat--how-agents-talk)
   - [Hooks](#4-hooks--the-automatic-nervous-system)
   - [Skills](#5-skills--reusable-workflows)
   - [Memory System](#6-memory--how-agents-remember)
   - [Copilot Review Gate](#7-copilot-review-gate--automated-code-review)
5. [The Agents](#the-agents)
6. [A Complete Workflow — Start to Finish](#a-complete-workflow--start-to-finish)
7. [Project Structure](#project-structure)
8. [Configuration Files](#configuration-files)
9. [The auto-agents CLI Tool](#the-auto-agents-cli-tool)
10. [The Comms API Server](#the-comms-api-server)
11. [Terminology Reference](#terminology-reference)
12. [Getting Started — Step by Step](#getting-started--step-by-step)
13. [Implementing in an Already Existing Project](#implementing-in-an-already-existing-project)
14. [CLI Internal Architecture](#cli-internal-architecture)

---

## The Problem

You have a project — say a web app with a frontend, backend, and database layer. You want to use Claude Code to build it. But running one Claude session means everything happens sequentially. Frontend waits while backend is being built. Database waits while frontend is being styled. Slow.

What if you could run **four Claude Code sessions at the same time**, each working on a different part of the codebase? One builds React components. Another builds Express routes. Another sets up the database. A fourth coordinates PRs and reviews.

But here's the problem: four agents on the same repo will create chaos. They'll edit the same files, create conflicting branches, and have no idea what the others are doing.

**auto-agents solves this.**

---

## The Solution

Four agents, each in its own isolated workspace, communicating through a shared group chat, submitting PRs that go through automated review before merging.

---

## The Big Picture

```
You (human architect)
  │
  ├── Group Chat ◄──────────────────────────────┐
  │     │                                        │
  │     ▼                                        │
  ├── Web Agent ────► PR ──► Copilot Review ──► Merge
  │   (frontend/)                                │
  │                                              │
  ├── API Agent ────► PR ──► Copilot Review ──► Merge
  │   (api/)                                     │
  │                                              │
  ├── Data Agent ───► PR ──► Copilot Review ──► Merge
  │   (data/)                                    │
  │                                              │
  └── GitHub Agent ──► Monitors PRs, assigns tasks, coordinates
      (cross-project)
```

**Your role shifts**: instead of writing code and reviewing diffs, you're in the group chat making architectural decisions. "Use SQLite, not Postgres." "The API should validate with Zod." "Web: make the task list sortable." The agents handle implementation. Copilot handles code review.

---

## Core Concepts

### 1. Git Worktrees — Isolated Workspaces

**What is a worktree?**

A worktree is a linked copy of your repository that lives in a separate directory but shares the same git history. Think of it as having multiple checkouts of the same repo side by side.

```
your-project/              ← Main repo (stays on default branch)
your-project-web/          ← Web agent works here (agent/web branch)
your-project-api/          ← API agent works here (agent/api branch)
your-project-data/         ← Data agent works here (agent/data branch)
your-project-github/       ← GitHub agent works here (agent/github branch)
```

**Key properties:**
- Each worktree can be on a **different branch** at the same time
- Two worktrees can **never** be on the same branch (git enforces this)
- All worktrees **share the same git history** — when one agent pushes a commit, all others can pull it
- Worktrees are **persistent** — you create them once and reuse them forever

**Why not just branches?**

Branches alone don't help — you'd still need to switch between them in the same directory, and you can only have one branch checked out at a time. Worktrees give each agent its own directory, so they can all work simultaneously without file system conflicts.

**Parking branches:**

Each agent has a "home" branch called a parking branch:
- `agent/web` — Web agent's home base
- `agent/api` — API agent's home base

When an agent finishes a task, it returns to its parking branch and pulls latest. When starting new work, it creates a feature branch from there. The parking branch is the stable landing zone between tasks.

---

### 2. Sector Ownership — Who Owns What

Even with separate workspaces, two agents could still edit the same file. Sector ownership prevents this by defining which agent owns which directories.

```
| Sector   | Directory    | Agent | Responsibility                        |
|----------|-------------|-------|---------------------------------------|
| Frontend | frontend/   | Web   | React components, styling, API client |
| API      | api/        | API   | Express routes, middleware, validation |
| Data     | data/       | Data  | Database schema, migrations, queries  |
| Shared   | shared/     | Any   | Types only — coordinate before changing |
```

**The rules are simple:**
- **Never modify files outside your sector** without asking in group chat first
- If you need a change in another sector, **send a message**: "API: please add GET /tasks/:id"
- Changes to **shared code** (like `shared/types.ts`) must be announced before committing

**How is this enforced?**

Through `CLAUDE.md` — a file in each worktree that tells the agent who it is and what it owns. Claude Code reads this at session start and naturally respects the boundaries. You'd be surprised how disciplined the agents are — they'll post a message like "Web: can you add a loading state?" rather than touching the frontend code themselves.

---

### 3. Group Chat — How Agents Talk

The group chat is where coordination happens. It's backed by a web API that all agents connect to.

**Message types:**

```
10:45:10  GitHub    CLAUDE.md updated on develop. All agents: pull latest.
10:45:33  Web       git: git checkout origin/develop -- CLAUDE.md
10:46:41  API       Data: the content table shows 'No Content Yet'. Are
                    records being saved as Content records?
10:50:54  Data      API: yes, records now saved to content table — PR #188
                    merged. After a rebuild, they should appear.
```

- **Direct messages**: Start with agent name — `API: please add rate limiting` — tagged `>>> FOR YOU` for the recipient
- **Broadcasts**: `All: switching to PostgreSQL, update connection strings`
- **Auto-posted**: Git operations are posted automatically by hooks

**How agents receive messages:**

Agents don't poll or check manually. A **hook** runs before every tool call and injects new messages into the agent's context. Messages just appear naturally as the agent works.

**How humans participate:**

You can join the group chat anytime:
```bash
auto-agents          # then /watch to monitor, or /chat to participate
```

You see the same messages agents see, and your messages appear to agents on their next tool call.

---

### 4. Hooks — The Automatic Nervous System

Hooks are Claude Code lifecycle events that trigger scripts automatically. They're what make the whole system work without agents needing special code.

**The four hooks:**

| Hook | When it fires | What it does |
|------|--------------|-------------|
| **SessionStart** | Agent starts a session | Registers the agent, posts "Session started" |
| **Stop** | Agent session ends | Posts "Session ended" |
| **PreToolUse** | Before every single tool call | Checks for new messages, injects them into context |
| **PostToolUse** | After Bash commands | Detects git operations, posts them to chat |

**PreToolUse is the magic hook.** Before every Read, Write, Bash, Grep, or any other tool call, it checks for new messages. This means:
- Agents see new messages within seconds of them being posted
- No explicit polling code needed
- Messages directed at the agent get `>>> FOR YOU` so the agent knows to act

**PostToolUse detects git operations.** When an agent runs `git push`, `git checkout`, or `gh pr merge`, the hook automatically posts it to the group chat. Other agents see what's happening without anyone manually announcing.

**Where hooks are configured:**

In `.claude/settings.json` inside your project directory:
```json
{
  "hooks": {
    "SessionStart": [
      {"hooks": [{"type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook session-start"}]}
    ],
    "PreToolUse": [
      {"hooks": [{"type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook check"}]}
    ]
  }
}
```

This file is **project-local** — anyone cloning the repo gets the hooks automatically.

---

### 5. Skills — Reusable Workflows

Skills are slash commands that agents can use. They're defined in `~/.claude/skills/` and loaded on demand.

**The four standard skills:**

| Skill | Command | What it does |
|-------|---------|-------------|
| **TDD** | `/tdd` | Test-driven development: write failing test, make it pass, refactor |
| **Review** | `/review` | Code review with structured checklist (correctness, security, quality) |
| **PR Process** | `/pr-process` | Batch-process open PRs: check reviews, fix comments, merge |
| **Copilot Loop** | `/copilot-loop` | Handle a single PR through the review cycle until merge |

**Example — TDD in action:**

An agent running `/tdd add user authentication` will:
1. **RED** — Write a failing test that defines expected behavior
2. **GREEN** — Write the minimum code to make the test pass
3. **REFACTOR** — Clean up while keeping tests green

Each step gets its own commit:
```
test: add failing test for user authentication
feat: implement user authentication to pass test
refactor: clean up authentication implementation
```

**Skills vs CLAUDE.md:**
- `CLAUDE.md` = identity, rules, always loaded
- Skills = specific workflows, loaded only when invoked, keeps base context lean

---

### 6. Memory — How Agents Remember

Claude Code sessions are ephemeral — when a session ends, the context is gone. The memory system bridges this gap with three layers:

**Layer 1: Private Memory (automatic)**
```
~/.claude/projects/<path>/memory/MEMORY.md
```
- Auto-managed by Claude Code
- Per-agent, per-project
- Survives across sessions
- Stores: stable patterns, key file paths, debugging insights
- Example: "The tasks table uses soft-delete with a deleted_at column"

**Layer 2: Shared Memory (DECISIONS.md)**
```
DECISIONS.md    ← in repo root, committed to git
```
- Visible to ALL agents (because worktrees share git history)
- Updated when: architectural decisions are made, API contracts established
- Example entries:
  - "Using Zod for API validation"
  - "The tasks table has a completed_at column"
  - "Frontend uses React Query for data fetching"

**Layer 3: Crash Recovery (CHECKPOINT.md)**
```
CHECKPOINT.md    ← in repo root
```
- Written before complex work begins
- Contains: current task, completed steps, next steps
- If a session crashes mid-task, the next session reads it and picks up exactly where it left off
- Cleared when the task is complete

---

### 7. Copilot Review Gate — Automated Code Review

Every PR goes through GitHub Copilot for review before it can merge. This is enforced by a GitHub Actions workflow.

**How it works:**

```
Agent creates PR
    │
    ▼
Copilot reviews (2-5 minutes)
    │
    ├── Comments found → Gate FAILS → Agent reads and fixes → Push → Repeat
    │
    └── No comments → Gate PASSES → Agent can merge
```

**The review gate workflow** (`require-copilot-review.yml`):
1. Triggers on PR events (opened, updated, reviewed)
2. Checks if Copilot has reviewed via GitHub API
3. Counts unresolved Copilot threads via GraphQL
4. Sets commit status to success (0 comments) or failure (N comments)
5. Branch protection requires this status to pass

**Typical cycle:**
- Most PRs clean up in 1-3 iterations
- Copilot catches: missing error handling, security issues, code quality problems
- Agent reads comments, fixes code, pushes, Copilot re-reviews
- When clean, agent merges

**What this replaces:**
Human code review. You no longer need to read every diff and leave comments. Copilot does that. You focus on architecture and design decisions.

---

## The Agents

### Specialist Agents (Web, API, Data)

Each specialist agent:
- **Owns a directory** (its sector)
- **Works on feature branches** created from its parking branch
- **Submits PRs** that go through Copilot review
- **Communicates** via group chat when it needs something from another sector
- **Uses `/tdd`** to build features test-first

### The GitHub Agent (Coordinator)

The GitHub agent is different:
- **Doesn't write application code** — it coordinates
- **Monitors PR queues** across all repos
- **Processes Copilot reviews** — reads comments, directs fixes
- **Assigns tasks** to specialist agents based on what it finds
- **Uses `/pr-process`** and **`/copilot-loop`** to manage the PR lifecycle
- **Is cross-project** — sees messages from all projects

---

## A Complete Workflow — Start to Finish

Here's what happens when an agent builds a feature, from launch to merge:

**1. Agent starts**
```
$ cd taskflow-web && claude
```
SessionStart hook fires → registers as "Web" agent → posts "Session started in taskflow-web"

**2. Agent reads its instructions**
- `CLAUDE.md`: "I am the Web agent. I own `frontend/`. Never modify other sectors."
- `DECISIONS.md`: "Using React Query. SQLite backend. Zod validation."
- `CHECKPOINT.md`: empty (no interrupted work)

**3. You give it a task**
```
> Build a task filtering component with status dropdown
```

**4. Agent creates feature branch and works**
```
git checkout -b feat/task-filtering
```
Uses `/tdd`: writes test, implements component, refactors. Commits each step.

**5. Another agent needs something**
The API agent posts: "Web: I need the Task type updated in shared/types.ts"

Before Web agent's next tool call, PreToolUse hook fires → checks for messages → sees `>>> FOR YOU` → Web agent responds: "On it, updating shared/types.ts now"

**6. Agent creates PR**
```
gh pr create --base main --title "feat: add task filtering"
```
PostToolUse hook detects this → posts to chat: "created PR #42"

**7. Copilot reviews**
- Copilot finds: "Missing error boundary for empty filter results"
- Gate status: FAIL

**8. Agent fixes and pushes**
- Reads Copilot's comment
- Adds error boundary
- Commits and pushes
- Copilot re-reviews → 0 comments → Gate PASSES

**9. Agent merges**
```
gh pr merge --squash
```
PostToolUse hook:
- Posts to chat: "merged PR #42"
- Auto-pulls main branch in the main repo directory

**10. Clean handoff**
```
git checkout agent/web     # Return to parking branch
git pull origin main       # Get latest
```
Ready for the next task. Other agents pull the merged changes on their next cycle.

---

## Project Structure

### The auto-agents framework repo

```
auto-agents/                           ← This repo (the framework)
├── README.md
├── DECISIONS.md                       ← Shared memory — architectural decisions
├── CHECKPOINT.md                      ← Crash recovery checkpoint
├── article.md                         ← How and why this works
├── tutorial.md                        ← Step-by-step setup guide
├── docs/
│   ├── architecture.md
│   ├── optional-hooks.md
│   └── project_working.md            ← This file
├── setup/
│   ├── auto-agents.py                 ← Unified CLI tool (all-in-one)
│   ├── auto-agents                    ← Shell wrapper
│   ├── comms.py                       ← DEPRECATED — superseded by auto-agents.py
│   ├── comms.sh                       ← DEPRECATED — superseded by auto-agents.py
│   ├── setup-worktrees.sh             ← DEPRECATED — use `auto-agents init` instead
│   ├── CLAUDE.md.template             ← Per-agent instructions template
│   ├── settings.json.example          ← Hook configuration example
│   ├── require-copilot-review.yml     ← GitHub Actions workflow
│   ├── server/                        ← Self-hosted comms API server
│   │   ├── server.py                  ← FastAPI + DynamoDB backend
│   │   ├── create_tables.py           ← Idempotent table creation
│   │   ├── requirements.txt
│   │   └── README.md
│   └── skills/                        ← Slash command workflows
│       ├── tdd/SKILL.md
│       ├── review/SKILL.md
│       ├── pr-process/SKILL.md
│       └── copilot-loop/SKILL.md
├── .github/
│   └── workflows/
│       └── require-copilot-review.yml ← Copilot review gate
└── sample-app/                        ← Example project to practice with
```

### What your project looks like after setup

```
your-project/                          ← Main repo
├── .claude/
│   └── settings.json                  ← Hooks (auto-generated by /init)
├── CLAUDE.md                          ← Agent instructions
├── DECISIONS.md                       ← Shared memory
├── CHECKPOINT.md                      ← Crash recovery
├── frontend/                          ← Web agent's sector
├── api/                               ← API agent's sector
├── data/                              ← Data agent's sector
└── shared/                            ← Shared code (coordinate changes)

your-project-web/                      ← Web agent's worktree
your-project-api/                      ← API agent's worktree
your-project-data/                     ← Data agent's worktree
your-project-github/                   ← GitHub agent's worktree
```

### What gets installed globally

```
~/.claude/
├── scripts/
│   ├── auto-agents.py                 ← The CLI tool (all-in-one)
│   ├── auto-agents                    ← Shell wrapper
│   ├── comms.py                       ← DEPRECATED (backward compat only)
│   └── comms.sh                       ← DEPRECATED (backward compat only)
├── comms/
│   ├── config                         ← API URL and secret
│   ├── projects.json                  ← Project registry
│   └── repl_history                   ← REPL command history
└── skills/
    ├── tdd/SKILL.md
    ├── review/SKILL.md
    ├── pr-process/SKILL.md
    └── copilot-loop/SKILL.md
```

---

## Configuration Files

| File | What it does | Who creates it |
|------|-------------|----------------|
| `~/.claude/comms/config` | Stores the comms API URL and secret | `/install` command |
| `~/.claude/comms/projects.json` | Registry of all your projects and their agents | `/init` command |
| `.claude/settings.json` | Claude Code hooks for this project (auto-generated) | `/init` command |
| `CLAUDE.md` | Agent identity, sector ownership, git workflow, communication rules | `/init` command (per worktree) |
| `DECISIONS.md` | Shared architectural decisions across all agents | `/init` command, then agents maintain it |
| `CHECKPOINT.md` | Crash recovery — current task state | Agents write before complex work |

### projects.json format

This is the central registry that replaces hardcoded configuration:

```json
{
  "version": 1,
  "projects": {
    "myapp": {
      "repo": "owner/myapp",
      "path": "/Users/you/code/myapp",
      "default_branch": "main",
      "agents": {
        "frontend": {
          "name": "Frontend",
          "sector": "src/frontend/",
          "description": "React UI, components"
        },
        "api": {
          "name": "API",
          "sector": "src/api/",
          "description": "Express routes, middleware"
        },
        "github": {
          "name": "GitHub",
          "sector": null,
          "cross_project": true,
          "description": "PR processing, CI"
        }
      }
    }
  }
}
```

---

## The auto-agents CLI Tool

The CLI is the main way to interact with the framework. It works in three modes:

### Mode 1: Interactive Menu (first run)

When you run `auto-agents` and you're not in a configured project:

```
  ╭───────────────────────────────────╮
  │  auto-agents v1.0                 │
  ╰───────────────────────────────────╯

  ? What would you like to do?

  > Check environment           /doctor
    Install auto-agents         /install
    Set up a new project        /init
    Exit                        /exit
```

### Mode 2: REPL (inside a project)

When you run `auto-agents` inside a configured project directory:

```
  auto-agents v1.0 — myapp (3 agents)
  Type /help for commands, /menu for setup options

auto-agents> /status
auto-agents> /watch
auto-agents> /post Web "please add the task filter"
```

### Mode 3: Direct commands (non-interactive)

For scripts, hooks, and CI:

```bash
auto-agents doctor                    # Check environment
auto-agents init                      # Set up project
auto-agents hook check                # Called by Claude Code hooks
auto-agents post -s "Web" "hello"     # Send a message
```

### All commands

| Command | Description |
|---------|-------------|
| `/doctor` | Check prerequisites (python3, git, gh, claude) and setup state |
| `/install` | One-time setup — copy scripts, configure API, install skills |
| `/init` | Interactive project wizard — creates everything you need |
| `/add-agent` | Add a new agent to the current project |
| `/remove-agent` | Remove an agent from the current project |
| `/start` | Launch all agents in Terminal tabs — macOS only, prompts for `--dangerously-skip-permissions` and `--begin-work` |
| `/status` | Show project config, agents, and worktree health |
| `/post` | Send a message to the group chat |
| `/watch` | Live-stream group chat messages |
| `/chat` | Interactive chat mode (send and receive) |
| `/history` | Show recent messages |
| `/menu` | Show the setup menu from within the REPL |
| `/help` | Show all available commands |
| `/exit` | Exit the REPL |

---

## The Comms API Server

The group chat client is built into `auto-agents.py`. It talks to a **server** hosted on AWS (DynamoDB + API routes). The server is deployed separately — ask your team lead for the API URL and secret. (The legacy standalone client `comms.py` is deprecated but kept for backward compatibility.)

**What the server provides:**
- Message storage and retrieval
- Agent registration
- Read cursors (tracking which messages each agent has seen)
- Project-scoped message filtering

**Configuration:** Store credentials in `~/.claude/comms/config`:
```
COMMS_API_URL="https://your-api-url.example.com"
COMMS_API_SECRET="your-secret"
```

**Without the server:**
- Everything else still works — worktrees, CLAUDE.md, hooks, skills, Copilot gate
- Agents can work in parallel independently
- They just can't communicate via group chat

**The API endpoints the client expects:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/comms/messages` | POST | Send a message |
| `/api/comms/messages` | GET | Get message history |
| `/api/comms/check` | GET | Get unread messages for a session |
| `/api/comms/agents` | POST | Register or auto-assign an agent |
| `/api/comms/agents` | GET | List registered agents |

---

## Terminology Reference

| Term | What it means |
|------|--------------|
| **Worktree** | A linked checkout of your repo in a separate directory. Each agent gets one. |
| **Parking branch** | An agent's "home" branch (e.g., `agent/web`). Returns here between tasks. |
| **Sector** | The directory an agent owns (e.g., `frontend/`). Don't touch other agents' sectors. |
| **Group chat** | The shared communication channel where agents coordinate. |
| **Hook** | A script that runs automatically at certain points in Claude Code's lifecycle. |
| **Skill** | A reusable workflow invoked with a slash command (e.g., `/tdd`). |
| **Ralph loop** | A structured task list processed sequentially — pick task, complete it, move on. |
| **Copilot review gate** | GitHub Actions workflow that blocks merges until Copilot approves with 0 comments. |
| **Private memory** | Per-agent persistent notes at `~/.claude/projects/.../MEMORY.md`. |
| **Shared memory** | `DECISIONS.md` — architectural decisions visible to all agents. |
| **Checkpoint** | `CHECKPOINT.md` — crash recovery file with current task state. |
| **Cross-project agent** | An agent (like GitHub) that sees messages from all projects, not just one. |
| **Direct message** | A message starting with an agent name: "API: please add endpoint" → tagged `>>> FOR YOU`. |
| **Comms** | Short for "communications" — the group chat system (client + API). |
| **PreToolUse** | Hook that fires before every tool call — this is how agents receive messages. |
| **PostToolUse** | Hook that fires after Bash commands — this is how git operations are announced. |

---

## Getting Started — Step by Step

1. **Install the CLI**: `python3 setup/auto-agents.py install`
2. **Go to your project**: `cd /path/to/your-project`
3. **Run the wizard**: `auto-agents init`
4. **Launch agents**: Open a terminal per agent, `cd` into its worktree, run `claude`
5. **Monitor**: Run `auto-agents` in the project dir, then `/watch` or `/chat`
6. **Give work**: Tell each agent what to build in its terminal
7. **Watch them coordinate**: Agents will communicate, create PRs, and merge through Copilot review

The system handles the rest — hooks post updates, agents check for messages, Copilot reviews PRs, and the GitHub agent keeps everything flowing.

---

## Implementing in an Already Existing Project

Your existing project has no knowledge of auto-agents. That's fine — auto-agents is installed **on your machine**, not inside your project. Here's the full process from zero.

### Prerequisites

1. Your project is a **git repository** with at least one commit
2. You have **python3**, **git**, **gh** (GitHub CLI), and **claude** (Claude Code) installed
3. You have access to a comms API server (URL + secret) — or you can skip group chat

### Step 1: Get the auto-agents framework

Clone the auto-agents framework repo somewhere on your machine. This is **not** inside your project — it's a separate repo that provides the tooling.

```bash
# Clone to any convenient location (e.g. ~/tools/)
git clone https://github.com/nbrandt64/auto-agents.git ~/tools/auto-agents
```

### Step 2: Run the installer

The installer copies the CLI scripts to `~/.claude/scripts/`, prompts for API credentials, and installs skills. This is a **one-time global setup** — it works for all your projects.

```bash
cd ~/tools/auto-agents
python3 setup/auto-agents.py install
```

The installer will:
- Copy `auto-agents.py` and its shell wrapper to `~/.claude/scripts/`
- Copy `CLAUDE.md.template` for agent instruction generation
- Prompt for comms API URL and secret (skip if you don't have a server yet)
- Install skills (`/tdd`, `/review`, `/pr-process`, `/copilot-loop`) to `~/.claude/skills/`
- Tell you how to add `~/.claude/scripts` to your PATH

### Step 3: Add to PATH

So that `auto-agents` works as a command from any directory:

```bash
# For zsh (default on macOS)
echo 'export PATH="$HOME/.claude/scripts:$PATH"' >> ~/.zshrc
source ~/.zshrc

# For bash
echo 'export PATH="$HOME/.claude/scripts:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Verify it works:
```bash
auto-agents --help
```

**If you don't want to modify PATH**, you can always run the CLI directly:
```bash
python3 ~/.claude/scripts/auto-agents.py <command>
```

### Step 4: Run the init wizard in your project

Now go to your existing project and run the wizard:

```bash
cd /path/to/your-existing-project
auto-agents init
```

The wizard will:
1. **Detect your repo** — recognizes the git root, default branch, and GitHub remote automatically
2. **Scan directories** — finds top-level directories (e.g. `src/`, `api/`, `frontend/`) and suggests one agent per directory
3. **Ask for customization** — you can rename agents, adjust sectors, add a cross-project GitHub agent, or define agents manually
4. **Create worktrees** — sibling directories next to your project (e.g. `your-project-web/`, `your-project-api/`)
5. **Generate config files** — `.claude/settings.json` (hooks), `CLAUDE.md` (agent instructions), `DECISIONS.md`, `CHECKPOINT.md`
6. **Register the project** — saves to `~/.claude/comms/projects.json`

**If you're not inside a git repo** when you run `auto-agents init`, it will ask you to provide the path to your project. It can even create the directory and `git init` for you.

### What changes in your repo

| What | Where | Impact |
|------|-------|--------|
| `.claude/settings.json` | Project root + each worktree | Hook config — gitignore-able |
| `CLAUDE.md` | Each worktree only | Agent instructions — not in main repo |
| `DECISIONS.md` | Project root | Shared memory — commit this |
| `CHECKPOINT.md` | Project root | Crash recovery — commit this |
| Sibling worktree dirs | Next to your project | Linked checkouts, don't touch main repo |

**Your existing code is untouched.** No files are modified. The wizard only adds new config files and creates worktree directories alongside (not inside) your project.

### Step 5: Customize for your architecture

If your project has a non-standard structure, you may want to:

- **Adjust sectors** in each worktree's `CLAUDE.md` — make sure each agent's sector matches your actual directory layout
- **Edit `DECISIONS.md`** — pre-populate with existing architectural decisions so agents know the codebase conventions (e.g. "Using PostgreSQL", "Frontend is Next.js with App Router")
- **Add `.claude/` to `.gitignore`** — the `settings.json` is project-local but you may not want it committed

### Step 6: Launch agents

Open a terminal per agent:
```bash
cd /path/to/your-project-web && claude    # Web agent
cd /path/to/your-project-api && claude    # API agent
cd /path/to/your-project-github && claude # GitHub agent
```

Monitor from the main project directory:
```bash
cd /path/to/your-project
auto-agents        # then /watch or /chat
```

### Step 7: Adding or removing agents later

```bash
cd /path/to/your-project
auto-agents
> /add-agent mobile     # Creates worktree, updates config, generates CLAUDE.md
> /remove-agent data    # Removes worktree, updates config
```

### Tips for existing projects

- **Start with 2-3 agents** — you can always add more later with `/add-agent`
- **The GitHub agent is optional** — only add it if you want automated PR coordination
- **Agents respect sector boundaries** — they won't modify files outside their assigned directories unless asked via group chat
- **Worktrees share git history** — when one agent merges a PR, others can `git pull` to get those changes
- **Nothing breaks if you stop** — worktrees are just linked checkouts; remove them anytime with `git worktree remove`
- **Existing CI/CD is unaffected** — the only new workflow is the optional Copilot review gate
- **No dependencies added to your project** — auto-agents lives in `~/.claude/`, not in your `node_modules` or `requirements.txt`

---

## CLI Internal Architecture

The `auto-agents.py` CLI is a single-file, zero-dependency Python script (~2000 lines) that consolidates all framework functionality.

### Key internal helpers

| Helper | Purpose | Used by |
|--------|---------|---------|
| `_format_check_messages()` | Format and print unread messages with directed-message tagging | `/check` REPL, hook handler, CLI dispatch |
| `_create_worktree()` | Create a parking branch and git worktree | `/init`, `/add-agent` |
| `_build_sector_table()` | Build markdown sector table from agents config | `/init`, `/add-agent` |
| `_render_claude_md()` | Apply template substitutions for CLAUDE.md generation | `/init`, `/add-agent` |
| `_resolve_or_create_repo()` | Prompt for a path, validate or create a git repo | `/init` (3 code paths) |
| `_find_file()` | Locate a file in setup dir, scripts dir, or git repo | Template loading, workflow copying |

### Three execution modes

1. **Interactive menu** — `auto-agents` with no args, not in a project → arrow-key menu
2. **REPL** — `auto-agents` with no args, inside a configured project → slash commands with tab completion
3. **CLI dispatch** — `auto-agents <command> [args]` → non-interactive, for scripts and hooks

### Hook handler

The built-in hook handler (`auto-agents.py hook <mode>`) replaces the legacy `comms.sh` script:
- Reads stdin JSON from Claude Code hooks
- Resolves agent names from `projects.json` (no hardcoded maps)
- No external dependencies (no `jq`, no `comms.py`)
- Logs errors to stderr (e.g. auto-pull failures) instead of silently swallowing them

### Legacy files

The following files are **deprecated** but kept for backward compatibility:

| File | Replacement |
|------|-------------|
| `comms.py` | Built into `auto-agents.py` (comms API layer) |
| `comms.sh` | Built into `auto-agents.py` (`hook` subcommand) |
| `setup-worktrees.sh` | Built into `auto-agents.py` (`init` and `add-agent` commands) |

These files have deprecation notices at the top. They still function if referenced directly, but new setups should use `auto-agents` exclusively.
