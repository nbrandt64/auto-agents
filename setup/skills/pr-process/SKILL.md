---
name: pr-process
description: Process open PRs — check Copilot reviews, fix comments, merge clean ones
user-invocable: true
disable-model-invocation: true
model: sonnet
---

# PR Processing

Process PRs for: $ARGUMENTS

If no repo specified, check all managed repos.

## Process

### 1. Check Open PRs
```bash
# Customize with your repos
for repo in OWNER/REPO1 OWNER/REPO2; do
  echo "=== $repo ==="
  gh pr list --repo $repo --state open
done
```

### 2. For Each Open PR

**Check Copilot review status:**
```bash
gh api repos/OWNER/REPO/pulls/PR_NUMBER/reviews \
  --jq '[.[] | {user: .user.login, state: .state}]'
```

**Count Copilot comments:**
```bash
gh api repos/OWNER/REPO/pulls/PR_NUMBER/comments \
  --jq '[.[] | select(.user.login == "copilot-pull-request-reviewer[bot]")] | length'
```

### 3. Decision Tree

- **No review yet**: Wait for Copilot review, re-check
- **Reviewed, 0 comments**: Check gate status, merge if passing
- **Reviewed, N comments**: Read comments, assess:
  - Valid bugs → fix on the branch, push, wait for re-review
  - Factually wrong comments → note and proceed to merge
  - Suggestions → note for future, proceed to merge

### 4. After Merge
- Switch repo back to default branch
- Pull latest
- Post update to group chat

## Rules

- NEVER push directly to protected branches
- NEVER leave repos on non-default branches
- Always report what was merged/closed/pending when done
