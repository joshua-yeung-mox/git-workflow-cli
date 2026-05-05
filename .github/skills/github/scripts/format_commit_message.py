#!/usr/bin/env python3
"""
Format or check a commit message so the subject and body lines are <= 70 chars.

Special behavior:
- Trailing 'Co-authored-by:' trailers are exempt from the body line-width wrap/check.
- Formatting will remove angle-bracketed emails from Co-authored-by trailers.
- Check mode will fail if any Co-authored-by trailer contains an email address.

Usage:
  # Format from stdin -> stdout
  echo "$(git log -n1 --format=%B <commit>)" | python3 scripts/format_commit_message.py

  # Check from stdin (exit 0 if OK, 1 if violations printed)
  echo "$(git log -n1 --format=%B <commit>)" | python3 scripts/format_commit_message.py --check
"""

from __future__ import annotations
import sys
import textwrap
import re
from typing import List, Tuple

WIDTH = 70


def _normalize_newlines(s: str) -> str:
    return s.replace('\r\n', '\n').replace('\r', '\n')


def _split_subject_body(msg: str):
    lines = msg.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i >= len(lines):
        return "", []
    subject = lines[i].rstrip()
    body = lines[i + 1 :]
    return subject, body


def _partition_trailers(body_lines: list[str]) -> Tuple[list[str], list[str], int | None]:
    """Separate trailing Co-authored-by trailers from the body.

    Returns (body_without_trailers, trailers, trailer_start_index_relative_to_body)
    If no trailer block is found, trailers will be an empty list and trailer_start is None.
    """
    if not body_lines:
        return body_lines, [], None
    # find last non-empty line
    j = len(body_lines) - 1
    while j >= 0 and body_lines[j].strip() == "":
        j -= 1
    if j < 0:
        return body_lines, [], None
    if not body_lines[j].lstrip().startswith("Co-authored-by:"):
        return body_lines, [], None
    # trailer block detected; walk backward to find its start (allowing blank lines between trailers)
    k = j
    while k >= 0:
        line = body_lines[k]
        if line.strip() == "":
            k -= 1
            continue
        if line.lstrip().startswith("Co-authored-by:"):
            k -= 1
            continue
        break
    trailer_start = k + 1
    return body_lines[:trailer_start], body_lines[trailer_start:], trailer_start


def _wrap_paragraph(par_lines: list[str]) -> list[str]:
    text = " ".join(l.strip() for l in par_lines)
    if not text:
        return []
    return textwrap.wrap(text, WIDTH)


def _wrap_body(body_lines: list[str]) -> list[str]:
    out: list[str] = []
    para: list[str] = []
    for ln in body_lines:
        if ln.strip() == "":
            if para:
                out.extend(_wrap_paragraph(para))
                para = []
            out.append("")
        else:
            para.append(ln)
    if para:
        out.extend(_wrap_paragraph(para))
    return out


def _clean_trailer_line(line: str) -> str:
    """Remove angle-bracketed emails from a trailer line and normalize whitespace."""
    cleaned = re.sub(r"<[^>]*>", "", line)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _trailer_contains_email(line: str) -> bool:
    return bool(re.search(r"<[^>]+@[^>]+>", line))


def format_message(msg: str) -> str:
    msg = _normalize_newlines(msg)
    subject, body = _split_subject_body(msg)
    if subject == "":
        return msg

    wrapped_subject = textwrap.wrap(subject, WIDTH)
    subject_out = wrapped_subject[0] if wrapped_subject else ""
    extra = wrapped_subject[1:]

    new_body: list[str] = []
    if extra:
        new_body.extend(extra)
        new_body.append("")
    new_body.extend(body)

    # separate trailing Co-authored-by trailers (they are exempt from wrapping)
    body_without_trailers, trailers, _ = _partition_trailers(new_body)

    wrapped_body = _wrap_body(body_without_trailers)

    out_lines: list[str] = [subject_out]
    if wrapped_body and any(l.strip() != "" for l in wrapped_body):
        out_lines.append("")
        out_lines.extend(wrapped_body)

    if trailers:
        # ensure single blank line before trailers
        out_lines.append("")
        for t in trailers:
            if t.strip() == "":
                out_lines.append("")
            else:
                out_lines.append(_clean_trailer_line(t))

    return "\n".join(out_lines).rstrip() + "\n"


def check_message(msg: str) -> list[tuple[str, int, int, str]]:
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
    # body lines start at index i+1 (0-based)
    body_lines = lines[i + 1 :]
    body_without_trailers, trailers, trailer_start = _partition_trailers(body_lines)
    for idx, line in enumerate(body_without_trailers, start=i + 2):
        if len(line) > WIDTH:
            violations.append(("body", idx, len(line), line))
    # report emails in trailers as violations (co-author trailers must not contain emails)
    if trailers and trailer_start is not None:
        for j, tline in enumerate(trailers):
            if _trailer_contains_email(tline):
                line_no = i + 2 + trailer_start + j
                violations.append(("coauthor-email", line_no, len(tline), tline))
    return violations


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Format/check commit messages to 70-char width")
    p.add_argument("--check", action="store_true", help="Check only; exit 0 if OK else 1 and print diagnostics")
    args = p.parse_args()

    msg = sys.stdin.read()
    if args.check:
        v = check_message(msg)
        if not v:
            return 0
        for typ, lineno, length, line in v:
            sys.stdout.write(f"{typ} line {lineno}: len={length}\n  {line}\n")
        return 1
    else:
        sys.stdout.write(format_message(msg))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
