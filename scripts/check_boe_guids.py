"""
check_boe_guids.py — detect stale Bureau of Experts (BOE) law GUIDs.

BOE returns HTTP 500 for a retired GUID; that is NOT a geo-block.  The current
index is `BoeLaws/Laws/Folders` (one page, 517 laws).  This script compares:

  - corpus/<law>.json document_url GUIDs,
  - evals/source-registry.json boe_reference_url GUIDs,
  - LawDetails links inside sources/*.md,

against the GUIDs currently listed in Folders.

Usage (inside the Kingdom; BOE is blocked from CI):

    python scripts/check_boe_guids.py
    python scripts/check_boe_guids.py --input saved-folders.html
    python scripts/check_boe_guids.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bs4 import BeautifulSoup  # noqa: E402

from scripts.ingest_laws import fetch  # noqa: E402

FOLDERS_URL = "https://laws.boe.gov.sa/BoeLaws/Laws/Folders"
_GUID_RE = re.compile(r"LawDetails/([0-9a-fA-F-]{36})")
_CORPUS_DIR = REPO_ROOT / "saudi_legal_mcp" / "data" / "corpus"
_SOURCES_DIR = REPO_ROOT / "saudi_legal_mcp" / "data" / "sources"
_REGISTRY = REPO_ROOT / "evals" / "source-registry.json"


def _guids_in_text(text: str) -> set[str]:
    return {match.group(1).lower() for match in _GUID_RE.finditer(text)}


def current_folder_guids(html_bytes: bytes) -> tuple[set[str], str]:
    soup = BeautifulSoup(html_bytes, "html.parser", from_encoding="utf-8")
    guids: set[str] = set()
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "LawDetails" not in href:
            continue
        match = _GUID_RE.search(href)
        if match:
            guids.add(match.group(1).lower())
    if not guids:
        raise SystemExit("No LawDetails GUIDs found in Folders — is the page layout changed?")
    return guids, urljoin(FOLDERS_URL, "")


def tracked_guids() -> dict[str, set[str]]:
    tracked: dict[str, set[str]] = {}

    for corpus_file in sorted(_CORPUS_DIR.glob("*.json")):
        data = json.loads(corpus_file.read_text(encoding="utf-8"))
        guids = _guids_in_text(str(data.get("document_url") or ""))
        if guids:
            tracked[f"corpus/{corpus_file.name}"] = guids

    for source_file in sorted(_SOURCES_DIR.glob("*.md")):
        guids = _guids_in_text(source_file.read_text(encoding="utf-8"))
        if guids:
            tracked[f"source/{source_file.name}"] = guids

    if _REGISTRY.exists():
        data = json.loads(_REGISTRY.read_text(encoding="utf-8"))
        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            guids = _guids_in_text(str(entry.get("boe_reference_url") or ""))
            if guids:
                tracked[f"registry/{key}"] = guids

    return tracked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="Saved Folders HTML (no network).")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    html_bytes = Path(args.input).read_bytes() if args.input else fetch(FOLDERS_URL)
    current, _ = current_folder_guids(html_bytes)
    tracked = tracked_guids()

    stale: dict[str, list[str]] = {}
    for label, guids in tracked.items():
        missing = sorted(guids - current)
        if missing:
            stale[label] = missing

    report = {
        "folders_url": FOLDERS_URL,
        "current_guid_count": len(current),
        "tracked_entries": len(tracked),
        "stale": stale,
        "status": "stale" if stale else "current",
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Folders: {len(current)} GUIDs")
        print(f"Tracked entries: {len(tracked)}")
        if stale:
            for label, guids in stale.items():
                print(f"STALE {label}: {', '.join(guids)}", file=sys.stderr)
            print("A stale GUID means the law page moved or was retired; re-check Folders.", file=sys.stderr)
        else:
            print("All tracked BOE GUIDs are present in Folders [OK]")

    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
