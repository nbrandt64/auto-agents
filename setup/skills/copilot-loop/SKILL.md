---
name: copilot-loop
description: Run the Copilot review loop for a specific PR until merge-ready
user-invocable: true
disable-model-invocation: true
model: sonnet
---

# Copilot Review Loop

Run the review loop for: $ARGUMENTS

Expected format: `REPO PR_NUMBER` (e.g., `myproject 42`)

## Loop

1. **Check review status:**
   ```bash
   gh api repos/OWNER/REPO/pulls/PR_NUMBER/reviews \
     --jq '[.[] | {user: .user.login, state: .state}]'
   ```

2. **If no review yet**: Wait 120 seconds, re-check (max 3 cycles)

3. **Count comments:**
   ```bash
   gh api repos/OWNER/REPO/pulls/PR_NUMBER/comments \
     --jq '[.[] | select(.user.login == "copilot-pull-request-reviewer[bot]")] | length'
   ```

4. **If comments > 0**: Read them, fix the code, commit, push, go to step 1

5. **If comments == 0**: Check gate, merge:
   ```bash
   gh pr checks PR_NUMBER --repo OWNER/REPO
   gh pr merge PR_NUMBER --repo OWNER/REPO --merge
   ```

6. **After merge**: Switch repo to default branch, pull latest

## Rules

- Maximum 3 wait cycles before reporting "Copilot not responding"
- Maximum 5 fix-and-push cycles before reporting "needs human review"
- Do NOT leave repos on non-default branches
- Report final status: merged / blocked / needs attention
