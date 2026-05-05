#!/usr/bin/env bash
set -euo pipefail
# Add Team Reviewers Script
# Usage: pr-add-team-reviewers.sh <repo-path> <pr-number> <team-slug> [exclude-user]

REPO_PATH="${1:-.}"
PR_NUMBER="$2"
TEAM_SLUG="$3"
EXCLUDE_USER="${4:-}"

if [ -z "$PR_NUMBER" ] || [ -z "$TEAM_SLUG" ]; then
    echo "Usage: pr-add-team-reviewers.sh <repo-path> <pr-number> <team-slug> [exclude-user]"
    echo "  Example: pr-add-team-reviewers.sh . 1234 data-services joshua-yeung-mox"
    exit 1
fi

cd "$REPO_PATH"

echo "Fetching members of team: $TEAM_SLUG"

# Get organization
ORG=$(gh repo view --json owner --jq '.owner.login')

# Fetch team members
TEAM_MEMBERS=$(gh api "/orgs/$ORG/teams/$TEAM_SLUG/members" --jq '.[].login')

if [ -z "$TEAM_MEMBERS" ]; then
    echo "Error: No team members found or team doesn't exist"
    exit 1
fi

# Build reviewers list (exclude specified user)
REVIEWERS=()
for member in $TEAM_MEMBERS; do
    if [ -n "$EXCLUDE_USER" ] && [ "$member" = "$EXCLUDE_USER" ]; then
        echo "Excluding: $member"
        continue
    fi
    REVIEWERS+=("$member")
done

if [ ${#REVIEWERS[@]} -eq 0 ]; then
    echo "No reviewers to add"
    exit 0
fi

echo "Adding reviewers: ${REVIEWERS[*]}"

# Build JSON array for API call
REVIEWERS_JSON="["
for i in "${!REVIEWERS[@]}"; do
    if [ $i -gt 0 ]; then
        REVIEWERS_JSON+=","
    fi
    REVIEWERS_JSON+="\"${REVIEWERS[$i]}\""
done
REVIEWERS_JSON+="]"

# Add reviewers via API
REPO_NAME=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
gh api -X POST "repos/$REPO_NAME/pulls/$PR_NUMBER/requested_reviewers" \
    --input - <<EOF
{
  "reviewers": $REVIEWERS_JSON
}
EOF

echo "Successfully added ${#REVIEWERS[@]} reviewers to PR #$PR_NUMBER"
