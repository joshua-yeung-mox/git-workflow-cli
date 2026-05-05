#!/usr/bin/env bash
set -euo pipefail
# Remove Files from Remote (Keep Local) Script
# Usage: pr-remove-files-from-remote.sh <repo-path> <file1> [file2] [file3] ...

REPO_PATH="$1"
shift

if [ -z "$REPO_PATH" ] || [ $# -eq 0 ]; then
    echo "Usage: pr-remove-files-from-remote.sh <repo-path> <file1> [file2] [file3] ..."
    echo ""
    echo "Removes files from git tracking while keeping them locally."
    echo "Useful for removing committed files that should be gitignored."
    echo ""
    echo "Example:"
    echo "  pr-remove-files-from-remote.sh . .env .pre-commit-config.yaml"
    exit 1
fi

cd "$REPO_PATH"

FILES=("$@")

echo "Files to remove from remote (keeping local):"
for file in "${FILES[@]}"; do
    if [ ! -e "$file" ]; then
        echo "  ✗ $file (does not exist)"
        exit 1
    else
        echo "  • $file"
    fi
done
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted"
    exit 1
fi

# Remove from git tracking
echo "Removing from git tracking..."
git rm --cached "${FILES[@]}"

echo ""
echo "Verification:"
for file in "${FILES[@]}"; do
    if [ -e "$file" ]; then
        echo "  ✓ $file still exists locally"
    else
        echo "  ✗ $file was deleted (unexpected!)"
    fi
done

echo ""
echo "Files removed from git tracking."
echo ""
echo "Next steps:"
echo "  1. Verify files are in .gitignore"
echo "  2. Commit: git commit -m 'chore: remove files from version control'"
echo "  3. Push: git push origin \$(git branch --show-current)"
