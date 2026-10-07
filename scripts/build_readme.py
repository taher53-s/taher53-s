#!/usr/bin/env python3
"""
build_readme.py — renders the SYSTEM STATUS block inside README.md
from data/profile.yml.

Only the text between the <!-- @BEGIN:now --> / <!-- @END:now --> markers
is regenerated; everything else in the README is hand-authored and
untouched. The block is rewritten in place only when content actually
changes (idempotent — safe to run as often as you like).

Usage:  python3 scripts/build_readme.py
Requires: PyYAML (the single dependency of this system).
"""

from __future__ import annotations

import os
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "..", "data", "profile.yml")
README = os.path.join(HERE, "..", "README.md")

BEGIN = "<!-- @BEGIN:now -->"
END = "<!-- @END:now -->"


def log(msg: str) -> None:
    print(f"[readme] {msg}", flush=True)


def render_block(now: dict) -> str:
    rows = [
        ("building", "▸ building", now.get("building", [])),
        ("learning", "learning", now.get("learning", [])),
        ("exploring", "exploring", now.get("exploring", [])),
        ("open to", "open_to", now.get("open_to", [])),
    ]

    lines = [
        "| now | focus |",
        "|---|---|",
    ]
    for label, _key, items in rows:
        joined = " · ".join(items) if items else "—"
        lines.append(f"| **{label}** | {joined} |")
    return "\n".join(lines)


def main() -> int:
    with open(PROFILE) as f:
        profile = yaml.safe_load(f)

    block = render_block(profile.get("now", {}))

    with open(README) as f:
        readme = f.read()

    if readme.count(BEGIN) != 1 or readme.count(END) != 1:
        log(f"ERROR: README.md must contain exactly one {BEGIN} and one {END}.")
        return 2

    head, _, rest = readme.partition(BEGIN)
    _, _, tail = rest.partition(END)
    new_readme = f"{head}{BEGIN}\n{block}\n{END}{tail}"

    if new_readme == readme:
        log("status block unchanged — README.md not modified.")
        return 0

    with open(README, "w") as f:
        f.write(new_readme)
    log("README.md status block re-rendered from data/profile.yml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
