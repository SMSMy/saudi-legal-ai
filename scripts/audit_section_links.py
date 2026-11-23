"""
audit_section_links.py — reproducible count of section links in sources/.

The earlier "435" report counted normalization changes, not links.  This audit
counts actual link markers and checks every content heading's IMMEDIATE body —
a link inside a child heading does not cover its parent.

Usage:
    python scripts/audit_section_links.py
    python scripts/audit_section_links.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from saudi_legal_mcp.tools.sources import VALID_REGULATIONS  # noqa: E402

SOURCES = REPO_ROOT / "saudi_legal_mcp" / "data" / "sources"
_EXEMPT = (
    "See also",
    "انظر أيضا",
    "انظر أيضًا",
    "المصادر الرسمية",
    "Official Legal Sources",
    "المصادر والمراجع",
)


def audit() -> dict:
    headings = 0
    missing: list[dict] = []
    doc_markers = 0
    portal_markers = 0
    official_rows = 0

    for source_id in sorted(VALID_REGULATIONS):
        lines = (SOURCES / f"{source_id}.md").read_text(encoding="utf-8").splitlines()
        doc_markers += sum(1 for line in lines if "**رابط الوثيقة:**" in line)
        portal_markers += sum(1 for line in lines if "**رابط البوابة:**" in line)
        official_rows += sum(1 for line in lines if "**الرابط الرسمي**" in line)

        i = 0
        while i < len(lines):
            match = re.match(r"^(#{2,4})\s+(.*)$", lines[i])
            if not match:
                i += 1
                continue
            title = match.group(2)
            headings += 1

            j = i + 1
            while j < len(lines) and not re.match(r"^#{1,6}\s+", lines[j]):
                j += 1
            body = "\n".join(lines[i:j])

            if not any(word in title for word in _EXEMPT):
                if "https://" not in body and "http://" not in body:
                    missing.append({
                        "source_id": source_id,
                        "level": len(match.group(1)),
                        "title": title,
                    })
            i += 1

    return {
        "content_headings": headings,
        "document_markers": doc_markers,
        "portal_markers": portal_markers,
        "official_source_rows": official_rows,
        "missing_content_headings": missing,
        "missing_count": len(missing),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"headings: {report['content_headings']}")
        print(f"document markers: {report['document_markers']}")
        print(f"portal markers: {report['portal_markers']}")
        print(f"official-source rows: {report['official_source_rows']}")
        print(f"missing content headings: {report['missing_count']}")
        for item in report["missing_content_headings"]:
            print(f"  MISS {item['source_id']} L{item['level']}: {item['title']}")
    return 1 if report["missing_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
