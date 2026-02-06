# Alex Onboarding — Zenvoy Agent Setup

## What You're Getting

You'll run Claude Code agents that coordinate with Nick's agents via shared group chat. Your agents:

| Directory | Agent Name | Role |
|-----------|-----------|------|
| `zenvoy-integr1/` | Integr1 | Integration work |
| `zenvoy-integr2/` | Integr2 | Integration work |
| `zenvoy-ops/` | AlexOps | Cross-project ops (sees all projects) |
| `zenvoy-alexmisc/` | AlexMisc | General tasks |

Nick's agents: Sysadmin, Web, App, Misc

## Quick Setup

### 1. Clone the Zenvoy Repo

```bash
cd ~/projects
gh repo clone nbrandt64/zenvoy
cd zenvoy
```

### 2. Create Your Worktrees

```bash
DEFAULT_BRANCH=develop

for agent in integr1 integr2 alexops alexmisc; do
  git branch "agent/$agent" "$DEFAULT_BRANCH" 2>/dev/null || true
done

git worktree add ../zenvoy-integr1 agent/integr1
git worktree add ../zenvoy-integr2 agent/integr2
git worktree add ../zenvoy-ops agent/alexops
git worktree add ../zenvoy-alexmisc agent/alexmisc
```

### 3. Install Comms Scripts

```bash
gh repo clone nbrandt64/auto-agents ~/projects/auto-agents

mkdir -p ~/.claude/scripts ~/.claude/comms
cp ~/projects/auto-agents/setup/comms.py ~/.claude/scripts/comms.py
cp ~/projects/auto-agents/setup/comms.sh ~/.claude/scripts/comms.sh
chmod +x ~/.claude/scripts/comms.sh
```

### 4. Configure Comms (get secret from Nick)

```bash
cat > ~/.claude/comms/config << 'EOF'
COMMS_API_URL=https://www.zenvoy.com
COMMS_API_SECRET=<GET FROM NICK>
EOF
```

### 5. Add Hooks to Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "bash ~/.claude/scripts/comms.sh session-start", "timeout": 5}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "bash ~/.claude/scripts/comms.sh session-end", "timeout": 5}]}],
    "PreToolUse": [{"hooks": [{"type": "command", "command": "bash ~/.claude/scripts/comms.sh check", "timeout": 5}]}],
    "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "bash ~/.claude/scripts/comms.sh git-detect", "timeout": 5}]}]
  }
}
```

### 6. Create AGENT.md in Each Worktree

Each agent needs an `AGENT.md` file in its directory (not tracked by git).

**zenvoy-integr1/AGENT.md:**
```markdown
# Agent: Integr1

You are **Integr1** — an integration agent.

## Responsibilities
- Integration implementations
- OAuth flows, API clients
- External service connections

## Parking Branch
`agent/integr1`
```

Copy and customize for each agent (Integr2, AlexOps, AlexMisc).

### 7. Test

```bash
# Test comms
python3 ~/.claude/scripts/comms.py history 5

# Test auto-assign
cd ~/projects/zenvoy-integr1
python3 ~/.claude/scripts/comms.py auto-assign test "$(pwd)"
# Should print: Integr1
```

### 8. Launch

```bash
cd ~/projects/zenvoy-integr1 && claude
```

## How Comms Works

- **Auto-join:** Agents register on the group chat when they start
- **Messages before tools:** New messages appear before every tool use
- **`>>> FOR YOU`:** Act on messages addressed to you
- **Send messages:** `python3 ~/.claude/scripts/comms.py post -s "Integr1" "message"`

## Git Workflow

1. Create feature branch: `git checkout -b feat/description`
2. Make changes, commit, push
3. Create PR: `gh pr create --base develop`
4. Wait for Copilot review, fix comments
5. After merge: `git checkout agent/integr1 && git pull origin develop`

**Never push directly to develop.**

## Key Files

- `CLAUDE.md` — Shared project instructions (tracked)
- `LEARNINGS.md` — Shared gotchas (tracked, read and contribute!)
- `AGENT.md` — Your agent's identity (untracked, per-worktree)

## Detailed Guide

See `auto-agents/docs/alex-setup.md` for full step-by-step instructions.
