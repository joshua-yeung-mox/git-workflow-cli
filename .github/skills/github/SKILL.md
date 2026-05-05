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

### Commit Message Management

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
