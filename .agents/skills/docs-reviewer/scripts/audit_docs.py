#!/usr/bin/env python3
"""Audit docs/ knowledge system for compliance and health.

Checks:
1. state/ files have "Last updated" metadata
2. records/ files follow YYYY-MM-DD naming and have "Date" metadata
3. short-term.md entries have date markers
4. Internal doc links are valid
"""

import re
import sys
from pathlib import Path


def find_project_root() -> Path:
    """Walk up from script location to find project root (has docs/ dir)."""
    path = Path(__file__).resolve()
    for parent in [path] + list(path.parents):
        if (parent / "docs").is_dir():
            return parent
    print("ERROR: Could not find project root with docs/ directory")
    sys.exit(1)


ROOT = find_project_root()
DOCS = ROOT / "docs"
errors: list[str] = []
warnings: list[str] = []


def check_state_metadata():
    """Every state/ file must have '> **Last updated:** YYYY-MM-DD' on line 3."""
    state_dir = DOCS / "state"
    if not state_dir.exists():
        errors.append("docs/state/ directory does not exist")
        return

    for md in sorted(state_dir.rglob("*.md")):
        rel = md.relative_to(ROOT)
        lines = md.read_text().splitlines()
        if len(lines) < 3:
            errors.append(f"{rel}: file too short, missing metadata")
            continue
        line3 = lines[2].strip()
        if not re.match(r"^>\s*\*\*Last updated:\*\*\s*\d{4}-\d{2}-\d{2}", line3):
            errors.append(
                f"{rel}: line 3 must be '> **Last updated:** YYYY-MM-DD', got: '{line3}'"
            )


def check_records_naming_and_metadata():
    """records/ files must be YYYY-MM-DD-description.md with Date metadata."""
    records_dir = DOCS / "records"
    if not records_dir.exists():
        return  # No records yet is fine

    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}-.+\.md$")
    for md in sorted(records_dir.rglob("*.md")):
        rel = md.relative_to(ROOT)
        if not date_pattern.match(md.name):
            errors.append(f"{rel}: filename must match YYYY-MM-DD-description.md")

        lines = md.read_text().splitlines()
        if len(lines) < 3:
            errors.append(f"{rel}: file too short, missing metadata")
            continue
        line3 = lines[2].strip()
        if not re.match(r"^>\s*\*\*Date:\*\*\s*\d{4}-\d{2}-\d{2}", line3):
            errors.append(
                f"{rel}: line 3 must be '> **Date:** YYYY-MM-DD', got: '{line3}'"
            )


def check_short_term_dates():
    """short-term.md active work entries must have date markers."""
    st = DOCS / "memory" / "short-term.md"
    if not st.exists():
        errors.append("docs/memory/short-term.md does not exist")
        return

    in_active = False
    for i, line in enumerate(st.read_text().splitlines(), 1):
        if line.strip().startswith("## Active Work"):
            in_active = True
            continue
        if line.strip().startswith("## ") and in_active:
            break
        if in_active and line.strip().startswith("- **"):
            if "(started" not in line.lower():
                warnings.append(
                    f"docs/memory/short-term.md:{i}: active work entry missing (started YYYY-MM) date"
                )


def check_internal_links():
    """Verify all docs/ cross-references point to existing files."""
    link_pattern = re.compile(r"`(docs/[^`]+\.md)`")

    for md in sorted(DOCS.rglob("*.md")):
        rel = md.relative_to(ROOT)
        for i, line in enumerate(md.read_text(errors="replace").splitlines(), 1):
            for match in link_pattern.finditer(line):
                target = ROOT / match.group(1)
                if not target.exists():
                    errors.append(f"{rel}:{i}: broken link to {match.group(1)}")


def main():
    print("Auditing docs/ knowledge system...\n")

    check_state_metadata()
    check_records_naming_and_metadata()
    check_short_term_dates()
    check_internal_links()

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  ✗ {e}")
        print()

    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ⚠ {w}")
        print()

    if not errors and not warnings:
        print("✓ All checks passed.")
        return 0

    print(f"Found {len(errors)} error(s) and {len(warnings)} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
