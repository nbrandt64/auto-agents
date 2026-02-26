---
name: review
description: Perform a thorough code review of recent changes or specified files
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash, LSP
model: opus
---

# Code Review

Review the following: $ARGUMENTS

If no specific target given, review uncommitted changes via `git diff`.

## Review Checklist

### Correctness
- Logic errors or edge cases
- Off-by-one errors
- Null/nil handling
- Error propagation

### Security
- SQL injection, XSS, command injection
- Hardcoded secrets or credentials
- Input validation at system boundaries
- OWASP top 10 concerns

### Code Quality
- Dead code or unused imports
- Duplicated logic (search codebase for similar code)
- Overly complex functions (>50 lines)
- Missing error handling at external boundaries

### Project Rules
- Check project CLAUDE.md for specific requirements
- Verify file organization matches conventions
- Check for documented gotchas about the code area

## Output Format

For each finding:
- **File:Line** — Description of issue
- **Severity**: Critical / Warning / Suggestion
- **Fix**: Concrete recommendation

End with a summary: X critical, Y warnings, Z suggestions.
