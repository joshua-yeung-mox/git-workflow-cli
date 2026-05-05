#!/usr/bin/env bash
set -euo pipefail

# Scan commits for messages with lines > 70 chars
# Integration of commit-cli check functionality

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [[ -z "$REPO_ROOT" ]]; then
  echo "Not a git repository (run from inside a repo)" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/commit_check.py"

REFS="${1:---refs-default}"

# If no args, use default behavior (commits not in base..HEAD)
if [[ "$REFS" == "--refs-default" ]]; then
  python3 "$PY_SCRIPT"
else
  python3 "$PY_SCRIPT" --refs "$REFS"
fi
