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
- Write a test that describes the desired behavior
- Place test in the project's test directory
- Run the test — confirm it FAILS
- If it passes, the test is wrong or the feature already exists

### 2. GREEN — Minimal Implementation
- Write the minimum code to make the test pass
- Do NOT add extra features, edge cases, or polish
- Run the test — confirm it PASSES
- If it fails, fix the implementation (not the test)

### 3. REFACTOR — Clean Up
- Remove duplication
- Improve naming
- Extract helpers only if genuinely needed
- Run tests again — confirm still PASSING

## Rules

- One test at a time — do not batch
- Test behavior, not implementation details
- Each cycle should be a separate commit
- Use descriptive test names that read like specifications
- Check for existing test patterns in the project before writing

## Commit Pattern

```
test: add failing test for [feature]
feat: implement [feature] to pass test
refactor: clean up [feature] implementation
```
