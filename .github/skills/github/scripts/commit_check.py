#!/usr/bin/env python3
"""Scan commits and report messages with lines > 70 chars."""

import subprocess
import sys
from typing import Optional

WIDTH = 70


def _normalize_newlines(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def check_message(msg: str) -> list[tuple[str, int, int, str]]:
    """Return list of violations: (type, lineno, length, line_text)
    
    type is 'subject' or 'body'
    """
    msg = _normalize_newlines(msg)
    lines = msg.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    violations: list[tuple[str, int, int, str]] = []
    if i < len(lines):
        subject = lines[i]
        if len(subject) > WIDTH:
            violations.append(("subject", i + 1, len(subject), subject))
    for idx, line in enumerate(lines[i + 1 :], start=i + 2):
        if len(line) > WIDTH:
            violations.append(("body", idx, len(line), line))
    return violations


def _git_verify(ref: str) -> bool:
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref]).returncode == 0


def detect_base() -> Optional[str]:
    candidates = ["origin/main", "origin/master", "main", "master"]
    for c in candidates:
        if _git_verify(c):
            return c
    # try origin/HEAD
    try:
        p = subprocess.run(
            ["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
        )
        if p.returncode == 0:
            ref = p.stdout.strip()
            if ref.startswith("refs/remotes/"):
                short = (
                    "/".join(ref.split("/")[3:]) if len(ref.split("/")) >= 4 else ref
                )
                if _git_verify(short):
                    return short
    except Exception:
        pass
    return None


def main() -> int:
    import argparse
    
    p = argparse.ArgumentParser(
        description="Scan commits and report messages with lines > 70 chars"
    )
    p.add_argument(
        "--refs", "-r",
        help="Revspec to scan (default: base..HEAD)"
    )
    args = p.parse_args()
    
    refs = args.refs
    if refs is None:
        base = detect_base()
        if base:
            refs = f"{base}..HEAD"
            print(f"Defaulting to commits not in {base} (range: {refs})")
        else:
            refs = "HEAD"
            print("Warning: could not detect main/master; scanning all commits reachable from HEAD.")
    
    print(f"Scanning commits in: {refs}")
    
    p = subprocess.run(
        ["git", "rev-list", "--reverse", refs], capture_output=True, text=True
    )
    if p.returncode != 0:
        print(f"git rev-list failed: {p.stderr}", file=sys.stderr)
        return 2
    
    bad = 0
    for commit in filter(None, p.stdout.splitlines()):
        msg_proc = subprocess.run(
            ["git", "log", "-1", "--format=%B", commit],
            capture_output=True,
            text=True,
        )
        if msg_proc.returncode != 0:
            continue
        
        violations = check_message(msg_proc.stdout)
        if violations:
            bad += 1
            print(f"{commit[:7]} {msg_proc.stdout.splitlines()[0][:50]}")
            for typ, lineno, length, line in violations:
                print(f"  {typ} line {lineno}: len={length}")
                print(f"    {line}")
    
    if bad:
        print(f"\n❌ Found {bad} commit(s) with lines > 70 chars")
        return 1
    else:
        print("\n✅ All commits passed (lines ≤ 70 chars)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
