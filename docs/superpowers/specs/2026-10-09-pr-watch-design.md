# Design: `github pr-watch`

**Date:** 2026-10-09
**Status:** Approved (design), pending written-spec review
**Repo:** git-workflow-cli (`.github/skills/github/`)
**Type:** Architectural — new subcommand on the `github` skill

## 1. Intent

A software engineer opens a PR and then babysits it: polling CI, waiting for
reviews, re-checking after pushing fixes. Across ~32 Mox repos this is constant
context-switching.

`pr-watch` removes the babysitting. It is a **foreground, blocking watcher**:
run it in a terminal tab, it live-updates a compact status block, and it exits
on its own when the PR reaches a terminal state. The terminal output *is* the
notification — no Slack, no background process.

**Success criteria:** run `github pr-watch`, leave it, and be told — via exit
code and a final status line — when the PR is merged, closed, or its CI fails.

## 2. Decisions (locked)

| Decision | Choice |
|---|---|
| Run mode | Foreground blocking watcher (not background, not one-shot) |
| CI signal | GitHub PR checks via `gh` (platform-agnostic: CircleCI + GHA + any check) |
| Events tracked | CI checks + review state + merged/closed |
| ci-debug integration | Opt-in `--diagnose` flag, off by default |
| Slack notify | None (foreground; status block is the notification) |
| Default interval | 15 seconds |

## 3. Interface

```
github pr-watch [<pr-number>] [options]
```

| Flag | Default | Meaning |
|---|---|---|
| `<pr-number>` | auto-detect | PR to watch. Omitted → detect from current branch via `gh pr view --json number` |
| `--interval N` | `15` | Poll interval in seconds |
| `--diagnose` | off | On CI failure, run `ci-debug analyze` for the branch and append a one-line root cause |
| `--exit-on-approved` | off | Exit 0 as soon as `reviewDecision == APPROVED` (before merge) |
| `--once` | off | Single poll, print status, exit (scriptability / manual verification) |
| `--json` | off | Emit the status block as JSON instead of the human block |

## 4. Architecture

Single Python script `scripts/pr_watch.py`, wired into `run.sh`:

```
pr-watch)
  exec python3 "$SCRIPTS_DIR/pr_watch.py" "$@"
  ;;
```

Follows the repo's existing pattern (`commit_check.py`, `gh-api-push.py`).
**No new dependencies** — shells out to `gh` (already a hard requirement of the
skill) and parses JSON. No TUI library; redraw is done by clearing and
re-printing the block each cycle.

### Components

- **`resolve_pr(arg)`** → int. Uses the arg if given, else
  `gh pr view --json number` on the current branch. Exit 3 if no PR.
- **`fetch_state(pr)`** → dict. One call:
  `gh pr view <pr> --json state,mergedAt,reviewDecision,latestReviews,statusCheckRollup,headRefName,title,url,number`
- **`classify_checks(statusCheckRollup)`** → counts of pass/pending/fail and the
  list of failing check names.
- **`render(state)`** → the human block or JSON (per `--json`).
- **`terminal_state(state)`** → the exit decision (§5).
- **`main loop`** — fetch → render → check terminal → sleep `--interval` → repeat.

### Data flow (per poll cycle)

1. Resolve PR number.
2. `fetch_state` — a single `gh` call returns everything needed.
3. Render the status block (in-place redraw).
4. Evaluate terminal-state logic; exit if matched.
5. Sleep `--interval`; repeat.

## 5. Terminal-state exit logic

Checked each cycle, **in this order** (first match wins):

| Condition | Output | Exit code |
|---|---|---|
| `mergedAt` set | `✅ Merged` | `0` |
| `state == CLOSED` and not merged | `⊘ Closed without merge` | `1` |
| All checks settled AND ≥1 failed | `❌ CI failing: <names>` | `2` |
| `--exit-on-approved` AND `reviewDecision == APPROVED` | `✅ Approved` | `0` |
| otherwise | keep watching | — |

"All checks settled" = no check in a pending/queued/in-progress bucket. A PR
with zero checks never triggers the CI-fail branch (nothing to fail).

### Exit-code contract

- `0` — merged (or approved with `--exit-on-approved`)
- `1` — closed without merge
- `2` — CI failing
- `3` — no PR found for the branch
- `130` — interrupted (Ctrl-C), clean exit, no stack trace

The contract lets callers script on the outcome, e.g.
`github pr-watch && github gh-api` or branch on CI failure.

## 6. Status block (human render)

```
PR #123  feat: add pipeline announce
─────────────────────────────────
CI      ● 3 pass · 1 pending · 0 fail
Review  ◐ changes requested by @alice
State   open (mergeable)
─────────────────────────────────
watching… (every 15s, ctrl-C to exit)
```

CI icon: `●` all-pass, `◐` pending, `✖` any-fail. Review line: approved /
changes-requested / review-required, with reviewer login(s) from
`latestReviews`.

## 7. Error handling

| Case | Behavior |
|---|---|
| `gh` not authenticated | Fail fast with pointer to `gh auth login` / `credentials-cli` |
| No PR on current branch | Clear message, exit 3 |
| Transient `gh` network error (Zscaler reset) | Retry up to 3× with backoff (mirrors `gh-api-push.py`) |
| Ctrl-C | Clean exit 130, restore cursor, no traceback |
| `--diagnose` but `ci-debug` unavailable | Warn, print failure without diagnosis, still exit 2 |

## 8. `--diagnose` behavior

When set and the CI-fail terminal state is hit, before exiting run
`ci-debug analyze <Org/repo> --branch <headRefName>` (or the PR form) and append
its one-line root-cause summary to the failure output. Keeps the base watcher
fast and decoupled; deep diagnosis only on explicit request.

## 9. Testing

The repo's scripts are untested shell/python with no test harness — this change
stays consistent (no new test framework introduced). Verifiability comes from:

- `--once` + `--json` for deterministic, scriptable single-poll output.
- **Live verification** against a real open PR: confirm the block renders,
  CI counts match `gh pr checks`, review state matches, and the merged exit
  fires correctly on a PR that gets merged during the watch.

## 10. Out of scope

- Background mode / Slack notification (rejected — foreground only).
- Auto-diagnosis on every failure (opt-in `--diagnose` instead).
- Watching for new commits pushed by others (not selected).
- Spinnaker deploy status (that's `deploy-cli`, a separate concern).
