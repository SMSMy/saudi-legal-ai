#!/usr/bin/env python3
"""
check_regulation_updates.py
Saudi Legal AI Framework — regulation-watch checker (metadata-only).

يكشف إشارات الاشتباه بتحديث تشريعي دون نسخ أي نص قانوني:
HTTP status / final URL / ETag / Last-Modified / Content-Length فقط.
NO body is ever stored, copied, or interpreted as legal text.

Signals are metadata-only: HTTP status / final URL / ETag /
Last-Modified / Content-Length. No response body is stored,
copied, or interpreted as legal text.

Policy basis:
- docs/official-api-sources.md — unlicensed scraping is prohibited.
- Only Bureau of Experts (boe.gov.sa) + Official Gazette (uqn.gov.sa)
  carry authoritative text; this script NEVER decides what the law says.
- Any SUSPECT / NEEDS_HUMAN_REVIEW result is a task for a licensed
  Saudi attorney — never an automatic content update.

Usage:
    python scripts/check_regulation_updates.py --offline
    python scripts/check_regulation_updates.py --check
    python scripts/check_regulation_updates.py --check --update-state
    python scripts/check_regulation_updates.py --check --json --state evals/.regulation-watch-state.json

Exit codes: 0 = all OK (or baseline), 1 = suspect/needs-review found,
            2 = infrastructure errors (network blocked etc.).
"""

import argparse
import datetime
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_REGISTRY = REPO_ROOT / "evals" / "source-registry.json"
DEFAULT_STATE = REPO_ROOT / "evals" / ".regulation-watch-state.json"

USER_AGENT = (
    "SaudiLegalAIFramework-RegulationWatch/1.0 "
    "(+https://github.com/Samix2026/saudi-legal-ai-framework)"
)
REQUEST_TIMEOUT = 15
RATE_LIMIT_SECONDS = 1.5

STATUS_OK = "OK"
STATUS_SUSPECT = "SUSPECT"
STATUS_NEW = "NEW"
STATUS_UNREACHABLE = "UNREACHABLE"
STATUS_SKIPPED = "SKIPPED"
STATUS_NEEDS_REVIEW = "NEEDS_HUMAN_REVIEW"


# ── Registry / state ─────────────────────────────────────────────────────────

def load_registry(registry_path: Path) -> dict:
    """Return {source_id: entry} excluding underscore-prefixed meta keys."""
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {"version": 1, "updated_at": None, "entries": {}}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "updated_at": None, "entries": {}}
    state.setdefault("version", 1)
    state.setdefault("entries", {})
    return state


def save_state(state_path: Path, state: dict) -> None:
    state["updated_at"] = _utcnow_iso()
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Metadata-only probing ────────────────────────────────────────────────────

def fingerprint_of(status: object, final_url: str, etag: str, last_modified: str,
                   content_length: str) -> str:
    """Metadata fingerprint — headers only, never response body."""
    raw = "|".join([str(status), final_url or "", etag or "", last_modified or "",
                    content_length or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def probe_url(url: str, session=None, timeout: int = REQUEST_TIMEOUT) -> dict:
    """
    HEAD request (headers only). Falls back to a header-only streamed GET
    when the server rejects HEAD (405/501). Never reads the response body.
    Returns dict with ok/status/final_url/etag/last_modified/content_length/error.
    """
    try:
        import requests
    except ImportError:
        return {"ok": False, "url": url, "error": "requests package not installed"}

    headers = {"User-Agent": USER_AGENT}
    try:
        resp = session.head(url, headers=headers, timeout=timeout, allow_redirects=True) \
            if session is not None else __import__("requests").head(
                url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code in (405, 501):
            resp = session.get(url, headers=headers, timeout=timeout,
                               allow_redirects=True, stream=True) \
                if session is not None else __import__("requests").get(
                    url, headers=headers, timeout=timeout,
                    allow_redirects=True, stream=True)
            resp.close()  # headers captured; body never read
        return {
            "ok": True,
            "url": url,
            "status": resp.status_code,
            "final_url": str(resp.url),
            "etag": resp.headers.get("ETag", ""),
            "last_modified": resp.headers.get("Last-Modified", ""),
            "content_length": resp.headers.get("Content-Length", ""),
            "rate_limited": resp.status_code == 429,
        }
    except Exception as exc:  # network blocked, DNS, TLS, timeout…
        return {"ok": False, "url": url, "error": f"{type(exc).__name__}: {exc}"}


# ── Entry check ──────────────────────────────────────────────────────────────

def _monitor_urls(entry: dict) -> list:
    """Primary url + sector_feed, de-duplicated. Never invented — registry only."""
    urls = []
    for key in ("url", "sector_feed"):
        u = (entry.get(key) or "").strip()
        if u and u not in urls:
            urls.append(u)
    return urls


def static_review_notes(entry: dict) -> list:
    """Known internal flags that always require human review (no network)."""
    notes = []
    for key in ("known_amendment_note", "known_discrepancy_note"):
        if entry.get(key):
            notes.append(entry[key])
    return notes


def check_entry(source_id: str, entry: dict, prior: dict | None,
                probe_fn=probe_url, sleep_fn=time.sleep,
                rate_state: dict | None = None) -> dict:
    """
    Check one registry entry. probe_fn(url) -> probe dict (injectable for tests).
    rate_state: shared {"halt": bool, "last_hit": {host: ts}} for politeness.
    """
    if rate_state is None:
        rate_state = {"halt": False, "last_hit": {}}

    result = {
        "source_id": source_id,
        "name": entry.get("name", source_id),
        "citation": entry.get("citation", ""),
        "source_file": entry.get("source_file", ""),
        "review_priority": entry.get("review_priority", "medium"),
        "static_notes": static_review_notes(entry),
        "probes": [],
        "status": STATUS_OK,
        "detail": "",
    }

    for url in _monitor_urls(entry):
        if rate_state["halt"]:
            result["probes"].append({"url": url, "skipped": True,
                                    "reason": "halted after HTTP 429"})
            continue
        host = urlparse(url).netloc
        last = rate_state["last_hit"].get(host, 0.0)
        wait = RATE_LIMIT_SECONDS - (time.monotonic() - last)
        if wait > 0:
            sleep_fn(wait)
        probe = probe_fn(url)
        rate_state["last_hit"][host] = time.monotonic()
        result["probes"].append(probe)
        if probe.get("rate_limited"):
            rate_state["halt"] = True

    ok_probes = [p for p in result["probes"] if p.get("ok")]
    if not ok_probes:
        if any("skipped" in p for p in result["probes"]):
            result["status"] = STATUS_SKIPPED
            result["detail"] = "Skipped after rate-limit (HTTP 429) — rerun later."
        else:
            result["status"] = STATUS_UNREACHABLE
            result["detail"] = "; ".join(
                f'{p.get("url")}: {p.get("error")}' for p in result["probes"])
        return result

    first = ok_probes[0]
    fp = fingerprint_of(first.get("status"), first.get("final_url", ""),
                        first.get("etag", ""), first.get("last_modified", ""),
                        first.get("content_length", ""))
    result["fingerprint"] = fp

    if prior is None or not prior.get("fingerprint"):
        result["status"] = STATUS_NEW
        result["detail"] = (f"Baseline recorded for {first.get('url')} "
                            f"(HTTP {first.get('status')}).")
    elif prior["fingerprint"] != fp:
        result["status"] = STATUS_SUSPECT
        changes = []
        for key, label in (("status", "HTTP status"), ("final_url", "final URL"),
                           ("etag", "ETag"), ("last_modified", "Last-Modified"),
                           ("content_length", "Content-Length")):
            old = (prior.get("signal") or {}).get(key, "")
            new = first.get(key, "")
            if str(old) != str(new):
                changes.append(f"{label}: {old!r} → {new!r}")
        result["detail"] = ("Metadata signal changed at "
                            f"{first.get('url')} — " + "; ".join(changes))
        result["prior_signal"] = prior.get("signal")
        result["current_signal"] = {k: first.get(k) for k in
                                    ("status", "final_url", "etag",
                                     "last_modified", "content_length")}
    else:
        result["status"] = STATUS_OK
        result["detail"] = (f"No metadata change at {first.get('url')} "
                            f"(HTTP {first.get('status')}).")

    if result["static_notes"]:
        # Static internal flags escalate OK/NEW to human review, never downgrade SUSPECT.
        if result["status"] in (STATUS_OK, STATUS_NEW):
            result["status"] = STATUS_NEEDS_REVIEW
            result["detail"] += " | Internal flag requires attorney review: " + \
                " / ".join(result["static_notes"])
        else:
            result["detail"] += " | Internal flag: " + " / ".join(result["static_notes"])
    return result


def run_checks(registry: dict, state: dict, probe_fn=probe_url,
               sleep_fn=None, offline: bool = False) -> list:
    """Run checks for all enabled entries. Returns list of result dicts."""
    if sleep_fn is None:
        sleep_fn = (lambda s: None) if offline else time.sleep
    rate_state = {"halt": False, "last_hit": {}}
    results = []
    for source_id in sorted(registry):
        entry = registry[source_id]
        if isinstance(entry, dict) and entry.get("monitor", {}).get("enabled", True) is False:
            continue
        if offline:
            res = {
                "source_id": source_id,
                "name": entry.get("name", source_id),
                "citation": entry.get("citation", ""),
                "source_file": entry.get("source_file", ""),
                "review_priority": entry.get("review_priority", "medium"),
                "static_notes": static_review_notes(entry),
                "probes": [],
                "status": STATUS_SKIPPED,
                "detail": "Offline mode — network probing skipped.",
            }
            if res["static_notes"]:
                res["status"] = STATUS_NEEDS_REVIEW
                res["detail"] = "Internal flag requires attorney review: " + \
                    " / ".join(res["static_notes"])
            results.append(res)
            continue
        prior = (state.get("entries") or {}).get(source_id)
        results.append(check_entry(source_id, entry, prior, probe_fn=probe_fn,
                                   sleep_fn=sleep_fn, rate_state=rate_state))
    return results


def summarize(results: list) -> dict:
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    actionable = [r for r in results if r["status"] in (STATUS_SUSPECT, STATUS_NEEDS_REVIEW)]
    return {"counts": counts, "actionable": [r["source_id"] for r in actionable],
            "total": len(results)}


# ── Reporting ────────────────────────────────────────────────────────────────

def render_markdown(results: list, summary: dict) -> str:
    lines = [
        "# Regulation Watch Report / تقرير مراقبة الأنظمة",
        "",
        f"_Generated (UTC): {_utcnow_iso()} — metadata-only signals, "
        "not legal advice. أي اشتباه يتطلب تحقق محامٍ مرخّص قبل أي تعديل._",
        "",
        "## Summary / الملخص",
        "",
        f"- Total monitored: {summary['total']}",
    ]
    for st in (STATUS_SUSPECT, STATUS_NEEDS_REVIEW, STATUS_UNREACHABLE,
               STATUS_NEW, STATUS_OK, STATUS_SKIPPED):
        if summary["counts"].get(st):
            lines.append(f"- {st}: {summary['counts'][st]}")
    lines += ["", "## Findings / النتائج", ""]
    lines += ["| Source | Citation | Status | Detail |",
              "|--------|----------|--------|--------|"]
    for r in results:
        detail = (r.get("detail") or "").replace("\n", " ").replace("|", "/")
        if len(detail) > 300:
            detail = detail[:297] + "…"
        lines.append(f"| {r['source_id']} | {r.get('citation', '')} | "
                     f"**{r['status']}** | {detail} |")
    lines += [
        "",
        "## Required human steps / خطوات بشرية مطلوبة",
        "",
        "1. Open each SUSPECT / NEEDS_HUMAN_REVIEW official URL above "
        "(boe.gov.sa → laws.boe.gov.sa → uqn.gov.sa → sector feed).",
        "2. Compare decree number + article text against the repo's "
        "`source_file` and `sources/regulation-index.md`.",
        "3. If confirmed: update `sources/…md` + `regulation-index.md` first, "
        "then datasets; set affected rows to `deprecated`/`superseded` per "
        "`docs/legal-verification-lifecycle.md`; open a PR with official links.",
        "4. Re-run with `--update-state` ONLY after the human verification "
        "decision is recorded.",
        "",
        "> تحذير: هذا تقرير إشارات أولي ولا يُعدّ استشارة قانونية. يجب مراجعة "
        "مختص قانوني مرخّص في المملكة العربية السعودية قبل اتخاذ أي إجراء.",
        "> Warning: this is a preliminary signal report, not legal advice. "
        "A licensed legal professional in Saudi Arabia must verify before action.",
    ]
    return "\n".join(lines) + "\n"


def apply_state_updates(state: dict, results: list) -> dict:
    """Fold current fingerprints into state (call only after human review)."""
    now = _utcnow_iso()
    entries = state.setdefault("entries", {})
    for r in results:
        prev = entries.get(r["source_id"], {})
        ent = dict(prev)
        if not ent.get("first_seen"):
            ent["first_seen"] = now
        ent["last_seen"] = now
        if r.get("fingerprint"):
            if ent.get("fingerprint") and ent["fingerprint"] != r["fingerprint"]:
                ent["last_change"] = now
            ent["fingerprint"] = r["fingerprint"]
            first_probe = next((p for p in r.get("probes", []) if p.get("ok")), None)
            if first_probe:
                ent["signal"] = {k: first_probe.get(k) for k in
                                 ("status", "final_url", "etag",
                                  "last_modified", "content_length")}
        if r["status"] == STATUS_UNREACHABLE:
            ent["consecutive_unreachable"] = int(ent.get("consecutive_unreachable", 0)) + 1
        else:
            ent["consecutive_unreachable"] = 0
        entries[r["source_id"]] = ent
    return state


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Regulation-watch: metadata-only update-signal checker.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--report", default=None,
                        help="Write Markdown report to this path.")
    parser.add_argument("--check", action="store_true",
                        help="Probe official URLs (default when no flags given).")
    parser.add_argument("--offline", action="store_true",
                        help="Skip network; report static internal flags only.")
    parser.add_argument("--update-state", action="store_true",
                        help="Persist fingerprints to state file (after human review).")
    parser.add_argument("--update-state-if-clean", action="store_true",
                        help="Persist fingerprints ONLY when no actionable findings "
                             "(for scheduled CI: keeps the baseline fresh while "
                             "freezing it whenever a signal awaits human review).")
    parser.add_argument("--json", action="store_true",
                        help="Print machine-readable JSON summary to stdout.")
    args = parser.parse_args(argv)

    registry_path = Path(args.registry)
    state_path = Path(args.state)
    if not registry_path.exists():
        print(f"ERROR: registry not found: {registry_path}", file=sys.stderr)
        return 2

    registry = load_registry(registry_path)
    state = load_state(state_path)
    results = run_checks(registry, state, offline=args.offline)
    summary = summarize(results)

    if args.json:
        print(json.dumps({"summary": summary, "results": results},
                         ensure_ascii=False, indent=2))
    else:
        print(render_markdown(results, summary))

    if args.report:
        Path(args.report).write_text(render_markdown(results, summary), encoding="utf-8")
        print(f"Report written to {args.report}")

    if args.update_state or (args.update_state_if_clean and not summary["actionable"]):
        state = apply_state_updates(state, results)
        save_state(state_path, state)
        print(f"State updated at {state_path}")
    elif args.update_state_if_clean and summary["actionable"]:
        print("State NOT updated: actionable findings await human review "
              "(baseline frozen so the signal persists).")

    if summary["actionable"]:
        return 1
    if summary["counts"].get(STATUS_UNREACHABLE) and \
            summary["counts"].get(STATUS_UNREACHABLE) == summary["total"]:
        return 2  # total network failure — infra issue, not a legal signal
    return 0


if __name__ == "__main__":
    sys.exit(main())
