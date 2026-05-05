#!/usr/bin/env python3
"""Format a commit message from stdin to 70-char width.

Extracted from commit-cli for integration into /github skill.
"""

import sys
from pathlib import Path

# Add lib to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "lib"))

from commit_cli.formatter import format_message


def main() -> int:
    msg = sys.stdin.read()
    formatted = format_message(msg)
    sys.stdout.write(formatted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
