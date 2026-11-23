"""
embed_document_links.py — put each source document's link inside every section.

Wave 1 requirement: a section must not return `citations: []` merely because
the document link lives only in the file footer.  This script inserts one
honest reference line under every level-2/3 heading that does not already
contain the document URL.  It is idempotent and does not invent URLs: the link
is taken from URLs already present in the file.

Usage:
    python scripts/embed_document_links.py
    python scripts/embed_document_links.py --check
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from saudi_legal_mcp.tools.provenance import (  # noqa: E402
    LINK_ARTICLE,
    LINK_DOCUMENT,
    LINK_PORTAL,
    classify_url,
    document_reference,
)
from saudi_legal_mcp.tools.sources import VALID_REGULATIONS  # noqa: E402

DATA_DIR = REPO_ROOT / "saudi_legal_mcp" / "data"
SOURCES_DIR = DATA_DIR / "sources"

_MARKERS = ("**رابط الوثيقة:**", "**رابط البوابة:**", "**رابط المادة:**")
_SKIP_HEADINGS = ("المصادر الرسمية", "Official Sources", "See also", "انظر أيضًا", "المصادر والمراجع")


def _marker_for(document: dict) -> str:
    url = document["url"]
    info = classify_url(url)
    if info["link_type"] == LINK_ARTICLE:
        return f"> **رابط المادة:** [أصل المادة]({url}) — يفتح المادة الممسوحة، لا القسم."
    if info["link_type"] == LINK_DOCUMENT:
        return f"> **رابط الوثيقة:** [وثيقة النظام]({url}) — يفتح الوثيقة كاملة، لا هذا القسم."
    return f"> **رابط البوابة:** [بوابة الجهة]({url}) — رابط عام، لا يفتح هذا القسم مباشرة."


def _heading_level(line: str) -> int:
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return 0
    return len(stripped) - len(stripped.lstrip("#"))


def embed(text: str, document: dict) -> tuple[str, int]:
    lines = text.splitlines()
    url = document["url"]
    marker = _marker_for(document)

    # Normalise an older/longer marker line in place, so this script stays
    # idempotent across wording changes.
    normalised = 0
    new_lines: list[str] = []
    for line in lines:
        if any(m in line for m in _MARKERS):
            if line != marker:
                normalised += 1
            new_lines.append(marker)
        else:
            new_lines.append(line)
    lines = new_lines

    output: list[str] = []
    changes = normalised
    i = 0

    while i < len(lines):
        line = lines[i]
        level = _heading_level(line)
        output.append(line)

        if level not in (2, 3) or any(skip in line for skip in _SKIP_HEADINGS):
            i += 1
            continue

        # Check only the heading's IMMEDIATE body (until the next heading of
        # any level).  A link inside a child section does not cover the parent
        # heading — the parent is still a section the reader can land on.
        j = i + 1
        while j < len(lines):
            if _heading_level(lines[j]):
                break
            j += 1

        section = "\n".join(lines[i:j])
        if url in section or any(m in section for m in _MARKERS):
            i += 1
            continue

        # Insert after the heading, preserving a blank line if present.
        output.append("")
        output.append(marker)
        changes += 1
        i += 1

    result = "\n".join(output)
    if text.endswith("\n"):
        result += "\n"
    return result, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if any file would change.")
    args = parser.parse_args()

    total = 0
    changed_files: list[str] = []
    for source_id in sorted(VALID_REGULATIONS):
        path = SOURCES_DIR / f"{source_id}.md"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        document = document_reference(text)
        if document is None:
            continue
        new_text, changes = embed(text, document)
        if changes:
            changed_files.append(f"{source_id}: {changes} section(s)")
            total += changes
            if not args.check:
                path.write_text(new_text, encoding="utf-8")

    for item in changed_files:
        print(item)
    print(f"[embed_document_links] {total} section(s) in {len(changed_files)} file(s)")

    if args.check and total:
        print("Files are missing in-section document links.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
