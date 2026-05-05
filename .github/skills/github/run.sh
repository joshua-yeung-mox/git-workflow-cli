#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"

usage() {
  cat <<EOF
GitHub workflow helper. Subcommands:

GitHub PR Operations:
  /github pr-setup           Setup a PR (add assignee, labels, reviewers)
  /github pr-create          Create a pull request
  /github pr-ready           Mark PR as ready for review
  /github pr-merge-master    Merge master into current branch
  /github pr-complete        Complete PR workflow
  /github pr-add-reviewers   Add team reviewers to PR
  /github pr-remove-files    Remove files from remote (keep local)

Commit Message Management:
  /github fix-commit         Check or fix commit message formatting
  /github validate-commit    Validate commit message format

Helpers:
  /github gh-api             Direct GitHub API push helper
  /github --help             Show this help

Examples:
  /github pr-setup
  /github pr-create --title "Feature: new operator"
  /github fix-commit --check
  /github fix-commit --fix --refs HEAD~5..HEAD
EOF
}

if [[ $# -eq 0 || "$1" == "--help" ]]; then
  usage
  exit 0
fi

SUBCOMMAND="$1"
shift

case "$SUBCOMMAND" in
  pr-setup)
    exec "$SCRIPTS_DIR/pr-setup.sh" "$@"
    ;;
  pr-create)
    exec "$SCRIPTS_DIR/pr-create.sh" "$@"
    ;;
  pr-ready)
    exec "$SCRIPTS_DIR/pr-ready.sh" "$@"
    ;;
  pr-merge-master)
    exec "$SCRIPTS_DIR/pr-merge-master.sh" "$@"
    ;;
  pr-complete)
    exec "$SCRIPTS_DIR/pr-complete-workflow.sh" "$@"
    ;;
  pr-add-reviewers)
    exec "$SCRIPTS_DIR/pr-add-team-reviewers.sh" "$@"
    ;;
  pr-remove-files)
    exec "$SCRIPTS_DIR/pr-remove-files-from-remote.sh" "$@"
    ;;
  fix-commit)
    exec "$SCRIPTS_DIR/fix-commit-messages.sh" "$@"
    ;;
  validate-commit)
    exec "$SCRIPTS_DIR/validate-commit-msg.py" "$@"
    ;;
  gh-api)
    exec "$SCRIPTS_DIR/gh-api-push.py" "$@"
    ;;
  *)
    echo "Unknown subcommand: $SUBCOMMAND" >&2
    usage
    exit 1
    ;;
esac
