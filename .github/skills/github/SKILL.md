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

### Push Operations (Zscaler Bypass)

#### `gh-api`
**Push via GitHub REST API — bypasses Zscaler on every push.**

Use this for ALL git pushes. Zscaler blocks `git push` (HTTPS binary pack
format) and SSH. This command uses JSON-only GitHub API calls that Zscaler
permits.

**Handles all scenarios automatically:**
- Regular incremental push (most common)
- Missing/gone local tracking ref — queries GitHub API for remote SHA, no `git fetch` needed
- Diverged remote (e.g. auto-init commit not in local history) — switches to full-file upload mode
- Brand-new empty repo — creates the branch ref from scratch
- Transient connection resets — retries up to 3× automatically

```bash
/github gh-api              # Standard push
/github gh-api --force      # Force push (diverged history, rebase, squash)
```

**Scenario 1 — Regular push (most common):**
```bash
git add . && git commit -m "feat: Add feature"
/github gh-api
# ── GitHub Git Data API push ──
# Repo:   owner/repo   Branch: main   Pushing 2 commit(s)
# ✅ main → a1b2c3d
```

**Scenario 2 — Brand-new repo:**
```bash
gh repo create owner/new-repo --private          # no --auto-init needed
git remote add origin https://github.com/owner/new-repo.git
git add . && git commit -m "feat: Initial commit"
/github gh-api    # auto-bootstraps the empty repo, then pushes all files
```

Note: GitHub's Git Data API returns 409 on repos with no commits yet. The
script detects this and automatically creates a bootstrap commit (via the
Contents API) before pushing your actual content. Only two commits will
appear in history: the bootstrap placeholder and your real commit.

**Scenario 3 — Tracking ref "gone" (repo recreated, no fetch yet):**
```bash
# git branch -vv shows: * main abc1234 [origin/main: gone]
/github gh-api    # auto-detects remote SHA via API — no manual fix needed
```

**After push, sync local tracking ref:**
```bash
git fetch && git reset --hard origin/main
```

**Push after committing (replaces git push):**
```bash
git add . && git commit -m "fix: Update logic"
/github gh-api
```

**New repo — first push:**
```bash
gh repo create owner/repo --private    # no --auto-init needed
git remote add origin https://github.com/owner/repo.git
git add . && git commit -m "feat: Initial commit"
/github gh-api    # bootstraps empty repo automatically, then pushes
```

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
