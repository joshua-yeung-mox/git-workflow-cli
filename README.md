# git-workflow-cli

Unified CLI for Git and GitHub workflows: branch management, PR workflows, commit formatting, and Zscaler-safe push operations.

Consolidates `/git` and `/github` Copilot skills into a single, maintainable repository with shared utilities.

## Features

### Git Skill (`/git`)
- **Branch management** — Create, switch, delete, merge branches
- **Commit workflows** — Interactive commits, rebase, squash
- **Conflict resolution** — Guided merge conflict resolution

### GitHub Skill (`/github`)
- **PR management** — Create, setup, add reviewers, mark ready
- **Commit formatting** — Validate and fix commit message width
- **GitHub API push** — **Bypass Zscaler DLP blocks** on git push

### Special: Zscaler Bypass — **ALWAYS Use `/github gh-api` to Push**

**⚠️ Important:** Standard `git push` is blocked by Zscaler. Use this instead:

```bash
cd <repo>
/github gh-api                 # Push via GitHub REST API (not git protocol)
```

**Why standard git push fails:**
- ❌ `git push` (HTTPS) → HTTP 403 (Zscaler blocks binary pack format)
- ❌ `git push` (SSH) → Connection timeout (Zscaler intercepts)
- **Error message:** `error: RPC failed; HTTP 403 curl 22 The requested URL returned error: 403`

**Why `/github gh-api` works:**
- Uses GitHub's Git Data API instead of git protocol
- Sends JSON/base64 payloads (Zscaler allows JSON, blocks binary)
- Converts commits on GitHub's server instead of sending binary packs
- Bypasses D05 (Source Code) DLP classification
- Works 100% reliably when standard push fails

**How to use:**
```bash
# Make commits as normal
git add .
git commit -m "feat: Add new feature"

# Push via API (do NOT use git push)
/github gh-api

# Optional: force push (for rebased/squashed commits)
/github gh-api --force

# Sync local repo to remote after push
git fetch && git reset --hard origin/main
```

**Technical details:**
1. Creates GitHub blob objects for changed files (via JSON API)
2. Builds tree object (via JSON API)
3. Creates commit object (via JSON API)
4. Updates branch ref (via JSON API)
5. All communication is JSON (Zscaler safe)

## Installation

### Prerequisites
- `git` command-line tool
- `gh` CLI (GitHub CLI) authenticated
- Python 3.12+
- `uv` for package management

### Setup

```bash
# Clone the repository
git clone https://github.com/joshua-yeung-mox/git-workflow-cli.git
cd git-workflow-cli

# Install dependencies (uv)
uv pip install -e .

# Or with dev tools:
uv pip install -e ".[dev]"
```

### Copilot Integration

Symlink the skills from copilot-workspace:

```bash
# In copilot-workspace/.github/skills/
ln -s ~/PycharmProjects/git-workflow-cli/.github/skills/git git
ln -s ~/PycharmProjects/git-workflow-cli/.github/skills/github github
```

Then use:
```bash
/git --branch feature/xyz --create
/github pr-create --title "My PR"
/github gh-api  # Push via GitHub API (Zscaler bypass)
```

## Repository Structure

```
git-workflow-cli/
├─ .github/
│  ├─ skills/
│  │  ├─ git/
│  │  │  ├─ SKILL.md
│  │  │  ├─ run.sh
│  │  │  └─ scripts/
│  │  │     ├─ branch-management.sh
│  │  │     ├─ pr-management.sh
│  │  │     └─ ...
│  │  ├─ github/
│  │  │  ├─ SKILL.md
│  │  │  ├─ run.sh
│  │  │  └─ scripts/
│  │  │     ├─ pr-setup.sh
│  │  │     ├─ fix-commit-messages.sh
│  │  │     ├─ gh-api-push.py
│  │  │     └─ ...
│  └─ copilot-instructions.md
├─ lib/
│  ├─ git_helpers.py       # Shared git utilities
│  ├─ github_helpers.py    # Shared GitHub API utilities
│  └─ common.py            # Shared constants, logging
├─ tests/
│  ├─ test_git_helpers.py
│  ├─ test_github_api.py
│  └─ ...
├─ pyproject.toml          # Python 3.12, uv config
├─ README.md
└─ LICENSE
```

## Development

### Running Tests

```bash
# With uv
uv run pytest tests/

# Or directly (Python 3.12+)
python -m pytest tests/
```

### Code Style

```bash
# Format with Black
uv run black .

# Lint with Ruff
uv run ruff check .
```

### Adding New Scripts

1. Add script to `.github/skills/{git,github}/scripts/`
2. Update run.sh dispatcher to call new script
3. Update SKILL.md with documentation
4. Add tests if needed to `tests/`

## Documentation

- **Global Copilot instructions**: `~/.copilot/copilot-instructions.md`
- **Repo-specific guide**: `.github/copilot-instructions.md` (this repo)
- **Skill documentation**: `.github/skills/{git,github}/SKILL.md`

### GitHub API Push (Zscaler Bypass)

When standard `git push` is blocked:

```bash
cd <repository>
/github gh-api

# Optional: force push
/github gh-api --force
```

The script:
1. Detects repo slug, current branch, remote HEAD
2. Diffs local HEAD vs remote HEAD
3. Creates GitHub blob objects for changed files
4. Builds new tree object
5. Creates commit object via API
6. Updates branch ref
7. Prints command to sync local repo

**Requirements:**
- `gh` CLI authenticated (`gh auth status`)
- Local HEAD must be ahead of remote (≥1 commit)
- GitHub API access (usually allowed through Zscaler)

## Future Enhancements

- [ ] Git hooks automation
- [ ] Advanced rebase workflows (interactive, autosquash)
- [ ] Bisect helpers
- [ ] Stash management
- [ ] Cherry-pick workflows
- [ ] Tag management
- [ ] CI/CD integration (check status before push, etc.)

## Contributing

1. Create a feature branch: `/git --branch feature/xyz --create`
2. Make changes and test: `uv run pytest`
3. Format code: `uv run black .`
4. Create PR: `/github pr-create`

## License

MIT

## Related

- **Copilot Workspace**: https://github.com/joshua-yeung-mox/copilot-workspace
- **Jira CLI**: https://github.com/joshua-yeung-mox/jira-cli
- **Mox AWS**: https://github.com/joshua-yeung-mox/mox-aws
