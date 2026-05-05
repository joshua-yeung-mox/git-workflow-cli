#!/usr/bin/env bash
set -euo pipefail
# Mark PR Ready for Review Script
# Usage: pr-ready.sh <repo-path> <pr-number> [--skip-checks]

REPO_PATH="${1:-.}"
PR_NUMBER="$2"
SKIP_CHECKS="${3:-}"

if [ -z "$PR_NUMBER" ]; then
    echo "Usage: pr-ready.sh <repo-path> <pr-number> [--skip-checks]"
    exit 1
fi

cd "$REPO_PATH"

echo "Checking PR #$PR_NUMBER status..."

# Check if PR is draft
IS_DRAFT=$(gh pr view "$PR_NUMBER" --json isDraft --jq '.isDraft')

if [ "$IS_DRAFT" = "false" ]; then
    echo "PR is already marked as ready for review"
    exit 0
fi

# Check CI status unless skipped
if [ "$SKIP_CHECKS" != "--skip-checks" ]; then
    echo "Checking CI status..."
    
    # Get check status
    CHECKS_OUTPUT=$(gh pr checks "$PR_NUMBER" 2>&1 || true)
    
    if echo "$CHECKS_OUTPUT" | grep -q "failing"; then
        echo "Warning: Some CI checks are failing"
        echo "$CHECKS_OUTPUT"
        read -p "Continue marking as ready? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Aborted"
            exit 1
        fi
    elif echo "$CHECKS_OUTPUT" | grep -q "pending"; then
        echo "Warning: Some CI checks are still pending"
        echo "$CHECKS_OUTPUT"
        read -p "Continue marking as ready? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Aborted"
            exit 1
        fi
    fi
fi

# Mark as ready
echo "Marking PR #$PR_NUMBER as ready for review..."
gh pr ready "$PR_NUMBER"

echo "PR #$PR_NUMBER is now ready for review!"
echo "PR URL: $(gh pr view $PR_NUMBER --json url --jq '.url')"
