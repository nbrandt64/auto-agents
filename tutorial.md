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

## Step 2: Install the CLI

Install the auto-agents CLI into your Claude Code config directory:

```bash
python3 setup/auto-agents.py install
```

Or manually:

```bash
mkdir -p ~/.claude/scripts ~/.claude/comms
cp setup/auto-agents.py ~/.claude/scripts/auto-agents.py
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
      { "hooks": [{ "type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook session-start" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook session-end" }] }
    ],
    "PreToolUse": [
      { "hooks": [{ "type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook check" }] }
    ],
    "PostToolUse": [
      { "matcher": "Bash", "hooks": [{ "type": "command", "command": "python3 ~/.claude/scripts/auto-agents.py hook git-detect" }] }
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

On macOS, use `auto-agents start` to open all agents and the group chat in one command:

```bash
auto-agents start
```

It asks two questions before opening any tabs:

```
  Skip permissions prompts? (--dangerously-skip-permissions) [y/N]
  Run /begin-work automatically on startup? [y/N]
```

Or pass flags to skip the prompts:

```bash
auto-agents start --skip-permissions --begin-work
```

Then it opens Terminal tabs for each agent plus a watch tab and an interactive chat tab. If you opted into `--begin-work`, each agent immediately runs the orientation sequence — reading their CLAUDE.md, checking shared decisions and any crash-recovery checkpoint, and polling the group chat — before beginning work.

Or launch manually:

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
auto-agents watch
```

You'll see session start messages as each agent comes online. You can also join interactively:

```bash
auto-agents chat
```

## Step 13: Give them work

If you chose to run `/begin-work` at startup, agents will have already oriented themselves by now. Otherwise, you can tell each agent to run `/begin-work` manually, or just give them their first task directly.

To assign initial work, post tasks via the group chat or tell each agent directly in its terminal. For the sample TaskFlow app:

- **Web**: "Build a React component that displays a list of tasks from the API"
- **API**: "Create Express routes for CRUD operations on tasks"
- **Data**: "Set up the SQLite schema and query functions for a tasks table"
- **GitHub**: "Monitor the group chat, process PRs, check error logs, and assign tasks"

Watch the group chat as they coordinate. You'll see agents asking each other for interfaces, announcing completed work, and the GitHub agent processing PRs and assigning tasks from error logs.
