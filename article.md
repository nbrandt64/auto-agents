# Sub-agents was 2025. Welcome to autonomous agents with group chat.

Claude Code has a Task tool. You can spin up a sub-agent, give it a job, and wait for it to finish. Then spin up another one. It works, but it's synchronous -- one agent at a time, all running inside the same process, the same working directory.

I wanted something different. I wanted to open four terminal tabs, run `claude` in each one, and have them all build a product simultaneously. A Web agent writing React components while an API agent builds Express routes while a Data agent sets up the database schema. All at the same time, all aware of each other, all coordinating without me in the middle.

The problem is that running multiple Claude Code instances against the same repo is chaos. Two agents checkout different branches and stomp each other. One agent edits a file while another is reading it. Nobody knows what anyone else is doing. Git conflicts pile up. You end up spending more time untangling the mess than you saved by parallelizing.

Sub-agents solve coordination by being sequential. But sequential means slow. If your Web agent is waiting on the API agent, and the API agent is waiting on the Data agent, you've just built a pipeline with extra steps.

What I wanted was true parallelism with real coordination. Agents that work independently but talk to each other. Agents that own their own code and stay out of each other's way. Agents that can ask each other for help and get a response. And an automated reviewer so I don't have to read every PR myself.

This article describes the system I built and used in production. Everything referenced here is in this repo, ready to use.

## The Architecture

Four agents, each in its own git worktree, communicating through a shared group chat backed by a web API. A human (you) can join the chat at any time. PRs flow through GitHub Copilot as an automated code reviewer before merging.

```
                            +------------------+
                            |    Group Chat    |
                            |   (Web API)      |
                            +--------+---------+
                                     |
              +----------+-----------+-----------+----------+
              |          |                       |          |
         +----+----+ +---+----+             +----+----+ +---+-----+
         |   Web   | |  API   |             |  Data   | | GitHub  |
         | Agent   | | Agent  |             | Agent   | | (Coord) |
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

**A shared API, not local files.** The group chat is backed by a web API (DynamoDB + Next.js routes) that works across multiple machines. Agents write messages with `comms.py post`, and a `PreToolUse` hook checks for new messages before every tool call. The API uses Bearer token auth and time-sorted keys for consistent ordering.

**Hooks, not code.** Agents don't need special code to participate in the chat. Claude Code hooks handle everything -- auto-registering on session start, checking for messages, detecting git operations, announcing session end. The agent just sees messages appear in context.

**Copilot, not human review.** A GitHub Actions workflow gates merges on Copilot review. The GitHub agent polls for review status, reads comments, fixes issues, pushes again, and repeats until the review is clean. Then it merges. The human never needs to open a PR page.

## The Pillars

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
your-project-github/    # GitHub agent's worktree → agent/github branch
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

The group chat is where coordination happens. It's a Python CLI (`setup/comms.py`) that talks to a shared web API and supports several modes:

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

The auto-naming system maps directories to agent names. If your session is running in `taskflow-web/`, you're automatically named "Web." The directory-to-name mapping is built into `comms.py` and the server-side API.

Messages are scoped by **project**. Each agent is automatically associated with a project based on its working directory, and `check` only surfaces messages from the same project (plus `general` broadcasts from the human). This keeps things clean when you're running agents across multiple repos -- a GitHub agent coordinating three projects doesn't flood the frontend agent with irrelevant chatter. Cross-project agents (like the GitHub agent) automatically see messages from all projects.

The `check` command is the magic. It's called before every tool use via a `PreToolUse` hook. It looks for messages since the last check and returns any that are relevant. Messages directed at your agent (e.g., "Web: please update the TaskList") are tagged `>>> FOR YOU` so the agent knows to act on them.

This means agents don't poll or wait. They just work, and between tool calls, they naturally see any new messages. If another agent needs something from them, the message appears in context and they can respond.

The human joins by running `python3 comms.py chat` in any terminal. You see the same messages the agents see, and you can post messages that agents will pick up on their next tool call. You can direct messages to specific agents ("API: add rate limiting to the tasks endpoint") or broadcast to everyone ("All: switching to PostgreSQL, update your connection strings").

### 4. Hooks as Nervous System

Claude Code hooks are the glue. They turn the comms system from something agents have to remember to use into something that just works. The configuration lives in `setup/settings.json.example`:

```json
{
  "env": {
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "80"
  },
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

The `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` setting triggers context compaction at 80% capacity instead of the default 95%. This matters for multi-agent work: each agent's PreToolUse hook injects comms messages into context on every tool call, which fills the window faster than a normal session. At 95%, agents are already losing earlier instructions and making mistakes by the time compaction kicks in. At 80%, they compact while there's still enough headroom for the summarization to preserve task lists, sector ownership rules, and recent decisions. This is especially important for Ralph loops, where an agent needs to hold a large task list in context across a long session.

Four hooks, four behaviors:

**SessionStart** -- When an agent starts, the hook reads the working directory, auto-assigns a name based on the directory suffix, and posts "Session started in taskflow-web" to the chat. Every other agent sees this on their next tool call.

**PreToolUse** -- Before every single tool call, the hook runs `comms.py check`. If there are new messages, they're injected into the agent's context. The agent sees them naturally, as if someone spoke to them. Directed messages get the `>>> FOR YOU` tag.

**PostToolUse (Bash only)** -- After any Bash command, the hook checks if it was a git operation (checkout, push, pull, merge, etc.). If so, it posts to the chat: "git: push origin feat/add-tasks". Other agents know when branches are changing. It also detects `gh pr merge` commands and automatically pulls the default branch in the main repo directory, so Xcode (or whatever builds from the main repo) always has the latest merged code. No more "rebuild didn't pick up changes" surprises.

**Stop** -- When a session ends, the hook posts "Session ended." Other agents know that agent is no longer active.

The wrapper script (`setup/comms.sh`) handles the plumbing -- reading the JSON that Claude Code passes to hooks via stdin, extracting the session ID and working directory, and calling the right `comms.py` subcommand. Agents don't need any awareness of this machinery. They just work, and the hooks handle communication transparently.

### 5. Skills as Reusable Workflows

Hooks handle the automatic behaviors. But agents also need repeatable workflows -- things like "process all open PRs" or "run the TDD cycle." That's what skills are for.

A skill is a SKILL.md file in `~/.claude/skills/` that defines a slash command. When you type `/tdd add user authentication` in a Claude Code session, the skill loads its instructions and the agent follows them. Skills are Claude Code's native mechanism for packaging workflows -- no external tooling needed.

The repo includes four example skills in `setup/skills/`:

**`/tdd`** -- The test-driven development cycle. Write a failing test, implement the minimum to pass, refactor. One test at a time, each cycle a separate commit. This is how specialist agents build features.

```markdown
---
name: tdd
description: Test-driven development cycle — write failing test, implement, refactor
user-invocable: true
model: sonnet
---
# Test-Driven Development
Implement using TDD: $ARGUMENTS
## Cycle
### 1. RED — Write Failing Test
### 2. GREEN — Minimal Implementation
### 3. REFACTOR — Clean Up
```

**`/review`** -- Code review with a structured checklist covering correctness, security, and code quality. The agent reads the diff, checks for common issues, and outputs findings with file:line references and severity levels.

**`/pr-process`** -- The GitHub agent's main workflow. Check open PRs across all repos, read Copilot review comments, decide whether to fix or merge, and report status. This is what the GitHub agent runs in a Ralph loop to process PR queues.

**`/copilot-loop`** -- The inner loop for a single PR. Check review status, read comments, fix the code, push, wait for re-review, repeat until clean, then merge. Called by `/pr-process` for each PR that needs attention.

Skills differ from CLAUDE.md instructions in an important way: they're loaded on demand, not injected into every session. An agent's CLAUDE.md defines its identity, sector ownership, and standing rules. Skills define specific workflows it can execute. This keeps the base context lean -- agents don't carry the full PR processing workflow in context until they actually need it.

The `user-invocable: true` flag means only the human can trigger these skills (via `/command`). Without it, Claude can also invoke them automatically when they match the task at hand. For workflows with side effects -- merging PRs, deploying code -- you generally want `disable-model-invocation: true` so the human stays in control of when they fire.

To install the example skills:

```bash
cp -r setup/skills/* ~/.claude/skills/
```

Then customize the repo names and owners in `/pr-process` and `/copilot-loop` to match your setup.

### 6. The GitHub Agent

The GitHub agent is different from the specialist agents. It doesn't write application code. Instead, it's the central coordinator across all projects -- processing PRs, monitoring error logs, and assigning tasks to specialist agents based on what it finds.

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

The GitHub agent polls, reads every comment Copilot left, fixes the code, pushes, and waits for the next review cycle. This typically takes 1-3 iterations. When the review comes back clean, it merges.

The human's role shifts from code reviewer to architect. You're not reading diffs and leaving comments -- Copilot does that. You're in the group chat setting direction, answering questions, and making design decisions. If Copilot flags something that needs human judgment, the GitHub agent will ask you in the chat.

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

When an agent pushes a fix for Copilot's feedback, the `synchronize` event fires, Copilot re-reviews, and the workflow updates the status. The GitHub agent polls until it sees `success`, then merges.

One edge case: sometimes the gate gets stuck in `pending` if Copilot is slow or if the workflow doesn't trigger correctly. The GitHub agent can push an empty commit to re-trigger the workflow. This is a pragmatic escape hatch, not something you want to do routinely.

## Real Results

I built a production application using this system. Four agents running in parallel: Web (React frontend), API (Express backend), Data (database layer), and a GitHub agent (coordination and PR management).

The numbers: 5,282 lines of code across 30 merged PRs in roughly 24 hours of wall-clock time. Four agents worked simultaneously, each in their own worktree, coordinating through the group chat.

Estimated time saved on code review alone: 5-10 hours. Every PR went through Copilot review. Most had 1-2 rounds of feedback before merging clean. I never opened a single PR page in my browser.

My role shifted entirely. Instead of writing code and reviewing diffs, I was in the group chat making architectural decisions: "Use SQLite, not Postgres." "The API should validate request bodies with Zod." "Web: make the task list sortable by due date." The agents handled implementation, and Copilot handled review quality.

The group chat was surprisingly effective. Agents naturally asked each other for things: "API: I need a `GET /tasks?status=active` endpoint." "Data: the tasks table needs a `completed_at` column." These requests appeared as directed messages, and the receiving agent picked them up within seconds on its next tool call.

---

**Ready to try it?** See the step-by-step [tutorial](tutorial.md).

---

## Sustained Work with Ralph Loops

Claude Code sessions have a natural attention span. Give an agent a single task and it'll complete it, but complex work requires dozens of tasks in sequence. Without structure, agents lose focus, skip steps, or declare "done" prematurely.

The solution is **Ralph loops** -- large blocks of tasks processed sequentially in a loop. You give the agent a numbered task list, and it works through them one at a time: pick the next task, complete it fully (implement, test, verify), mark it done, move to the next. The agent keeps iterating until the list is empty.

This works because it gives the agent a clear contract: you're not done until every task is checked off. No jumping between tasks. No declaring victory after the first one. The task list acts as both a progress tracker and an anchor that keeps the agent oriented across a long session.

In practice, a Ralph loop looks like this in your prompt:

```
Work through these tasks sequentially. Complete each one fully before moving to the next.

1. Add input validation to the /tasks endpoint
2. Write tests for the validation rules
3. Update the API error response format
4. Add rate limiting middleware
5. Write integration tests for rate limiting
6. Update the API documentation
```

The agent picks up task 1, implements it, verifies it works, then moves to task 2. If it hits a blocker, it posts in the group chat rather than skipping ahead. Combined with TDD (write the failing test first, then implement), this produces reliable, sustained work across sessions that would otherwise drift.

For the GitHub agent, Ralph loops are how it processes PR queues: check PR #1 for Copilot comments, fix them, push, move to PR #2, repeat. For specialist agents, it's how they build features: scaffold, implement, test, refactor, one task at a time.

## Persistent Memory

Agents lose all context when their session ends. Worse, sessions can freeze or crash mid-task, leaving work half-finished with no trail. The memory system addresses both problems with three lightweight layers — no new tooling, just files and conventions.

**Private memory** is built into Claude Code. Each agent automatically maintains long-term notes at `~/.claude/projects/<path>/memory/MEMORY.md`, which persists across sessions and loads into context on startup. Agents save stable patterns, key file paths, and debugging insights here. This is per-agent and per-project — the Web agent's memory is separate from the API agent's.

**Shared memory** is a `DECISIONS.md` file committed to the repo root. Since all worktrees share the same git history, every agent sees it. When an agent makes or discovers a decision that affects others — "we're using Zod for API validation," "the tasks table has a soft-delete column" — it adds a line and commits. Agents check this file at session start to pick up cross-agent context without re-reading the codebase.

**Checkpointing** handles crash recovery. Before starting complex work, an agent writes a `CHECKPOINT.md` in the repo root with the current task, completed steps, and next steps. It updates this file as it completes each major step. If the session freezes mid-task, the next session reads the checkpoint and picks up exactly where it left off — no re-investigation, no repeated work. Combined with frequent small commits, `git log` acts as a secondary recovery trail. When the task is complete, the agent clears the checkpoint.

The overhead is minimal: agents already commit frequently, and the checkpoint is just a few lines updated between steps. The payoff is significant — sessions that would otherwise start cold (re-reading files, re-discovering decisions, re-planning interrupted work) can resume in seconds.

## What's Next

This system works well for a single repo with 3-4 specialist agents. There are several directions to push it further.

**Agent specialization.** Beyond sector-based specialists, you could add a security reviewer agent that audits every PR, a test writer that generates tests for merged code, or a documentation agent that keeps docs in sync with implementation changes.

**Conflict resolution.** Right now, sector ownership prevents most conflicts. But when two agents both need to change `shared/types.ts`, coordination is manual (post in chat, wait for acknowledgment). An automated conflict resolution protocol -- locking, queuing, or merge-and-rebase -- would make shared code less fragile.

**Multi-repo orchestration.** The comms system supports project scoping and cross-project visibility. Agents across separate repos (frontend repo, backend repo, infrastructure repo) can coordinate through the same shared API. Messages are tagged by project, and the GitHub agent can see messages from all projects while specialist agents only see their own. Since the backend is a web API, agents on different machines can participate in the same group chat.

The core insight is simple: agents don't need a framework to coordinate. They need a shared communication channel, isolated workspaces, and clear ownership boundaries. Everything else follows.
