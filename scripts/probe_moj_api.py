"""
probe_moj_api.py — clean-parser trial against the Ministry of Justice API.

The MOJ gateway is NOT the source of the three Wave-2 laws (Labor, Civil
Transactions, PDPL); it covers judicial laws.  This probe proves the parser is
clean before it is reused:

    POST https://laws-gateway.moj.gov.sa/apis/legislations/v1/statute/section-search
    GET  https://laws-gateway.moj.gov.sa/apis/legislations/v1/statute/get-Statute-gateway-Detail?Serial=<serial>

Observed 2026-11-23 for نظام المرافعات الشرعية:
    14 chapters, 243 article nodes (type=1), 0 empty texts.
    One sequence is "المادية الحادية والستون" (a publisher typo); a tolerant
    parser must not drop it.

Usage:
    python scripts/probe_moj_api.py
    python scripts/probe_moj_api.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request

BASE = "https://laws-gateway.moj.gov.sa/apis/legislations/v1"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ar,en;q=0.8",
    "Content-Type": "application/json",
    "Origin": "https://laws.moj.gov.sa",
    "Referer": "https://laws.moj.gov.sa/",
}


def _request(url: str, body: dict | None = None, *, attempts: int = 4) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    last_error: Exception | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(2)
        request = urllib.request.Request(url, data=data, headers=HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310
                raw = response.read()
            if raw.lstrip().startswith((b"{", b"[")):
                return json.loads(raw.decode("utf-8"))
            last_error = ValueError(f"non-JSON response ({len(raw)} bytes)")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
    raise SystemExit(f"MOJ API did not return JSON after {attempts} attempts: {last_error}")


def find_serial(name: str) -> str:
    payload = _request(
        f"{BASE}/statute/section-search",
        {"pageNumber": 1, "pageSize": 20, "searchText": name},
    )
    for item in payload.get("model", {}).get("collection", []):
        if name in (item.get("statuteName") or ""):
            return item["serial"]
    raise SystemExit(f"Could not find statute: {name}")


def flatten_articles(structure: list[dict]) -> tuple[list[dict], list[dict]]:
    articles: list[dict] = []
    chapters: list[dict] = []

    def walk(node: dict) -> None:
        node_type = node.get("type")
        if node_type == 3:
            chapters.append(node)
        if node_type == 1:
            text = re.sub(r"<[^>]+>", " ", node.get("text") or "")
            text = re.sub(r"\s+", " ", text).strip()
            articles.append({
                "sequence": node.get("sequence") or "",
                "text": text,
                "legal_status": node.get("legalStatusName"),
                "decree": node.get("decree"),
                "is_cancelled": node.get("isCancelled"),
            })
        for child in node.get("items") or []:
            walk(child)

    for chapter in structure:
        walk(chapter)
    return articles, chapters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="نظام المرافعات الشرعية")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    serial = find_serial(args.name)
    time.sleep(2)  # documented WAF spacing between search and detail
    detail = _request(f"{BASE}/statute/get-Statute-gateway-Detail?Serial={serial}")
    model = detail.get("model", {})
    articles, chapters = flatten_articles(model.get("statuteStructure") or [])

    odd = [
        a["sequence"] for a in articles
        if a["sequence"] and not a["sequence"].startswith("المادة")
    ]
    empty = [a for a in articles if not a["text"]]
    report = {
        "name": model.get("name"),
        "serial": model.get("serial"),
        "legal_status": model.get("legalStatueName"),
        "chapters": len(chapters),
        "articles": len(articles),
        "empty_articles": len(empty),
        "non_standard_sequences": odd,
        "sample": articles[:2],
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['name']} ({report['serial']}) — {report['legal_status']}")
        print(f"chapters={report['chapters']} articles={report['articles']} empty={report['empty_articles']}")
        if odd:
            print("non-standard sequences:", ", ".join(odd))
        print("PASS: parser found article structure" if articles and not empty else "FAIL")
    return 0 if articles and not empty else 1


if __name__ == "__main__":
    raise SystemExit(main())
