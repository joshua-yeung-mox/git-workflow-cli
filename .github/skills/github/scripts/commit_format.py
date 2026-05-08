#!/usr/bin/env python3
"""Format a commit message from stdin to 70-char width."""

import sys
import textwrap

WIDTH = 70


def _normalize_newlines(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


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

    wrapped_body = _wrap_body(new_body)
    out_lines: list[str] = [subject_out]
    if wrapped_body and any(l.strip() != "" for l in wrapped_body):
        out_lines.append("")
        out_lines.extend(wrapped_body)

    return "\n".join(out_lines).rstrip() + "\n"


def main() -> int:
    msg = sys.stdin.read()
    formatted = format_message(msg)
    sys.stdout.write(formatted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
