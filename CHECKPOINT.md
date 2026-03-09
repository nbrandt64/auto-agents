# CHECKPOINT

Crash recovery checkpoint. Write current task state here before complex work.

## Format

```
## Agent: <name>
## Task: <what you're working on>
## Status: in-progress | blocked | complete

### Completed
- Step 1 description
- Step 2 description

### Next
- Step 3 description
- Step 4 description

### Notes
Any context needed to resume (blockers, decisions made, etc.)
```

Clear this file when the task is complete.
