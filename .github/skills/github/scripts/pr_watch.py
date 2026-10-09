#!/usr/bin/env python3
"""Watch a GitHub PR's CI/review/merge state, foreground, exit on terminal state.

See docs/superpowers/specs/2026-10-09-pr-watch-design.md.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

# Exact fields requested from `gh pr view --json` each poll cycle (spec §4).
PR_FIELDS = (
    "state,mergedAt,reviewDecision,latestReviews,statusCheckRollup,headRefName,title,url,number"
)


class GhError(Exception):
    """A `gh` invocation failed (after retries, for transient errors)."""


class GhAuthError(GhError):
    """`gh` is not authenticated."""


def _is_auth_error(stderr: str) -> bool:
    """True if gh's stderr indicates an authentication/credential problem."""
    low = stderr.lower()
    return (
        "auth" in low
        or "login" in low
        or "token" in low
        or "bad credentials" in low
        or "401" in low
    )


def _is_auth_error(stderr: str) -> bool:
    """True if gh's stderr indicates an authentication/credential problem."""
    low = stderr.lower()
    return (
        "auth" in low
        or "login" in low
        or "token" in low
        or "bad credentials" in low
        or "401" in low
    )


def _is_not_found(stderr: str) -> bool:
    """True if gh's stderr indicates the requested object does not exist."""
    low = stderr.lower()
    return "no pull requests found" in low or "could not resolve" in low or "not found" in low


def _run_gh(cmd: list, retries: int = 3) -> str:
    """Run a `gh` command, returning stdout. Shared retry/auth handling.

    Raises GhAuthError on an auth failure (no retry); raises GhError after
    `retries` transient failures (with exponential backoff).
    """
    last_err = ""
    for attempt in range(retries):
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            return proc.stdout
        last_err = proc.stderr
        if _is_auth_error(last_err):
            raise GhAuthError(
                "gh is not authenticated. Run `gh auth login` or inject a token "
                f"via credentials-cli. (gh said: {last_err.strip()})"
            )
        if attempt < retries - 1:
            time.sleep(2**attempt)
    raise GhError(f"gh failed after {retries} attempt(s): {last_err.strip()}")


def fetch_state(pr: int, retries: int = 3) -> dict:
    """Fetch a PR's state via `gh pr view --json <PR_FIELDS>`.

    Raises GhAuthError if `gh` is unauthenticated; NoPRError if the PR does not
    exist; GhError after `retries` transient failures (with exponential backoff).
    """
    cmd = ["gh", "pr", "view", str(pr), "--json", PR_FIELDS]
    try:
        return json.loads(_run_gh(cmd, retries))
    except GhError as e:
        if not isinstance(e, GhAuthError) and _is_not_found(str(e)):
            raise NoPRError(f"No PR found with number {pr}.")
        raise


@dataclass
class CheckSummary:
    """Aggregate of a PR's status checks."""

    passed: int = 0
    pending: int = 0
    failed: int = 0
    failed_names: list = field(default_factory=list)
    settled: bool = True


# Conclusions/states that count as a failure.
_FAILED = {"FAILURE", "ERROR", "TIMED_OUT", "ACTION_REQUIRED", "CANCELLED"}
# States/conclusions that count as a pass (everything else settled is neutral).
_PASSED = {"SUCCESS", "NEUTRAL", "SKIPPED"}
# Status-context states that mean the check has not finished yet.
_PENDING_STATE = {"PENDING", "EXPECTED"}


def _check_key(check: dict):
    """Identity of a check for rerun de-duplication.

    Check-runs key on (workflowName, name); status-contexts key on context.
    Distinct workflows can reuse a job name, so workflow is part of the key.
    """
    if "state" in check:  # status-context
        return ("ctx", check.get("context") or check.get("name") or "")
    return ("run", check.get("workflowName") or "", check.get("name") or "")


def _check_recency(check: dict) -> str:
    """Sort key picking a check's latest attempt (newest wins)."""
    return check.get("completedAt") or check.get("startedAt") or ""


def classify_checks(rollup: list) -> CheckSummary:
    """Classify a PR's `statusCheckRollup` into a CheckSummary.

    Two GitHub shapes are normalized:
      - check-runs:      `status` (QUEUED/IN_PROGRESS/COMPLETED) + `conclusion`
      - status-contexts: `state` (PENDING/EXPECTED/SUCCESS/FAILURE/ERROR/...)

    Duplicate runs of the same check (a rerun after a failure) collapse to the
    latest attempt before classification, so a superseded failure is ignored.
    A check is pending if not yet completed (or EXPECTED), failed if its
    conclusion/state is in _FAILED, passed if in _PASSED. An empty rollup
    yields all zeros and settled=True (a PR with no checks has nothing to
    fail — spec Review Focus #1). `settled` is True iff no check is pending
    (spec Review Focus #2).
    """
    # De-dup to latest attempt per check identity (Review: rerun after failure).
    latest: dict = {}
    for check in rollup or []:
        key = _check_key(check)
        if key not in latest or _check_recency(check) >= _check_recency(latest[key]):
            latest[key] = check

    summary = CheckSummary()
    for check in latest.values():
        name = check.get("name") or check.get("context") or ""
        if "state" in check:  # status-context
            state = (check.get("state") or "").upper()
            if state in _PENDING_STATE:
                summary.pending += 1
                continue
            verdict = state
        else:  # check-run
            status = (check.get("status") or "").upper()
            if status != "COMPLETED":
                summary.pending += 1
                continue
            verdict = (check.get("conclusion") or "").upper()
        if verdict in _FAILED:
            summary.failed += 1
            summary.failed_names.append(name)
        else:
            # _PASSED and any other settled/neutral verdict count as passed.
            summary.passed += 1
    summary.settled = summary.pending == 0
    return summary


def terminal_state(state: dict, checks: CheckSummary, exit_on_approved: bool):
    """Decide whether the PR has reached a terminal state.

    Returns None to keep watching, else (exit_code, message). Evaluated in
    spec §5 order; first match wins. A zero-check PR (checks.failed == 0)
    never returns exit 2 — there is nothing to fail.
    """
    if state.get("mergedAt"):
        return (0, "✅ Merged")
    if (state.get("state") or "").upper() == "CLOSED":
        return (1, "⊘ Closed without merge")
    if checks.settled and checks.failed > 0:
        return (2, "❌ CI failing: " + ", ".join(checks.failed_names))
    if exit_on_approved and state.get("reviewDecision") == "APPROVED":
        return (0, "✅ Approved")
    return None


def _review_text(state: dict) -> str:
    """Human-readable review line (spec §6)."""
    decision = state.get("reviewDecision") or ""
    if decision == "APPROVED":
        return "approved"
    if decision == "CHANGES_REQUESTED":
        reviewers = [
            r.get("author", {}).get("login", "")
            for r in (state.get("latestReviews") or [])
            if r.get("state") == "CHANGES_REQUESTED"
        ]
        who = " by " + ", ".join("@" + r for r in reviewers if r) if reviewers else ""
        return "changes requested" + who
    # Empty / REVIEW_REQUIRED / anything else → review required (Review Focus #3).
    return "review required"


def _ci_icon(checks: CheckSummary) -> str:
    if checks.failed > 0:
        return "✖"
    if checks.pending > 0:
        return "◐"
    return "●"


def render(state: dict, checks: CheckSummary, interval: int, as_json: bool) -> str:
    """Render the status block as JSON (--json) or the human block (spec §6)."""
    if as_json:
        return json.dumps(
            {
                "number": state.get("number"),
                "title": state.get("title"),
                "url": state.get("url"),
                "ci": {
                    "passed": checks.passed,
                    "pending": checks.pending,
                    "failed": checks.failed,
                },
                "review": _review_text(state),
                "state": state.get("state"),
                "merged": bool(state.get("mergedAt")),
            }
        )
    sep = "─" * 33
    lines = [
        f"PR #{state.get('number')}  {state.get('title')}",
        sep,
        f"CI      {_ci_icon(checks)} {checks.passed} pass · {checks.pending} pending · {checks.failed} fail",
        f"Review  {_review_text(state)}",
        f"State   {(state.get('state') or '').lower()}",
        sep,
        f"watching… (every {interval}s, ctrl-C to exit)",
    ]
    return "\n".join(lines)


class NoPRError(GhError):
    """No PR exists for the current branch."""


def resolve_pr(arg) -> int:
    """Resolve the PR number from the arg, else the current branch's PR.

    Raises NoPRError when the branch genuinely has no PR; raises GhAuthError /
    GhError for auth / transient operational failures (shared retry logic).
    """
    if arg is not None:
        try:
            return int(arg)
        except ValueError:
            raise NoPRError(f"invalid PR number: {arg!r}")
    # Auto-detect: retry transient errors, distinguish a real "no PR" (gh exits
    # non-zero with a not-found message) from operational failures.
    last_err = ""
    for attempt in range(3):
        proc = subprocess.run(
            ["gh", "pr", "view", "--json", "number"], capture_output=True, text=True
        )
        if proc.returncode == 0:
            return json.loads(proc.stdout)["number"]
        last_err = proc.stderr
        low = last_err.lower()
        if _is_auth_error(last_err):
            raise GhAuthError(
                "gh is not authenticated. Run `gh auth login` or inject a token "
                f"via credentials-cli. (gh said: {last_err.strip()})"
            )
        if "no pull requests found" in low or "not found" in low:
            raise NoPRError(
                "No PR found for the current branch. Pass a PR number: github pr-watch <pr>"
            )
        if attempt < 2:
            time.sleep(2**attempt)
    raise GhError(f"gh pr view failed after 3 attempt(s): {last_err.strip()}")


def diagnose_failure(state: dict) -> str:
    """Run `ci-debug analyze --format json` for the PR branch; return a one-line root cause.

    Extracts the first likely cause from the JSON `root_causes`. Returns ""
    (with a stderr warning) when ci-debug is missing, repo lookup fails, or
    diagnosis errors — the CI-failure exit code is unaffected.
    """
    if shutil.which("ci-debug") is None:
        print("warning: --diagnose set but ci-debug not found on PATH", file=sys.stderr)
        return ""
    repo_proc = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
    )
    repo = repo_proc.stdout.strip()
    if repo_proc.returncode != 0 or not repo:
        print("warning: --diagnose could not determine repo", file=sys.stderr)
        return ""
    branch = state.get("headRefName") or ""
    proc = subprocess.run(
        ["ci-debug", "analyze", repo, "--branch", branch, "--format", "json"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"warning: ci-debug analyze failed: {proc.stderr.strip()[:120]}", file=sys.stderr)
        return ""
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("warning: ci-debug returned non-JSON output", file=sys.stderr)
        return ""
    root_causes = data.get("root_causes") or []
    for rc in root_causes:
        causes = rc.get("likely_causes") or []
        if causes:
            return causes[0]
    return ""


def _run_loop(args) -> int:
    while True:
        state = fetch_state(args.pr)
        checks = classify_checks(state.get("statusCheckRollup"))
        if not args.once and not args.json:
            print("\033[2J\033[H", end="")  # clear screen, cursor home
        # flush=True so piped JSON/block output is emitted each cycle, not buffered.
        print(render(state, checks, args.interval, args.json), flush=True)
        term = terminal_state(state, checks, args.exit_on_approved)
        if term is not None:
            code, message = term
            # In --json mode keep stdout pure JSON; verdict goes to stderr.
            print(message, file=sys.stderr if args.json else sys.stdout)
            if code == 2 and args.diagnose:
                diag = diagnose_failure(state)
                if diag:
                    print(diag, file=sys.stderr if args.json else sys.stdout)
            return code
        if args.once:
            return 0
        time.sleep(args.interval)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="github pr-watch",
        description="Watch a PR's CI/review/merge state; exit on terminal state.",
    )
    parser.add_argument(
        "pr", nargs="?", default=None, help="PR number (default: current branch's PR)"
    )
    parser.add_argument(
        "--interval", type=int, default=15, help="poll interval in seconds (default 15)"
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="on CI failure, run ci-debug analyze and print root cause",
    )
    parser.add_argument(
        "--exit-on-approved",
        action="store_true",
        help="exit 0 as soon as the PR is approved (before merge)",
    )
    parser.add_argument("--once", action="store_true", help="single poll, print status, exit")
    parser.add_argument(
        "--json", action="store_true", help="emit status as JSON instead of the human block"
    )
    args = parser.parse_args(argv)
    if args.interval < 1:
        parser.error("--interval must be a positive integer")
    try:
        args.pr = resolve_pr(args.pr)
        return _run_loop(args)
    except KeyboardInterrupt:
        return 130
    except NoPRError as e:
        print(str(e), file=sys.stderr)
        return 3
    except GhAuthError as e:
        print(str(e), file=sys.stderr)
        return 4
    except GhError as e:
        print(f"error: {e}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    sys.exit(main())
