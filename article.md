# Sub-agents was 2025. Welcome to autonomous agents with group chat.

Claude Code has a Task tool. You can spin up a sub-agent, give it a job, and wait for it to finish. Then spin up another one. It works, but it's synchronous -- one agent at a time, all running inside the same process, the same git branch, the same working directory.

I wanted something different. I wanted to open four terminal tabs, run `claude` in each one, and have them all build a product simultaneously. A Web agent writing React components while an API agent builds Express routes while a Data agent sets up the database schema. All at the same time, all aware of each other, all coordinating without me in the middle.

The problem is that running multiple Claude Code instances against the same repo is chaos. Two agents checkout different branches and stomp each other. One agent edits a file while another is reading it. Nobody knows what anyone else is doing. Git conflicts pile up. You end up spending more time untangling the mess than you saved by parallelizing.

Sub-agents solve coordination by being sequential. But sequential means slow. If your Web agent is waiting on the API agent, and the API agent is waiting on the Data agent, you've just built a pipeline with extra steps.

What I wanted was true parallelism with real coordination. Agents that work independently but talk to each other. Agents that own their own code and stay out of each other's way. Agents that can ask each other for help and get a response. And an automated reviewer so I don't have to read every diff myself.

This article describes the system I built and used in production. Everything referenced here is in this repo, ready to use.

## The Architecture

Four agents, each in its own git worktree, communicating through a SQLite group chat. A human (you) can join the chat at any time. PRs flow through GitHub Copilot as an automated code reviewer before merging.

```
                            +------------------+
                            |    Group Chat    |
                            |   (SQLite DB)    |
                            +--------+---------+
                                     |
              +----------+-----------+-----------+----------+
              |          |                       |          |
         +----+----+ +---+----+             +----+----+ +---+-----+
         |   Web   | |  API   |             |  Data   | | Sysadmin|
         | Agent   | | Agent  |             | Agent   | |  (Orch) |
         +----+----+ +---+----+             +----+----+ +---+-----+
              |          |                       |          |
         +----+----+ +---+----+             +----+----+    |
         |taskflow | |taskflow|             |taskflow |    |
         |  -web/  | | -api/  |             | -data/  |    |
         |(worktree)|(worktree)|            |(worktree)|   |
         +---------+ +--------+             +---------+    |
              |          |                       |          |
              +----------+-----------+-----------+          |
                                     |                      |
                              +------+------+               |
                              |   GitHub    |               |
                              |   (PRs)     |<--------------+
                              +------+------+      creates PRs,
                                     |           runs review loop
                              +------+------+
                              |  Copilot    |
                              | Review Gate |
                              +-------------+
```

The key ideas:

**Worktrees, not branches.** Each agent gets its own directory -- a full copy of the repo via `git worktree`. No checkout conflicts because no one shares a working directory. Agent Web works in `taskflow-web/`, Agent API works in `taskflow-api/`. They can both be on different branches at the same time.

**SQLite, not an API.** The group chat is a single SQLite file. No server, no dependencies, no ports. Agents write messages with `comms.py post`, and a `PreToolUse` hook checks for new messages before every tool call. WAL mode handles concurrent writes cleanly.

**Hooks, not code.** Agents don't need special code to participate in the chat. Claude Code hooks handle everything -- auto-registering on session start, checking for messages, detecting git operations, announcing session end. The agent just sees messages appear in context.

**Copilot, not human review.** A GitHub Actions workflow gates merges on Copilot review. The Sysadmin agent polls for review status, reads comments, fixes issues, pushes again, and repeats until the review is clean. Then it merges. The human never needs to open a PR page.

## The Five Pillars

### 1. Worktree Isolation

Git worktrees are the foundation. Without them, nothing else works.

A worktree is a linked copy of your repo that lives in a separate directory but shares the same `.git` history. Each worktree can be on a different branch. Crucially, two worktrees can never be on the same branch -- git enforces this, which prevents conflicts by design.

The setup script (`setup/setup-worktrees.sh`) creates one worktree per agent:

```bash
cd /path/to/your-project
bash setup/setup-worktrees.sh
```

This produces:

```
your-project/           # Main repo — stays on default branch, no direct work
your-project-web/       # Web agent's worktree → agent/web branch
your-project-api/       # API agent's worktree → agent/api branch
your-project-data/      # Data agent's worktree → agent/data branch
your-project-sysadmin/  # Sysadmin's worktree → agent/sysadmin branch
```

Each agent has a "parking branch" (`agent/web`, `agent/api`, etc.). When an agent starts working, it creates a feature branch from that parking branch. When the PR merges, it returns to the parking branch and pulls latest.

This is important: agents never share a working directory. Two agents can both be writing code at the same time without any risk of file conflicts, race conditions, or lock contention. They're literally working in different directories.

The worktrees are persistent -- you create them once and reuse them across sessions. Launch `claude` in `your-project-web/` and that instance becomes the Web agent. Launch it in `your-project-api/` and it becomes the API agent. The directory determines the identity.

### 2. Sector Ownership

Worktrees prevent git conflicts, but they don't prevent logical conflicts. Two agents could still edit the same file if they're both working on, say, `shared/types.ts`. Sector ownership solves this.

The CLAUDE.md template (`setup/CLAUDE.md.template`) defines who owns what:

```markdown
| Sector | Directory | Agent | Responsibility |
|--------|-----------|-------|----------------|
| Frontend | `frontend/` | Web | React components, styling, API client |
| API | `api/` | API | Express routes, middleware, validation |
| Data | `data/` | Data | Database schema, migrations, queries |
| Shared | `shared/` | Any | Types only — coordinate before changing |
```

The rules are simple: only modify files in your sector. If you need a change in someone else's sector, ask in the group chat. If you need to change shared types, announce it first.

This works because Claude Code reads CLAUDE.md at session start and follows it. The agent internalizes "I am the API agent, I only touch `api/`" and respects that boundary. In practice, I've found agents are remarkably disciplined about this -- they'll post a message like "Web: can you add a loading state to the TaskList component?" rather than modifying the frontend code themselves.

Sector ownership also makes PRs cleaner. Each PR only touches one sector's files, which makes Copilot review more focused and makes rollbacks simpler if something breaks.

### 3. Group Chat

The group chat is where coordination happens. It's a SQLite database with a Python CLI (`setup/comms.py`) that supports several modes:

**Posting a message:**
```bash
python3 comms.py post -s "Web" "Finished TaskList component, PR #4 ready"
```

**Watching the chat in real time:**
```bash
python3 comms.py watch
```

**Interactive chat mode (for humans):**
```bash
python3 comms.py chat
```

**Checking for new messages (called by hooks):**
```bash
python3 comms.py check <session_id>
```

The auto-naming system maps directories to agent names. If your session is running in `taskflow-web/`, you're automatically named "Web." This is configurable:

```bash
export COMMS_AGENT_NAMES="Sysadmin,Web,API,Data"
export COMMS_DIR_MAP='{"ops": "Sysadmin"}'
```

The `check` command is the magic. It's called before every tool use via a `PreToolUse` hook. It looks for messages since the last check and returns any that are relevant. Messages directed at your agent (e.g., "Web: please update the TaskList") are tagged `>>> FOR YOU` so the agent knows to act on them.

This means agents don't poll or wait. They just work, and between tool calls, they naturally see any new messages. If another agent needs something from them, the message appears in context and they can respond.

The human joins by running `python3 comms.py chat` in any terminal. You see the same messages the agents see, and you can post messages that agents will pick up on their next tool call. You can direct messages to specific agents ("API: add rate limiting to the tasks endpoint") or broadcast to everyone ("All: switching to PostgreSQL, update your connection strings").

### 4. Hooks as Nervous System

Claude Code hooks are the glue. They turn the comms system from something agents have to remember to use into something that just works. The configuration lives in `setup/settings.json.example`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "bash ~/.claude/scripts/comms.sh session-start"
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "bash ~/.claude/scripts/comms.sh session-end"
      }
    ],
    "PreToolUse": [
      {
        "type": "command",
        "command": "bash ~/.claude/scripts/comms.sh check"
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "type": "command",
        "command": "bash ~/.claude/scripts/comms.sh git-detect"
      }
    ]
  }
}
```

Four hooks, four behaviors:

**SessionStart** -- When an agent starts, the hook reads the working directory, auto-assigns a name based on the directory suffix, and posts "Session started in taskflow-web" to the chat. Every other agent sees this on their next tool call.

**PreToolUse** -- Before every single tool call, the hook runs `comms.py check`. If there are new messages, they're injected into the agent's context. The agent sees them naturally, as if someone spoke to them. Directed messages get the `>>> FOR YOU` tag.

**PostToolUse (Bash only)** -- After any Bash command, the hook checks if it was a git operation (checkout, push, pull, merge, etc.). If so, it posts to the chat: "git: push origin feat/add-tasks". Other agents know when branches are changing. It also detects `gh pr merge` commands and automatically pulls the default branch in the main repo directory, so Xcode (or whatever builds from the main repo) always has the latest merged code. No more "rebuild didn't pick up changes" surprises.

**Stop** -- When a session ends, the hook posts "Session ended." Other agents know that agent is no longer active.

The wrapper script (`setup/comms.sh`) handles the plumbing -- reading the JSON that Claude Code passes to hooks via stdin, extracting the session ID and working directory, and calling the right `comms.py` subcommand. Agents don't need any awareness of this machinery. They just work, and the hooks handle communication transparently.

### 5. The Orchestrator

The Sysadmin agent is different from the specialist agents. It doesn't write application code. Instead, it manages the PR lifecycle: creating PRs, running the Copilot review loop, fixing feedback, and merging clean PRs.

The Copilot review loop looks like this:

```bash
# 1. Create the PR
gh pr create --base main --title "feat: add task CRUD" --body "..."

# 2. Wait for Copilot to review (takes 2-5 minutes)
sleep 60

# 3. Check review status
gh api repos/OWNER/REPO/pulls/PR_NUMBER/reviews \
  --jq '[.[] | {user: .user.login, state: .state}]'

# 4. Read Copilot's comments
gh api repos/OWNER/REPO/pulls/PR_NUMBER/comments \
  --jq '.[] | "[\(.path):\(.line)] \(.body)"'

# 5. Fix the issues, commit, push

# 6. Repeat from step 2 until 0 comments

# 7. Merge
gh pr merge PR_NUMBER --merge
```

The Sysadmin polls, reads every comment Copilot left, fixes the code, pushes, and waits for the next review cycle. This typically takes 1-3 iterations. When the review comes back clean, it merges.

The human's role shifts from code reviewer to architect. You're not reading diffs and leaving comments -- Copilot does that. You're in the group chat setting direction, answering questions, and making design decisions. If Copilot flags something that needs human judgment, the Sysadmin will ask you in the chat.

## The Copilot Gate

The Copilot review loop only works if you can actually prevent merges until Copilot has reviewed. That's what `setup/require-copilot-review.yml` does.

This GitHub Actions workflow triggers on PR events (opened, synchronized, reopened) and on review submissions. It checks whether Copilot has reviewed the PR and sets a commit status accordingly:

- **No review yet** -- sets status to `pending` with description "Waiting for Copilot review (2-5 min)"
- **Reviewed with comments** -- sets status to `failure` with the comment count
- **Reviewed with no comments** -- sets status to `success`

The commit status is named "Copilot Review Gate." You add this as a required status check in your branch protection rules, and now PRs literally cannot merge until Copilot reviews them and leaves no comments.

```yaml
# The workflow sets commit statuses like this:
gh api "repos/$REPO/statuses/$SHA" \
  -f state=success \
  -f context="Copilot Review Gate" \
  -f description="Copilot reviewed — no comments"
```

When an agent pushes a fix for Copilot's feedback, the `synchronize` event fires, Copilot re-reviews, and the workflow updates the status. The Sysadmin agent polls until it sees `success`, then merges.

One edge case: sometimes the gate gets stuck in `pending` if Copilot is slow or if the workflow doesn't trigger correctly. The Sysadmin can manually set the status to `success` via the API if it's confirmed that Copilot has reviewed. This is a pragmatic escape hatch, not something you want to do routinely.

## Real Results

I built a production application (Zenvoy) using this system. Four agents running in parallel: Web (React frontend), API (Express backend), Data (database layer), and Sysadmin (orchestration and PR management).

The numbers: 5,282 lines of code across 30 merged PRs in roughly 24 hours of wall-clock time. Four agents worked simultaneously, each in their own worktree, coordinating through the group chat.

Estimated time saved on code review alone: 5-10 hours. Every PR went through Copilot review. Most had 1-2 rounds of feedback before merging clean. I never opened a single PR page in my browser.

My role shifted entirely. Instead of writing code and reviewing diffs, I was in the group chat making architectural decisions: "Use SQLite, not Postgres." "The API should validate request bodies with Zod." "Web: make the task list sortable by due date." The agents handled implementation, and Copilot handled review quality.

The group chat was surprisingly effective. Agents naturally asked each other for things: "API: I need a `GET /tasks?status=active` endpoint." "Data: the tasks table needs a `completed_at` column." These requests appeared as directed messages, and the receiving agent picked them up within seconds on its next tool call.

---

**Ready to try it?** See the step-by-step [tutorial](tutorial.md).

---

## What's Next

This system works well for a single repo with 3-4 specialist agents. There are several directions to push it further.

**Agent specialization.** Beyond sector-based specialists, you could add a security reviewer agent that audits every PR, a test writer that generates tests for merged code, or a documentation agent that keeps docs in sync with implementation changes.

**Conflict resolution.** Right now, sector ownership prevents most conflicts. But when two agents both need to change `shared/types.ts`, coordination is manual (post in chat, wait for acknowledgment). An automated conflict resolution protocol -- locking, queuing, or merge-and-rebase -- would make shared code less fragile.

**Multi-repo orchestration.** The comms system already supports multiple agent names and custom directory mappings. Extending this to coordinate agents across separate repos (frontend repo, backend repo, infrastructure repo) is a natural next step.

**Persistent memory.** Agents lose all context when their session ends. A persistent memory layer -- key decisions, architectural choices, known issues -- would reduce the ramp-up cost of starting new sessions and let agents build on prior work without re-reading the entire codebase.

The core insight is simple: agents don't need a framework to coordinate. They need a shared communication channel, isolated workspaces, and clear ownership boundaries. Everything else follows.
