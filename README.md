# auto-agents

**Run multiple Claude Code agents in parallel with group chat coordination.**

## What This Is

A framework for running multiple Claude Code CLI sessions simultaneously on the same codebase, each in its own git worktree, communicating through a shared SQLite group chat. Agents coordinate work, avoid conflicts, and submit PRs that go through automated Copilot review before merging.

## How It Works

- **Git worktrees** give each agent its own working directory on the same repo, so they can work in parallel without stepping on each other.
- **Group chat** (SQLite-backed) lets agents send messages, see what others are doing, and receive directed instructions.
- **Claude Code hooks** automatically post session starts, git operations, and check for new messages before every tool use.
- **Copilot review gate** blocks PR merges until GitHub Copilot reviews pass with zero comments, enforced by a GitHub Actions workflow.

## Quick Start

1. **Clone this repo**

   ```bash
   git clone https://github.com/nbrandt64/auto-agents.git
   cd auto-agents
   ```

2. **Copy scripts into your Claude Code config**

   ```bash
   mkdir -p ~/.claude/scripts ~/.claude/comms
   cp setup/comms.py ~/.claude/scripts/comms.py
   cp setup/comms.sh ~/.claude/scripts/comms.sh
   chmod +x ~/.claude/scripts/comms.sh
   ```

3. **Configure Claude Code hooks**

   Merge `setup/settings.json.example` into your `~/.claude/settings.json` to register the SessionStart, SessionStop, PreToolUse, and PostToolUse hooks.

4. **Create worktrees for your project**

   ```bash
   # Edit setup/setup-worktrees.sh with your repo path and agent names, then:
   bash setup/setup-worktrees.sh
   ```

5. **Add a CLAUDE.md to each worktree**

   Use `setup/CLAUDE.md.template` as a starting point. Each agent gets its own identity, responsibilities, and branch conventions.

6. **Launch agents**

   Open a separate terminal for each worktree and run `claude` in each one. Agents will auto-register on the group chat and begin coordinating.

7. **(Optional) Add the Copilot review gate**

   Copy `setup/require-copilot-review.yml` into your repo's `.github/workflows/` directory.

## Repo Structure

```
auto-agents/
├── README.md
├── docs/
│   ├── architecture.md        # System design and data flow
│   └── article.md             # Full write-up
├── setup/
│   ├── comms.py               # Agent comms CLI
│   ├── comms.sh               # Hook wrapper script
│   ├── settings.json.example  # Claude Code hook config
│   ├── setup-worktrees.sh     # Worktree creation script
│   ├── CLAUDE.md.template     # Per-agent instructions template
│   └── require-copilot-review.yml  # GitHub Actions workflow
└── sample-app/
    ├── api/                   # Example backend agent scope
    ├── frontend/              # Example frontend agent scope
    ├── data/                  # Example data agent scope
    └── shared/                # Shared code between agents
```

## Read the Article

For the full story behind this system, see [article.md](article.md).

## License

MIT
