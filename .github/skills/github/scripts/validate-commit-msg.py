#!/usr/bin/env python3
"""
Validate commit message format per dl-pipeline-data-infra requirements.

Checks:
1. Subject line ≤75 characters
2. Body lines ≤72 characters each
3. Semver token present (+semver:fix|patch|minor|major)

Usage:
    python3 scripts/github/validate-commit-msg.py
"""

import subprocess
import sys
import re


def get_commit_message(commit_sha="HEAD"):
    """Get commit message from git."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%B", commit_sha],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error reading commit message: {e.stderr}", file=sys.stderr)
        sys.exit(1)


def validate_subject_line(message):
    """Check subject line is ≤75 characters."""
    subject = message.split("\n")[0]
    length = len(subject)
    if length <= 75:
        return True, f"Subject line: {length} characters (≤75)"
    return False, f"Subject line: {length} characters (max 75)\n  Line: \"{subject[:80]}...\""


def validate_body_lines(message):
    """Check body lines are ≤72 characters each."""
    lines = message.split("\n")
    
    # Body starts after subject + blank line
    if len(lines) < 2:
        return True, "Body lines: None (not required)"
    
    if lines[1].strip() != "":
        # No blank line after subject - treat entire message as subject
        return True, "Body lines: None (no blank line after subject)"
    
    # Check body lines (start from line 2)
    body_lines = lines[2:]
    failures = []
    
    for i, line in enumerate(body_lines, start=3):
        if len(line) > 72:
            failures.append(f"  Line {i}: {len(line)} chars - \"{line[:70]}...\"")
    
    if not failures:
        return True, "Body lines: All ≤72 characters"
    
    return False, "Body lines: VIOLATIONS\n" + "\n".join(failures)


def validate_semver_token(message):
    """Check for semver token (+semver:fix|patch|minor|major)."""
    pattern = r"\+semver\s*:\s*(fix|patch|minor|major)"
    match = re.search(pattern, message, re.IGNORECASE)
    
    if match:
        return True, f"Semver token found: +semver:{match.group(1)}"
    
    return False, (
        "Semver token: NOT FOUND\n"
        "  Suggestion: Add \"+semver:fix|patch|minor|major\" to commit message"
    )


def main():
    """Validate commit message and report results."""
    message = get_commit_message()
    
    if not message.strip():
        print("Error: Commit message is empty", file=sys.stderr)
        sys.exit(1)
    
    # Run all validations
    checks = [
        ("subject", validate_subject_line(message)),
        ("body", validate_body_lines(message)),
        ("semver", validate_semver_token(message)),
    ]
    
    # Print results
    all_pass = True
    for check_name, (passed, message_text) in checks:
        status = "✓" if passed else "✗"
        print(f"{status} {message_text}")
        if not passed:
            all_pass = False
    
    # Exit code
    if all_pass:
        print("\n✓ All checks passed!")
        sys.exit(0)
    else:
        print("\n✗ Validation failed. Fix issues above and retry.")
        sys.exit(1)


if __name__ == "__main__":
    main()
