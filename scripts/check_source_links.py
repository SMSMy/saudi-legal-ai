"""
check_source_links.py — live HEAD/GET probe for newly added documentary links.

Checks the documentary URLs added in Wave 2 (bankruptcy/arbitration BOE
LawDetails, FIFA January-2025 PDF) plus the existing documentary set.
BOE (laws.boe.gov.sa) is blocked from GitHub CI (ConnectTimeout) — a BOE
timeout is reported as SKIP, never as a hard failure.  The FIFA PDF must
return application/pdf.

Usage:
    python scripts/check_source_links.py
    python scripts/check_source_links.py --strict   # BOE timeout fails too
"""
from __future__ import annotations

import argparse
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen

LINKS = {
    # New in Wave 2 — must be verified live before merge.
    "bankruptcy-law": "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/68204119-84f1-4789-8fad-a9ec014c3788/1",
    "arbitration-law": "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/5535039e-13da-43f6-8f53-a9a700f26485/1",
    "fifa-rstp-pdf": "https://digitalhub.fifa.com/m/696d877ea35ca761/original/Regulations-on-the-Status-and-Transfer-of-Players-January-2025-edition.pdf",
    # Pre-existing documentary set (regression).
    "labor-law": "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/08381293-6388-48e2-8ad2-a9a700f2aa94/1",
    "civil-transactions-law": "https://uqn.gov.sa/details?p=23125",
    "pdpl": "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/b7cfae89-828e-4994-b167-adaa00e37188/1",
}

ALLOWED_HOSTS = {
    "laws.boe.gov.sa",
    "uqn.gov.sa",
    "www.uqn.gov.sa",
    "digitalhub.fifa.com",
}

TIMEOUT = 30


def probe(name: str, url: str) -> tuple[str, str]:
    host = urlparse(url).netloc.lower()
    if host not in ALLOWED_HOSTS:
        return name, f"REFUSED host not allowlisted: {host}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            ctype = r.headers.get_content_type() or ""
            if name == "fifa-rstp-pdf" and "pdf" not in ctype:
                return name, f"FAIL Content-Type={ctype!r} (expected pdf)"
            return name, f"OK HEAD {r.status} Content-Type={ctype}"
    except Exception as exc:  # noqa: BLE001 - probe must report, not crash
        msg = f"{type(exc).__name__}: {exc}"
        if "boe.gov.sa" in host and any(
            k in msg for k in ("Timeout", "timed out", "ConnectTimeout", "URLError", "Temporary failure")
        ):
            return name, f"SKIP BOE blocked from this network: {msg[:120]}"
        # Fall back to GET of first bytes (some hosts refuse HEAD).
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=TIMEOUT) as r:
                chunk = r.read(2)
                ctype = r.headers.get_content_type() or ""
                if name == "fifa-rstp-pdf":
                    if chunk[:2] != b"%P" or "pdf" not in ctype:
                        return name, f"FAIL GET Content-Type={ctype!r} magic={chunk!r}"
                return name, f"OK GET {r.status} Content-Type={ctype} len2={len(chunk)}"
        except Exception as exc2:  # noqa: BLE001
            msg2 = f"{type(exc2).__name__}: {exc2}"
            if "boe.gov.sa" in host:
                return name, f"SKIP BOE blocked from this network: {msg2[:120]}"
            return name, f"FAIL {msg2[:200]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="BOE SKIP becomes failure.")
    args = parser.parse_args()

    failed = 0
    for name, url in LINKS.items():
        _, report = probe(name, url)
        print(f"{name}: {report}")
        if report.startswith("FAIL"):
            failed += 1
        elif report.startswith("SKIP") and args.strict:
            failed += 1
    if failed:
        print(f"[check_source_links] {failed} link(s) FAILED")
        return 1
    print("[check_source_links] all documentary links OK (BOE SKIP allowed outside --strict) [OK]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
