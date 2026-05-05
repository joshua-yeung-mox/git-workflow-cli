#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [[ -z "$REPO_ROOT" ]]; then
  echo "Not a git repository (run from inside a repo)" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/format_commit_message.py"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--check|--fix] [--refs <revspec>]

Options:
  --check        Scan commits and report commit messages that violate 70-char lines (default)
  --fix          Rewrite commit messages to wrap subject/body at 70 chars (destructive)
  --refs <ref>   Refs or revision expression to operate on (passed to git rev-list).
                 Default: commits on current branch not reachable from main/master (i.e. <base>..HEAD)
  --help         Show this help

Examples:
  $(basename "$0") --check            # scan commits on current branch since main/master
  $(basename "$0") --check --refs HEAD~10..HEAD
  $(basename "$0") --fix --refs HEAD  # rewrite only commits on HEAD
EOF
}

MODE=check
REFS=""
REFS_PROVIDED=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)
      MODE=check; shift;;
    --fix)
      MODE=fix; shift;;
    --refs)
      shift
      if [[ $# -eq 0 ]]; then
        echo "--refs requires an argument" >&2; usage; exit 2
      fi
      REFS="$1"; REFS_PROVIDED=true; shift;;
    --help)
      usage; exit 0;;
    *)
      echo "Unknown arg: $1" >&2; usage; exit 2;;
  esac
done

if [[ ! -f "$PY_SCRIPT" ]]; then
  echo "Missing helper script: $PY_SCRIPT" >&2
  exit 3
fi

detect_base() {
  # prefer remote main/master, then local main/master
  candidates=("origin/main" "origin/master" "main" "master")
  for c in "${candidates[@]}"; do
    if git rev-parse --verify --quiet "$c" >/dev/null 2>&1; then
      echo "$c"
      return 0
    fi
  done
  # fall back to origin/HEAD target if present
  if git symbolic-ref --quiet refs/remotes/origin/HEAD >/dev/null 2>&1; then
    tgt=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || true)
    if [[ -n "$tgt" ]] && git rev-parse --verify --quiet "$tgt" >/dev/null 2>&1; then
      echo "$tgt"
      return 0
    fi
  fi
  return 1
}

if [[ "$REFS_PROVIDED" = false ]]; then
  if base=$(detect_base); then
    REFS="$base..HEAD"
    echo "Defaulting to commits not in $base (range: $REFS)"
  else
    REFS="HEAD"
    echo "Warning: could not detect main/master; scanning all commits reachable from HEAD."
  fi
fi

if [[ "$MODE" == "check" ]]; then
  echo "Scanning commits in: $REFS"
  BAD=0
  # iterate commits oldest-first without using a pipeline to preserve BAD counter
  while read -r commit; do
    if ! git log -n1 --format=%B "$commit" | python3 "$PY_SCRIPT" --check >/dev/null; then
      echo
      echo "Commit: $commit"
      git --no-pager log -n1 --format="%h %s" "$commit"
      git log -n1 --format=%B "$commit" | python3 "$PY_SCRIPT" --check || true
      BAD=$((BAD+1))
    fi
  done < <(git rev-list --reverse $REFS)
  if [[ $BAD -eq 0 ]]; then
    echo "No violations found."
    exit 0
  else
    echo "$BAD commit(s) violate formatting."
    exit 1
  fi
fi

# MODE == fix
cat <<'WARN'
WARNING: This will rewrite Git history for the specified refs. Back up your repository
(e.g., git clone --mirror . ../backup.git) and ensure you understand the impact.
WARN

read -p "Type 'yes' to proceed: " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
  echo "Aborting."; exit 0
fi

echo "Rewriting commit messages for: $REFS"

git filter-branch -f --msg-filter "python3 \"$PY_SCRIPT\"" -- $REFS

RC=$?
if [[ $RC -ne 0 ]]; then
  echo "git filter-branch failed (rc=$RC)" >&2; exit $RC
fi

echo "Rewrite finished. Inspect history, then push with: git push --force-with-lease <remote> <branch>"
echo "filter-branch left backups under refs/original/; remove them when happy:"
echo "  git for-each-ref --format='%(refname)' refs/original/ | xargs -r -n1 git update-ref -d"

exit 0
