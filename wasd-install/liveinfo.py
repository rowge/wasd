#!/usr/bin/env python3
"""Print the live USB's disks and warnings as JSON. This does not erase."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/usr/libexec")

from disks import live_payload  # noqa: E402


def main():
    try:
        print(json.dumps(live_payload()))
    except Exception:
        print(json.dumps({"warnings": ["The disks could not be read."], "blocked": True, "disks": []}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
