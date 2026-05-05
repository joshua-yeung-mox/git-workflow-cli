---
name: github
description: Consolidated GitHub workflow helpers for pull request management and commit message formatting.
allowed-tools: []
---

# GitHub Skill

Consolidated GitHub workflow helpers for pull request management and commit message formatting.

## Subcommands

### PR Operations

#### `pr-setup`
Setup a pull request with assignee, labels, and reviewers.

```bash
/github pr-setup
```

#### `pr-create`
Create a new pull request.

```bash
/github pr-create
```

#### `pr-ready`
Mark a pull request as ready for review.

```bash
/github pr-ready
```

#### `pr-merge-master`
Merge master/main into the current branch.

```bash
/github pr-merge-master
```

#### `pr-complete`
Complete the full PR workflow (setup, create, ready, merge).

```bash
/github pr-complete
```

#### `pr-add-reviewers`
Add team reviewers to an existing pull request.

```bash
/github pr-add-reviewers
```

#### `pr-remove-files`
Remove files from remote while keeping them locally.

```bash
/github pr-remove-files
```

### Commit Message Management (Integrated from commit-cli)

#### `commit-check`
Scan commits and report messages with lines > 70 characters.

```bash
/github commit-check                    # Scan commits not in base branch
/github commit-check --refs HEAD~10     # Scan specific range
```

Options:
- `--refs <revspec>` — Git revision spec to scan (default: base..HEAD where base is origin/main, origin/master, etc.)

Example output:
```
Scanning commits in: origin/main..HEAD
abc1234 "Add new feature to system"
  subject line 1: len=85
    This is a really long subject line that exceeds seventy characters
  body line 5: len=92
    This is some body text that is also too long and needs to be wrapped properly
```

#### `commit-format`
Format a commit message from stdin to 70-character width.

```bash
echo "This is a very long commit message that needs to be wrapped" | /github commit-format
```

Behavior:
- Wraps subject and body lines to 70 characters
- Preserves paragraph structure (blank lines between paragraphs)
- Preserves trailing trailers (Co-authored-by, etc.)

#### `fix-commit`
Check or fix commit message formatting to 70-character width.

**Check mode (default):**
```bash
/github fix-commit --check
/github fix-commit --check --refs HEAD~5..HEAD
```

**Fix mode (rewrites history):**
```bash
/github fix-commit --fix --refs HEAD
```

Options:
- `--check` — Scan commits and report violations (default)
- `--fix` — Rewrite commit messages to wrap at 70 chars (destructive; requires confirmation)
- `--refs <revspec>` — Revision range (default: commits on current branch not in main/master)

Behavior:
- Wraps subject and body lines to 70 characters
- Preserves and cleans trailing `Co-authored-by:` trailers
- Removes angle-bracketed emails from trailers in check mode
- Fails if `Co-authored-by:` trailers contain emails

#### `validate-commit`
Validate commit message format (used by pre-commit hooks).

```bash
git log -n1 --format=%B | /github validate-commit --check
```

### Helpers

#### `gh-api`
Direct GitHub API push helper.

```bash
/github gh-api [args]
```

## Examples

**Setup a new PR with reviewers:**
```bash
/github pr-setup
/github pr-add-reviewers
/github pr-ready
```

**Check if commit messages conform to 70-char width:**
```bash
/github fix-commit --check
```

**Fix multiple commits and force-push:**
```bash
/github fix-commit --fix --refs HEAD~3..HEAD
git push --force-with-lease origin my-branch
```

**Complete PR workflow:**
```bash
/github pr-complete
```

## Related Documentation

- `copilot-workspace/.github/copilot-instructions.md` — Git workflow setup
- `scripts/git-hooks/pre-commit` — Pre-commit hook configuration
