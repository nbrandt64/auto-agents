# Agent OS Integration

## What is Agent OS

[Agent OS](https://buildermethods.com/agent-os) is a framework for managing coding standards in AI-powered development. It provides a structured way to discover, organize, and inject standards into your project's CLAUDE.md files so that every AI coding agent follows consistent patterns.

Agent OS focuses on the *quality layer* -- what standards your agents follow. auto-agents focuses on the *coordination layer* -- how agents work together. The two are complementary.

## How They Complement Each Other

| Concern | auto-agents | Agent OS |
|---------|-------------|----------|
| Agent isolation | Git worktrees | -- |
| Agent communication | SQLite group chat | -- |
| Code review automation | Copilot review gate | -- |
| Standards discovery | -- | `discover` command |
| Standards injection | -- | `inject` command |
| Standards consistency | Shared CLAUDE.md via git | Standards profiles |
| Planning & architecture | -- | `shape` command |

**auto-agents** ensures agents don't step on each other and can communicate. **Agent OS** ensures they all write code the same way.

## Key Agent OS Concepts

### Standards

Standards are documented rules for how code should be written -- naming conventions, file organization, error handling, testing patterns, etc. Agent OS organizes these as markdown files that get referenced from CLAUDE.md.

### Profiles

A profile is a collection of standards scoped to a project or team. A "base" profile provides defaults, and project-level profiles override or extend them.

### Commands

- **discover** -- Scans your codebase and existing docs to identify implicit standards
- **inject** -- Writes discovered standards into your CLAUDE.md as `@references`
- **shape** -- Uses standards to generate implementation plans before writing code

## Using Together

### Setup Flow

```
1. Set up auto-agents (worktrees, comms, hooks)
         |
2. Install Agent OS in your project
         |
3. Run discover → identify your coding standards
         |
4. Run inject → standards go into CLAUDE.md
         |
5. Git push → all worktrees pull the updated CLAUDE.md
         |
6. Every agent now follows the same standards
```

### Step by Step

1. **Set up auto-agents** as described in the [tutorial](../tutorial.md). You now have multiple worktrees with agents communicating via group chat.

2. **Install Agent OS** in your project root (the main repo directory, not a worktree):

   ```bash
   cd /path/to/your-project
   # Follow Agent OS installation at https://buildermethods.com/agent-os
   ```

3. **Discover standards** from your existing codebase:

   ```bash
   # Agent OS scans your code and docs to identify patterns
   agent-os discover
   ```

4. **Inject into CLAUDE.md**:

   ```bash
   # Adds @references to your standards files in CLAUDE.md
   agent-os inject
   ```

5. **Commit and push** so all worktrees get the updated standards:

   ```bash
   git add -A && git commit -m "chore: add coding standards via Agent OS"
   git push
   ```

6. **Pull in each worktree**:

   ```bash
   # In each agent worktree:
   git pull origin main
   ```

   Now every agent session reads the same CLAUDE.md with the same standards.

### Architecture

```
┌─────────────────────────────────────────────────┐
│                Your Project Repo                 │
│                                                  │
│  CLAUDE.md ◄── Agent OS injects standards        │
│  .agent-os/                                      │
│    └── standards/                                │
│         ├── naming.md                            │
│         ├── error-handling.md                    │
│         └── testing.md                           │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Worktree  │  │ Worktree  │  │ Worktree  │    │
│  │ -web/     │  │ -api/     │  │ -data/    │    │
│  │           │  │           │  │           │    │
│  │ Same      │  │ Same      │  │ Same      │    │
│  │ CLAUDE.md │  │ CLAUDE.md │  │ CLAUDE.md │    │
│  │ Same      │  │ Same      │  │ Same      │    │
│  │ standards │  │ standards │  │ standards │    │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  │
│        └───────────┬───┴───────────────┘        │
│                    │                             │
│         ┌──────────▼──────────┐                  │
│         │   SQLite Group Chat  │                 │
│         │   (auto-agents)      │                 │
│         └─────────────────────┘                  │
└─────────────────────────────────────────────────┘
```

All worktrees share the same `.git` directory, so they all have access to the same CLAUDE.md and standards files. When Agent OS updates standards in the main repo, a simple `git pull` in each worktree propagates the changes to every agent.

## Without Agent OS

auto-agents works fine without Agent OS. You can manually write your CLAUDE.md with whatever standards you want. Agent OS simply automates the discovery and maintenance of those standards -- it's an optional enhancement, not a requirement.
