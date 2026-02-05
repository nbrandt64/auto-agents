# Alex Setup Guide — Zenvoy Agent Comms

## Overview

You'll set up 4 Claude Code agents that coordinate via shared group chat:

| Directory | Agent Name | Role |
|-----------|-----------|------|
| `zenvoy-integr1/` | Integr1 | Integration work |
| `zenvoy-integr2/` | Integr2 | Integration work |
| `zenvoy-ops/` | AlexOps | Cross-project ops (sees all projects) |
| `zenvoy-alexmisc/` | AlexMisc | General tasks |

## Prerequisites

- macOS or Linux
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed
- [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated
- Access to the `nbrandt64/zenvoy` repo

## Step 1: Clone the Zenvoy Repo

```bash
cd ~/projects   # or wherever you keep repos
gh repo clone nbrandt64/zenvoy
cd zenvoy
```

## Step 2: Create Agent Worktrees

```bash
# From inside the zenvoy repo directory:
DEFAULT_BRANCH=develop

# Create parking branches
for agent in integr1 integr2 alexops alexmisc; do
  git branch "agent/$agent" "$DEFAULT_BRANCH" 2>/dev/null || true
done

# Create worktrees
git worktree add ../zenvoy-integr1 agent/integr1
git worktree add ../zenvoy-integr2 agent/integr2
git worktree add ../zenvoy-ops agent/alexops
git worktree add ../zenvoy-alexmisc agent/alexmisc
```

Verify:
```bash
git worktree list
```

## Step 3: Install Comms Scripts

```bash
# Clone auto-agents (if not already)
gh repo clone nbrandt64/auto-agents ~/projects/auto-agents

# Copy scripts
mkdir -p ~/.claude/scripts ~/.claude/comms
cp ~/projects/auto-agents/setup/comms.py ~/.claude/scripts/comms.py
cp ~/projects/auto-agents/setup/comms.sh ~/.claude/scripts/comms.sh
chmod +x ~/.claude/scripts/comms.sh
```

## Step 4: Configure Comms Backend

Create `~/.claude/comms/config`:

```bash
cat > ~/.claude/comms/config << 'EOF'
COMMS_API_URL=https://www.zenvoy.com
COMMS_API_SECRET=<ask Nick for the secret>
EOF
```

Test it:
```bash
python3 ~/.claude/scripts/comms.py history 5
```

You should see recent messages from the group chat.

## Step 5: Configure Claude Code Hooks

Add these hooks to your `~/.claude/settings.json`. If the file doesn't exist, create it. If it exists, merge the `hooks` section:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/scripts/comms.sh session-start",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/scripts/comms.sh session-end",
            "timeout": 5
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/scripts/comms.sh check",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/scripts/comms.sh git-detect",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## Step 6: Add CLAUDE.md to Each Worktree

Each agent needs a `CLAUDE.md` in its worktree root. Create one per agent. Example for Integr1:

```markdown
# CLAUDE.md — Zenvoy (Integr1)

## Agent Identity

You are **Integr1** — an integration agent working on the zenvoy project.

## Git Workflow

You are in a persistent worktree. Your workflow:

1. Create a feature branch: `git checkout -b feat/description`
2. Make changes, commit, push
3. Create PR: `gh pr create --base develop --title "..." --body "..."`
4. Wait for Copilot review, fix any comments, push again
5. After merge: `git checkout agent/integr1 && git pull origin develop`

**Never push directly to develop.**

## Group Chat

Messages appear automatically before each tool use.
- `>>> FOR YOU` — act on it
- Messages to other agents — read for context

Send messages:
\`\`\`bash
python3 ~/.claude/scripts/comms.py post -s "Integr1" "your message"
\`\`\`
```

Repeat for each agent, replacing the name and parking branch.

## Step 7: Test Everything

```bash
# Test auto-assign
cd ~/projects/zenvoy-integr1
python3 ~/.claude/scripts/comms.py auto-assign test-session-alex "$(pwd)"
# Should print: Integr1

# Test posting
python3 ~/.claude/scripts/comms.py post -s "Integr1" -p "zenvoy" "test message from Alex"

# Test check
python3 ~/.claude/scripts/comms.py check test-session-alex
```

## Step 8: Launch Agents

Open a terminal for each worktree and start Claude Code:

```bash
# Terminal 1
cd ~/projects/zenvoy-integr1 && claude

# Terminal 2
cd ~/projects/zenvoy-integr2 && claude

# Terminal 3
cd ~/projects/zenvoy-ops && claude

# Terminal 4
cd ~/projects/zenvoy-alexmisc && claude
```

Agents auto-register on the group chat when they start.

## Agent Names Reference

All registered agent names across the team:

| Name | Owner | Directory | Cross-Project |
|------|-------|-----------|---------------|
| Sysadmin | Nick | github/, zenvoy-sysadmin/ | Yes |
| Web | Nick | zenvoy-web/ | No |
| App | Nick | zenvoy-app/ | No |
| Misc | Nick | zenvoy-misc/ | No |
| Integr1 | Alex | zenvoy-integr1/ | No |
| Integr2 | Alex | zenvoy-integr2/ | No |
| AlexOps | Alex | zenvoy-ops/ | Yes |
| AlexMisc | Alex | zenvoy-alexmisc/ | No |

## Communicating with Nick's Agents

Address messages to specific agents by prefixing their name:

```bash
python3 ~/.claude/scripts/comms.py post -s "Integr1" "Web: can you add the OAuth callback route?"
python3 ~/.claude/scripts/comms.py post -s "AlexOps" "nick: PR #270 ready for review"
```

## Watching the Chat

Monitor all messages in real time:

```bash
python3 ~/.claude/scripts/comms.py watch
```

Interactive chat mode (send and receive):

```bash
python3 ~/.claude/scripts/comms.py chat -p zenvoy
```
