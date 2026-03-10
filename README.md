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
- **Persistent memory** gives agents long-term knowledge (private auto memory), shared decisions (`DECISIONS.md`), and crash recovery (`CHECKPOINT.md`).

## Quick Start (CLI)

The `auto-agents` CLI replaces the manual multi-step setup with an interactive wizard:

```bash
# 1. Clone this repo
git clone https://github.com/nbrandt64/auto-agents.git
cd auto-agents

# 2. Run the installer (copies scripts, configures API, installs skills)
python3 setup/auto-agents.py install

# 3. Go to your project repo and run the init wizard
cd /path/to/your-project
auto-agents init
```

The `/init` wizard will interactively:
- Detect your git repo and default branch
- Ask for project name, GitHub repo, and agent definitions
- Create git worktrees for each agent
- Generate `.claude/settings.json` with hooks (project-local, not global)
- Generate per-agent `CLAUDE.md` files from template
- Create `DECISIONS.md` and `CHECKPOINT.md`
- Register the project in `~/.claude/comms/projects.json`
- Optionally set up the Copilot review gate workflow

After init, run `auto-agents` in your project to get a REPL with slash commands:

```
auto-agents> /status        # Show project config and agents
auto-agents> /watch         # Watch group chat in real-time
auto-agents> /post Web "please add GET /tasks/:id"
auto-agents> /add-agent mobile   # Add a new agent
auto-agents> /doctor        # Check environment prerequisites
```

### Quick Start (Manual)

<details>
<summary>Click to expand manual setup steps (legacy)</summary>

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

   ```bash
   cat > ~/.claude/comms/config << 'EOF'
   COMMS_API_URL=https://your-api-host.com
   COMMS_API_SECRET=your-shared-secret
   EOF
   ```

4. **Configure Claude Code hooks**

   Merge `setup/settings.json.example` into your `~/.claude/settings.json`.

5. **Create worktrees for your project**

   ```bash
   bash setup/setup-worktrees.sh
   ```

6. **Install skills (optional)**

   ```bash
   cp -r setup/skills/* ~/.claude/skills/
   ```

   This gives all agents access to `/begin-work`, `/tdd`, `/review`, `/pr-process`, and `/copilot-loop` slash commands. Customize repo names in the PR skills to match your setup.

7. **Add a CLAUDE.md to each worktree** from `setup/CLAUDE.md.template`

8. **Launch agents**

   Open a separate terminal for each worktree and run `claude` in each one, or use `auto-agents start` on macOS to open all tabs at once:

   ```bash
   auto-agents start                        # interactive prompts
   auto-agents start --skip-permissions     # skip dangerously-skip-permissions prompt
   auto-agents start --begin-work           # auto-run /begin-work on startup
   ```

   Agents will auto-register on the group chat and begin coordinating.

9. **(Optional) Add the Copilot review gate**

   Copy `setup/require-copilot-review.yml` into your repo's `.github/workflows/` directory.

</details>

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

With the `auto-agents` CLI, agent names and project scoping are configured in `~/.claude/comms/projects.json` (created by `/init`). No code editing required.

With legacy `comms.py`, agent names are auto-assigned from directory names:

- Directory suffixes map to names: `myproject-web` → `Web`, `myproject-api` → `API`
- Built-in names: `GitHub`, `Web`, `App`, `Misc` (customize in `comms.py` `FRIENDLY_NAMES`)
- Custom mappings: add exact directory-to-name entries in `comms.py` `DIR_MAP`

## What It Looks Like

Here's an actual group chat session with four agents working on the same codebase:

```
10:45:10  GitHub      CLAUDE.md updated on develop. All agents: pull latest.
10:45:33  Web         git: git checkout origin/develop -- CLAUDE.md
10:46:11  Data        git: git fetch origin develop && git merge origin/develop
10:46:25  API         git: git fetch origin develop -- CLAUDE.md
10:46:41  API         Data: the content table shows 'No Content Yet'. Are synced
                      records being saved as Content records? Or only going to a
                      different table?
10:50:54  Data        API: yes, records are now saved to the content table — PR #188
                      just merged. Previously they only went to the facts table.
                      After a rebuild + sync, they should appear in the browser.
10:53:04  API         Data: thanks, user is rebuilding now
11:00:34  Web         git: git push -u origin feat/contact-page
...
16:20:43  GitHub      Web: Release CI builds (24MB artifact) but upload fails with
                      413 — Lambda 6MB payload limit. Need either presigned S3
                      upload or metadata-only API call. Please fix the release API.
16:25:11  GitHub      Data: PRs #237, #238, #239 all have Copilot review comments.
                      Please address.
16:26:29  Web         GitHub: saw your message about the 413. I'll fix the release
                      API with a presigned S3 upload approach. Picking this up now.
16:31:47  Web         git: git checkout -b fix/release-presigned-url
16:36:47  Web         git: git push fix/release-presigned-url
```

Agents address each other by name (`Web:`, `Data:`), and directed messages show up as `>>> FOR YOU` in the recipient's terminal.

The **GitHub agent** is the central coordinator across all projects. It handles GitHub operations (PRs, CI, branch protection), monitors error logs, and assigns tasks to specialist agents based on what it finds. Specialist agents (Web, API, Data, etc.) own their code sectors and focus on implementation.

## Repo Structure

```
auto-agents/
├── README.md
├── DECISIONS.md               # Shared memory — architectural decisions
├── CHECKPOINT.md              # Crash recovery checkpoint
├── article.md                 # How and why this works
├── tutorial.md                # Step-by-step setup guide
├── docs/
│   ├── architecture.md        # System design and data flow
│   ├── optional-hooks.md      # Optional hook patterns for code quality
│   └── project_working.md     # Complete guide — concepts, CLI internals, setup
├── setup/
│   ├── auto-agents.py         # Unified CLI — menu, REPL, hooks
│   ├── auto-agents            # Shell wrapper for auto-agents.py
│   ├── comms.py               # Agent comms CLI (legacy, still works)
│   ├── comms.sh               # Hook wrapper script (legacy, still works)
│   ├── settings.json.example  # Claude Code hook + env config
│   ├── setup-worktrees.sh     # Worktree creation script (legacy)
│   ├── start-agents.sh        # Launch all agents in Terminal tabs — legacy, use 'auto-agents start'
│   ├── CLAUDE.md.template     # Per-agent instructions template
│   ├── require-copilot-review.yml  # GitHub Actions workflow
│   ├── server/                # Self-hosted comms API server
│   │   ├── server.py          # FastAPI + DynamoDB backend
│   │   ├── create_tables.py   # Idempotent DynamoDB table creation
│   │   ├── requirements.txt   # Python dependencies
│   │   └── README.md          # Server setup guide
│   └── skills/                # Reusable slash command workflows
│       ├── begin-work/SKILL.md    # /begin-work — session startup orientation
│       ├── tdd/SKILL.md       # /tdd — test-driven development cycle
│       ├── review/SKILL.md    # /review — code review checklist
│       ├── pr-process/SKILL.md    # /pr-process — batch PR processing
│       └── copilot-loop/SKILL.md  # /copilot-loop — single PR review loop
├── .github/
│   └── workflows/
│       └── require-copilot-review.yml  # Copilot review gate
└── sample-app/
    ├── api/                   # Example backend agent scope
    ├── frontend/              # Example frontend agent scope
    ├── data/                  # Example data agent scope
    └── shared/                # Shared code between agents
```

## CLI Reference

The `auto-agents` CLI works in three modes:

| Mode | When | What happens |
|------|------|-------------|
| **Menu** | `auto-agents` (no args, not in project) | Arrow-key menu: Doctor / Install / Init / Exit |
| **REPL** | `auto-agents` (no args, in configured project) | Interactive prompt with `/commands` and tab completion |
| **Direct** | `auto-agents <command> [args]` | Non-interactive, for scripts and hooks |

### Setup Commands

| Command | Description |
|---------|-------------|
| `/doctor` | Check prerequisites (python3, git, gh, claude) and setup state |
| `/install` | Copy scripts to `~/.claude/scripts/`, configure API, install skills |
| `/init` | Interactive wizard — worktrees, hooks, CLAUDE.md, projects.json |
| `/add-agent <suffix>` | Add an agent — creates worktree, updates config, notifies chat |
| `/remove-agent <suffix>` | Remove an agent — removes worktree, updates config |

### Runtime Commands

| Command | Description |
|---------|-------------|
| `/start` | Launch all agents in Terminal tabs (macOS) |
| `/status` | Show project info, agents, and worktree status |
| `/post <sender> <message>` | Send a message to the group chat |
| `/check <session_id>` | Check unread messages for a session |
| `/watch` | Live-stream new messages (Ctrl+C to stop) |
| `/chat` | Interactive chat mode with real-time polling |
| `/history [n] [project]` | Show recent messages |

### Configuration

The CLI uses `~/.claude/comms/projects.json` as a central project registry, replacing hardcoded dictionaries in `comms.py`:

```json
{
  "version": 1,
  "projects": {
    "myapp": {
      "repo": "owner/myapp",
      "path": "/Users/you/code/myapp",
      "default_branch": "main",
      "agents": {
        "frontend": { "name": "Frontend", "sector": "src/frontend/", "description": "React UI" },
        "github": { "name": "GitHub", "sector": null, "cross_project": true, "description": "PR processing" }
      }
    }
  }
}
```

### Hook Handler

The CLI includes a built-in hook handler that replaces `comms.sh` (no `jq` dependency):

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook session-start"}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook session-end"}]}],
    "PreToolUse": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook check"}]}],
    "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook git-detect"}]}]
  }
}
```

Hooks are generated per-machine by `auto-agents init` into each worktree's `.claude/settings.json`. Since `.claude/` is typically `.gitignore`d, each developer runs the init wizard to generate their own hooks.

## Read More

- [Complete Guide](docs/project_working.md) -- Concepts, CLI internals, setup for existing projects
- [Article](article.md) -- How and why this system works
- [Tutorial](tutorial.md) -- Step-by-step setup guide
- [Architecture](docs/architecture.md) -- System design and data flow
- [Optional Hooks](docs/optional-hooks.md) -- Hook patterns for code quality

## License

MIT
