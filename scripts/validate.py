#!/usr/bin/env python3
"""
validate.py — pre-flight checks for the profile repository.

Verifies, and exits non-zero on the first failure:
  1. both SVGs parse as valid XML
  2. data/profile.yml parses as valid YAML with required keys
  3. README.md has exactly one now-block marker pair
  4. every image referenced in README.md exists in the repo
  5. every URL referenced in README.md / profile.yml uses https
  6. no secret-looking material anywhere in the repo

Usage: python3 scripts/validate.py
"""

from __future__ import annotations

import os
import re
import sys
import xml.dom.minidom

try:
    import yaml
except ImportError:
    print("[validate] ERROR: PyYAML is required: pip install pyyaml")
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"nvapi-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)password\s*[:=]\s*['\"][^'\"]{8,}"),
]
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}
SKIP_FILES = {"validate.py"}  # this file legitimately contains the patterns

failures = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[validate] {status}  {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    # 1 ── XML validity
    for svg in ("assets/hero.svg", "assets/project-map.svg", "assets/activity.svg"):
        path = os.path.join(ROOT, svg)
        try:
            xml.dom.minidom.parse(path)
            check(f"XML valid: {svg}", True)
        except FileNotFoundError:
            check(f"XML valid: {svg}", False, "file missing")
        except Exception as e:
            check(f"XML valid: {svg}", False, repr(e))

    # 2 ── YAML validity + required keys
    try:
        with open(os.path.join(ROOT, "data", "profile.yml")) as f:
            profile = yaml.safe_load(f)
        for key in ("identity", "now", "links", "featured", "deployed"):
            check(f"profile.yml key: {key}", isinstance(profile.get(key), dict | list))
    except Exception as e:
        check("profile.yml parses", False, repr(e))

    # 3 ── README markers
    with open(os.path.join(ROOT, "README.md")) as f:
        readme = f.read()
    check("README now-block markers",
          readme.count("<!-- @BEGIN:now -->") == 1
          and readme.count("<!-- @END:now -->") == 1)

    # 4 ── images referenced in README exist
    for ref in re.findall(r'src="([^"]+)"', readme):
        if ref.startswith(("http://", "https://")):
            continue
        check(f"image exists: {ref}", os.path.exists(os.path.join(ROOT, ref)))

    # 5 ── links are https
    for ref in re.findall(r'\]\((https?://[^)]+)\)', readme) + re.findall(r'src="(https?://[^"]+)"', readme):
        check(f"https only: {ref[:60]}", ref.startswith("https://"))
    try:
        for link in profile.get("links", {}).values():
            if isinstance(link, str) and link.startswith("http"):
                check(f"https only: {link[:60]}", link.startswith("https://"))
    except Exception:
        pass

    # 6 ── secret scan across the whole repo
    hits = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn in SKIP_FILES or not fn.isascii():
                continue
            p = os.path.join(dirpath, fn)
            try:
                with open(p, errors="ignore") as f:
                    text = f.read()
            except Exception:
                continue
            for pat in SECRET_PATTERNS:
                m = pat.search(text)
                if m:
                    hits.append(f"{os.path.relpath(p, ROOT)} matches {pat.pattern[:30]}…")
    check("no secrets in repo", not hits, "; ".join(hits))

    print()
    if failures:
        print(f"[validate] {len(failures)} check(s) FAILED — refusing to ship.")
        return 1
    print("[validate] all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
