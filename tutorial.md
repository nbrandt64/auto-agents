# Tutorial: Set It Up

Here's how to get this running with the sample app included in this repo.

## Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated
- `jq` installed (`brew install jq` on macOS)
- Python 3.6+
- A GitHub account with Copilot enabled

## Step 1: Clone this repo

```bash
git clone https://github.com/nbrandt64/auto-agents.git
cd auto-agents
```

## Step 2: Install the comms scripts

Copy the comms system into your Claude Code config directory:

```bash
mkdir -p ~/.claude/scripts ~/.claude/comms
cp setup/comms.py ~/.claude/scripts/comms.py
cp setup/comms.sh ~/.claude/scripts/comms.sh
chmod +x ~/.claude/scripts/comms.sh
```

## Step 3: Configure the comms backend

Create a config file with the API URL and shared secret (get these from your team lead):

```bash
cat > ~/.claude/comms/config << 'EOF'
COMMS_API_URL=https://your-api-host.com
COMMS_API_SECRET=your-shared-secret
EOF
```

## Step 4: Configure Claude Code hooks

Merge the hooks from `setup/settings.json.example` into your Claude Code settings. If you don't have existing hooks, you can copy it directly:

```bash
# If no existing settings:
cp setup/settings.json.example ~/.claude/settings.json

# If you have existing settings, manually merge the hooks section
```

The hooks config should look like this:

```json
{
  "env": {
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "80"
  },
  "hooks": {
    "SessionStart": [
      { "type": "command", "command": "bash ~/.claude/scripts/comms.sh session-start" }
    ],
    "Stop": [
      { "type": "command", "command": "bash ~/.claude/scripts/comms.sh session-end" }
    ],
    "PreToolUse": [
      { "type": "command", "command": "bash ~/.claude/scripts/comms.sh check" }
    ],
    "PostToolUse": [
      { "matcher": "Bash", "type": "command", "command": "bash ~/.claude/scripts/comms.sh git-detect" }
    ]
  }
}
```

## Step 5: Install skills

Copy the example skills so all agents have access to `/begin-work`, `/tdd`, `/review`, `/pr-process`, and `/copilot-loop`:

```bash
cp -r /path/to/auto-agents/setup/skills/* ~/.claude/skills/
```

Edit `~/.claude/skills/pr-process/SKILL.md` and `~/.claude/skills/copilot-loop/SKILL.md` to replace `OWNER/REPO` with your GitHub org and repo names.

## Step 6: Create your project repo

Set up a new repo on GitHub for the sample app:

```bash
mkdir taskflow && cd taskflow
cp -r /path/to/auto-agents/sample-app/* .
git init && git add -A && git commit -m "feat: initial project structure"
gh repo create taskflow --private --push --source=.
```

## Step 7: Add the Copilot review workflow

```bash
mkdir -p .github/workflows
cp /path/to/auto-agents/setup/require-copilot-review.yml .github/workflows/
git add .github/workflows && git commit -m "ci: add Copilot review gate"
git push
```

## Step 8: Set up branch protection

Go to your repo settings on GitHub, or use the CLI:

```bash
gh api repos/OWNER/taskflow/branches/main/protection -X PUT \
  -f "required_status_checks[strict]=true" \
  -f "required_status_checks[contexts][]=Copilot Review Gate" \
  -f "enforce_admins=false" \
  -f "required_pull_request_reviews=null" \
  -f "restrictions=null"
```

## Step 9: Create agent worktrees

```bash
cd /path/to/taskflow
bash /path/to/auto-agents/setup/setup-worktrees.sh
```

This creates `taskflow-web/`, `taskflow-api/`, `taskflow-data/`, and `taskflow-github/` as sibling directories.

## Step 10: Add CLAUDE.md and shared memory files

```bash
cp /path/to/auto-agents/setup/CLAUDE.md.template CLAUDE.md

# Create shared memory files
echo "# Decisions\n\nArchitectural decisions, API contracts, and conventions shared across all agents." > DECISIONS.md
touch CHECKPOINT.md
```

Edit the CLAUDE.md template to fill in your project name, default branch, and agent sectors. Commit and push, then pull in each worktree so every agent has the same files.

## Step 11: Launch the agents

Open four terminal tabs:

```bash
# Tab 1
cd /path/to/taskflow-web && claude

# Tab 2
cd /path/to/taskflow-api && claude

# Tab 3
cd /path/to/taskflow-data && claude

# Tab 4
cd /path/to/taskflow-github && claude
```

## Step 12: Watch the chat

Open a fifth terminal tab:

```bash
python3 ~/.claude/scripts/comms.py watch
```

You'll see session start messages as each agent comes online. You can also join interactively:

```bash
python3 ~/.claude/scripts/comms.py chat
```

## Step 13: Give them work

In each agent's terminal, give them their first task. For the sample TaskFlow app:

- **Web**: "Build a React component that displays a list of tasks from the API"
- **API**: "Create Express routes for CRUD operations on tasks"
- **Data**: "Set up the SQLite schema and query functions for a tasks table"
- **GitHub**: "Monitor the group chat, process PRs, check error logs, and assign tasks"

Alternatively, agents can run `/begin-work` to orient themselves automatically — they'll read their CLAUDE.md, check shared decisions and any crash-recovery checkpoint, poll the group chat, and begin immediately if assigned work or announce they're ready if not.

Watch the group chat as they coordinate. You'll see agents asking each other for interfaces, announcing completed work, and the GitHub agent processing PRs and assigning tasks from error logs.
