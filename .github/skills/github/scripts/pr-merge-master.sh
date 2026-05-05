#!/usr/bin/env bash
set -euo pipefail
# Merge Master into Current Branch Script
# Usage: pr-merge-master.sh <repo-path> [base-branch]

REPO_PATH="${1:-.}"
BASE_BRANCH="${2:-master}"

cd "$REPO_PATH"

CURRENT_BRANCH=$(git branch --show-current)

if [ "$CURRENT_BRANCH" = "$BASE_BRANCH" ]; then
    echo "Error: Already on $BASE_BRANCH branch"
    exit 1
fi

echo "Current branch: $CURRENT_BRANCH"
echo "Base branch: $BASE_BRANCH"
echo ""

# Fetch latest from base
echo "Fetching latest from $BASE_BRANCH..."
git fetch origin "$BASE_BRANCH"

# Show what will be merged
COMMITS_BEHIND=$(git rev-list --count HEAD..origin/$BASE_BRANCH)
echo "Your branch is $COMMITS_BEHIND commits behind origin/$BASE_BRANCH"
echo ""

if [ "$COMMITS_BEHIND" -eq 0 ]; then
    echo "Already up to date with $BASE_BRANCH"
    exit 0
fi

# Merge with theirs strategy for conflicts
echo "Merging origin/$BASE_BRANCH into $CURRENT_BRANCH..."
git merge origin/$BASE_BRANCH --no-edit || {
    echo ""
    echo "Merge conflicts detected. Resolving..."
    echo "Manual intervention may be required."
    exit 1
}

echo ""
echo "Merge completed successfully!"
echo ""
echo "Next steps:"
echo "  1. Review the merge commit"
echo "  2. Test the changes"
echo "  3. Push: git push origin $CURRENT_BRANCH"
