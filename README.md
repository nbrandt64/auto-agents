# auto-agents

**Run multiple Claude Code agents in parallel with group chat coordination.**

## What This Is

A framework for running multiple Claude Code CLI sessions simultaneously on the same codebase, each in its own git worktree, communicating through a shared group chat. Agents coordinate work, avoid conflicts, and submit PRs that go through automated Copilot review before merging.

Supports two communication backends:
- **Web API** (recommended) — shared DynamoDB-backed API, works across multiple machines
- **Local SQLite** — single-machine only (legacy)

## How It Works

- **Git worktrees** give each agent its own working directory on the same repo, so they can work in parallel without stepping on each other.
- **Group chat** (web API or SQLite-backed) lets agents send messages, see what others are doing, and receive directed instructions.
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

3. **Configure the comms backend**

   For **web API mode** (recommended for multi-machine teams), create a config file:

   ```bash
   cat > ~/.claude/comms/config << 'EOF'
   COMMS_API_URL=https://your-api-host.com
   COMMS_API_SECRET=your-shared-secret
   EOF
   ```

   Get the API URL and secret from your team lead. If no config file exists, comms falls back to local SQLite mode.

4. **Configure Claude Code hooks**

   Merge `setup/settings.json.example` into your `~/.claude/settings.json` to register the SessionStart, SessionStop, PreToolUse, and PostToolUse hooks.

5. **Create worktrees for your project**

   ```bash
   # Edit setup/setup-worktrees.sh with your repo path and agent names, then:
   bash setup/setup-worktrees.sh
   ```

6. **Add a CLAUDE.md to each worktree**

   Use `setup/CLAUDE.md.template` as a starting point. Each agent gets its own identity, responsibilities, and branch conventions.

7. **Launch agents**

   Open a separate terminal for each worktree and run `claude` in each one. Agents will auto-register on the group chat and begin coordinating.

8. **(Optional) Add the Copilot review gate**

   Copy `setup/require-copilot-review.yml` into your repo's `.github/workflows/` directory.

## Configuration

### Web API Mode (recommended)

Create `~/.claude/comms/config`:

```
COMMS_API_URL=https://your-api-host.com
COMMS_API_SECRET=your-shared-secret
```

The config file is sourced by `comms.sh` and read by `comms.py`. Environment variables override config file values.

| Variable | Description |
|----------|-------------|
| `COMMS_API_URL` | Base URL of the comms API (e.g., `https://example.com`) |
| `COMMS_API_SECRET` | Shared Bearer token for API authentication |

### Agent Name Assignment

Agent names are auto-assigned from the working directory name:

- Directory suffixes map to names: `myproject-web` → `Web`, `myproject-app` → `App`
- Built-in names: `Sysadmin`, `Web`, `Integr`, `App`, `Misc`
- Exact directory mappings: `github` → `Sysadmin`, `signaturefinder` → `SignatureFinder`, `poker-ai` → `PokerAI`

Project scoping is also derived from directories: `myproject-web` → project `myproject`.

## Repo Structure

```
auto-agents/
├── README.md
├── article.md                 # How and why this works
├── tutorial.md                # Step-by-step setup guide
├── docs/
│   ├── architecture.md        # System design and data flow
│   ├── agent-os-integration.md # Using with Agent OS for consistent standards
│   └── optional-hooks.md      # Optional hook patterns for code quality
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

## Read More

- [Article](article.md) -- How and why this system works
- [Tutorial](tutorial.md) -- Step-by-step setup guide
- [Architecture](docs/architecture.md) -- System design and data flow
- [Agent OS Integration](docs/agent-os-integration.md) -- Pairing with Agent OS for consistent standards
- [Optional Hooks](docs/optional-hooks.md) -- Hook patterns for code quality

## License

MIT
