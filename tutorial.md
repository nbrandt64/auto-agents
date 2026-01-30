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

## Step 3: Configure Claude Code hooks

Merge the hooks from `setup/settings.json.example` into your Claude Code settings. If you don't have existing hooks, you can copy it directly:

```bash
# If no existing settings:
cp setup/settings.json.example ~/.claude/settings.json

# If you have existing settings, manually merge the hooks section
```

The hooks config should look like this:

```json
{
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

## Step 4: Create your project repo

Set up a new repo on GitHub for the sample app:

```bash
mkdir taskflow && cd taskflow
cp -r /path/to/auto-agents/sample-app/* .
git init && git add -A && git commit -m "feat: initial project structure"
gh repo create taskflow --private --push --source=.
```

## Step 5: Add the Copilot review workflow

```bash
mkdir -p .github/workflows
cp /path/to/auto-agents/setup/require-copilot-review.yml .github/workflows/
git add .github/workflows && git commit -m "ci: add Copilot review gate"
git push
```

## Step 6: Set up branch protection

Go to your repo settings on GitHub, or use the CLI:

```bash
gh api repos/OWNER/taskflow/branches/main/protection -X PUT \
  -f "required_status_checks[strict]=true" \
  -f "required_status_checks[contexts][]=Copilot Review Gate" \
  -f "enforce_admins=false" \
  -f "required_pull_request_reviews=null" \
  -f "restrictions=null"
```

## Step 7: Create agent worktrees

```bash
cd /path/to/taskflow
bash /path/to/auto-agents/setup/setup-worktrees.sh
```

This creates `taskflow-web/`, `taskflow-api/`, `taskflow-data/`, and `taskflow-sysadmin/` as sibling directories.

## Step 8: Add CLAUDE.md to the repo

```bash
cp /path/to/auto-agents/setup/CLAUDE.md.template CLAUDE.md
```

Edit the template to fill in your project name, default branch, and agent sectors. Commit and push, then pull in each worktree so every agent has the same CLAUDE.md.

## Step 9: Launch the agents

Open four terminal tabs:

```bash
# Tab 1
cd /path/to/taskflow-web && claude

# Tab 2
cd /path/to/taskflow-api && claude

# Tab 3
cd /path/to/taskflow-data && claude

# Tab 4
cd /path/to/taskflow-sysadmin && claude
```

## Step 10: Watch the chat

Open a fifth terminal tab:

```bash
python3 ~/.claude/scripts/comms.py watch
```

You'll see session start messages as each agent comes online. You can also join interactively:

```bash
python3 ~/.claude/scripts/comms.py chat
```

## Step 11: Give them work

In each agent's terminal, give them their first task. For the sample TaskFlow app:

- **Web**: "Build a React component that displays a list of tasks from the API"
- **API**: "Create Express routes for CRUD operations on tasks"
- **Data**: "Set up the SQLite schema and query functions for a tasks table"
- **Sysadmin**: "Monitor the group chat and process PRs as they come in"

Watch the group chat as they coordinate. You'll see agents asking each other for interfaces, announcing completed work, and the Sysadmin creating and merging PRs.
