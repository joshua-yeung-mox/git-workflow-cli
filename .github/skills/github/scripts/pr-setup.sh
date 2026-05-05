#!/usr/bin/env bash
set -euo pipefail
# PR Setup Script - Add assignee, labels, and reviewers
# Usage: pr-setup.sh <repo-path> <pr-number> <assignee> <semver-label>

REPO_PATH="${1:-.}"
PR_NUMBER="$2"
ASSIGNEE="$3"
SEMVER_LABEL="$4"

if [ -z "$PR_NUMBER" ] || [ -z "$ASSIGNEE" ] || [ -z "$SEMVER_LABEL" ]; then
    echo "Usage: pr-setup.sh <repo-path> <pr-number> <assignee> <semver-label>"
    echo "  semver-label: patch|minor|major"
    exit 1
fi

cd "$REPO_PATH"

echo "Setting up PR #$PR_NUMBER..."

# Set assignee
echo "Adding assignee: $ASSIGNEE"
gh pr edit "$PR_NUMBER" --add-assignee "$ASSIGNEE"

# Note: Labels may not exist in all repos, so we skip this
# If you need to add labels, uncomment:
# echo "Adding label: $SEMVER_LABEL"
# gh pr edit "$PR_NUMBER" --add-label "$SEMVER_LABEL" || echo "Warning: Label not found"

# Request Copilot review
echo "Requesting Copilot review..."
REPO_OWNER=$(gh repo view --json owner --jq '.owner.login')
REPO_NAME=$(gh repo view --json name --jq '.name')
gh api -X POST "repos/$REPO_OWNER/$REPO_NAME/pulls/$PR_NUMBER/requested_reviewers" \
    -F 'reviewers[]=copilot' >/dev/null 2>&1 || echo "Note: Copilot user may not exist"

echo "PR setup complete!"
echo "PR URL: $(gh pr view $PR_NUMBER --json url --jq '.url')"
