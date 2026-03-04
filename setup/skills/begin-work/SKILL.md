---
name: begin-work
description: Orient at session start — read memory, check decisions, check chat, begin work
user-invocable: true
model: sonnet
---

# Begin Work

Orient yourself and start your session.

## Steps

### 1. Read Your CLAUDE.md
Read the `CLAUDE.md` in this repo to understand your agent identity, sector ownership, git workflow, and group chat rules.

### 2. Load Private Memory
Check your auto memory for stable patterns and past debugging insights:
```
~/.claude/projects/<encoded-path>/memory/MEMORY.md
```
Claude Code loads this automatically. Review it to recall project-specific conventions.

### 3. Check Shared Decisions
Read `DECISIONS.md` in the repo root for cross-agent architectural decisions and API contracts that affect your work.

### 4. Check for a Checkpoint
Read `CHECKPOINT.md` in the repo root. If it has content, a previous session crashed mid-task — resume from the listed next steps and clear the file when done.

### 5. Check the Group Chat
```bash
auto-agents check
```
Look for messages tagged `>>> FOR YOU` and act on them first. Read others for context.

### 6. Begin Work
- **If assigned** (via chat, checkpoint, or `$ARGUMENTS`): start immediately — no waiting
- **If nothing assigned**: post to the group chat to announce you're online and ready

## Rules
- Do not wait for further input once you know what to do
- Act on `>>> FOR YOU` messages before picking up any new task
- If resuming from a checkpoint, finish that work before starting anything new
