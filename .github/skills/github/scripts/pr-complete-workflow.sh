#!/usr/bin/env bash
set -euo pipefail
# Complete PR Workflow Script
# Usage: pr-complete-workflow.sh <repo-path> <title> <body-file> <assignee> <semver-label> <team-slug> [--draft]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_PATH="${1:-.}"
TITLE="$2"
BODY_FILE="$3"
ASSIGNEE="$4"
SEMVER_LABEL="$5"
TEAM_SLUG="$6"
DRAFT_FLAG="${7:-}"

if [ -z "$TITLE" ] || [ -z "$BODY_FILE" ] || [ -z "$ASSIGNEE" ] || [ -z "$SEMVER_LABEL" ] || [ -z "$TEAM_SLUG" ]; then
    echo "Usage: pr-complete-workflow.sh <repo-path> <title> <body-file> <assignee> <semver-label> <team-slug> [--draft]"
    echo ""
    echo "Arguments:"
    echo "  repo-path      Path to repository (default: current directory)"
    echo "  title          PR title"
    echo "  body-file      Path to file containing PR description"
    echo "  assignee       GitHub username to assign"
    echo "  semver-label   Semantic version level: patch|minor|major"
    echo "  team-slug      Team slug for reviewers (e.g., data-services)"
    echo "  --draft        Optional: Create as draft PR"
    echo ""
    echo "Example:"
    echo "  pr-complete-workflow.sh ~/repos/my-repo 'Fix bug' pr-body.md john-doe minor data-services --draft"
    exit 1
fi

cd "$REPO_PATH"

echo "=========================================="
echo "PR Complete Workflow"
echo "=========================================="
echo "Repository: $(pwd)"
echo "Title: $TITLE"
echo "Assignee: $ASSIGNEE"
echo "Semver: $SEMVER_LABEL"
echo "Team: $TEAM_SLUG"
if [ "$DRAFT_FLAG" = "--draft" ]; then
    echo "Mode: Draft"
else
    echo "Mode: Ready for review"
fi
echo "=========================================="
echo ""

# Step 1: Create PR
echo "Step 1: Creating PR..."
PR_NUMBER=$("$SCRIPT_DIR/pr-create.sh" "$REPO_PATH" "$TITLE" "$BODY_FILE" "$DRAFT_FLAG")
echo "✓ Created PR #$PR_NUMBER"
echo ""

# Step 2: Setup PR (assignee, labels, copilot reviewer)
echo "Step 2: Setting up PR..."
"$SCRIPT_DIR/pr-setup.sh" "$REPO_PATH" "$PR_NUMBER" "$ASSIGNEE" "$SEMVER_LABEL"
echo "✓ PR setup complete"
echo ""

# Step 3: Add team reviewers
echo "Step 3: Adding team reviewers..."
"$SCRIPT_DIR/pr-add-team-reviewers.sh" "$REPO_PATH" "$PR_NUMBER" "$TEAM_SLUG" "$ASSIGNEE"
echo "✓ Team reviewers added"
echo ""

# Step 4: Mark ready if not draft
if [ "$DRAFT_FLAG" != "--draft" ]; then
    echo "Step 4: Marking PR as ready for review..."
    "$SCRIPT_DIR/pr-ready.sh" "$REPO_PATH" "$PR_NUMBER" --skip-checks
    echo "✓ PR marked as ready"
    echo ""
fi

echo "=========================================="
echo "PR Workflow Complete!"
echo "=========================================="
echo "PR #$PR_NUMBER: $(gh pr view $PR_NUMBER --json url --jq '.url')"
echo ""
echo "Next steps:"
if [ "$DRAFT_FLAG" = "--draft" ]; then
    echo "  1. Complete testing checklist items"
    echo "  2. Wait for CI checks to pass"
    echo "  3. Run: pr-ready.sh '$REPO_PATH' $PR_NUMBER"
else
    echo "  1. Monitor CI checks"
    echo "  2. Address any review feedback"
    echo "  3. Merge when approved"
fi
echo "=========================================="
