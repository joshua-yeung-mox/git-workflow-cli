#!/usr/bin/env bash
set -euo pipefail
# PR Creation Script
# Usage: pr-create.sh <repo-path> <title> <body-file> [--draft]

REPO_PATH="${1:-.}"
TITLE="$2"
BODY_FILE="$3"
DRAFT_FLAG="${4:-}"

if [ -z "$TITLE" ] || [ -z "$BODY_FILE" ]; then
    echo "Usage: pr-create.sh <repo-path> <title> <body-file> [--draft]"
    exit 1
fi

if [ ! -f "$BODY_FILE" ]; then
    echo "Error: Body file '$BODY_FILE' not found"
    exit 1
fi

cd "$REPO_PATH"

# Get current branch
CURRENT_BRANCH=$(git branch --show-current)
echo "Current branch: $CURRENT_BRANCH"

# Extract JIRA key from branch name
JIRA_KEY=$(echo "$CURRENT_BRANCH" | grep -oE '[A-Z]+-[0-9]+' | head -1)
if [ -z "$JIRA_KEY" ]; then
    echo "Warning: No JIRA key found in branch name"
fi

# Check for existing PR
echo "Checking for existing PRs..."
EXISTING_PR=$(gh pr list --head "$CURRENT_BRANCH" --json number --jq '.[0].number')

if [ -n "$EXISTING_PR" ]; then
    echo "Error: PR #$EXISTING_PR already exists for branch $CURRENT_BRANCH"
    exit 1
fi

# Create PR
echo "Creating PR..."
if [ "$DRAFT_FLAG" = "--draft" ]; then
    PR_NUMBER=$(gh pr create --title "$TITLE" --body-file "$BODY_FILE" --draft --json number --jq '.number')
else
    PR_NUMBER=$(gh pr create --title "$TITLE" --body-file "$BODY_FILE" --json number --jq '.number')
fi

echo "Created PR #$PR_NUMBER"
echo "PR URL: $(gh pr view $PR_NUMBER --json url --jq '.url')"

# Return PR number for chaining
echo "$PR_NUMBER"
