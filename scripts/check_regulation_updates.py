#!/usr/bin/env python3
"""
check_regulation_updates.py — v2
Saudi Legal AI Framework — regulation-watch checker (metadata-only).

يكشف إشارات الاشتباه بتحديث تشريعي دون نسخ أي نص قانوني:
HTTP status / final URL / ETag / Last-Modified / Content-Length فقط.
NO body is ever stored, copied, or interpreted as legal text.

v2 fixes (review-driven):
- Every monitored URL gets its OWN fingerprint (gazette + istitlaa +
  sector, not just the first successful probe). Fields that are absent
  in the registry are skipped honestly — never invented.
- Confidence weighting: only an `exact` (law-page / gazette / named
  document) signal change raises SUSPECT. A `portal` (homepage) change
  raises PORTAL_CHANGED — informational, never an Issue by itself.
- Static internal flags (known amendments, date discrepancies) are
  REPORT-ONLY: they appear in the report but never change a status,
  never block the baseline, and never open an Issue.

Policy basis:
- docs/official-api-sources.md — unlicensed scraping is prohibited.
- Only Bureau of Experts (boe.gov.sa) + Official Gazette (uqn.gov.sa)
  carry authoritative text; this script NEVER decides what the law says.
- Any SUSPECT result is a task for a licensed Saudi attorney —
  never an automatic content update.

Usage:
    python scripts/check_regulation_updates.py --offline
    python scripts/check_regulation_updates.py --check
    python scripts/check_regulation_updates.py --check --update-state
    python scripts/check_regulation_updates.py --check --json --state evals/.regulation-watch-state.json

Exit codes: 0 = no SUSPECT (baseline / OK / portal-noise only),
            1 = SUSPECT found, 2 = infrastructure errors.
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
    "SaudiLegalAI-RegulationWatch/2.0 "
    "(+https://github.com/SMSMy/saudi-legal-ai)"
)
REQUEST_TIMEOUT = 15
RATE_LIMIT_SECONDS = 1.5

STATUS_OK = "OK"
STATUS_SUSPECT = "SUSPECT"
STATUS_PORTAL_CHANGED = "PORTAL_CHANGED"
STATUS_NEW = "NEW"
STATUS_UNREACHABLE = "UNREACHABLE"
STATUS_SKIPPED = "SKIPPED"

CONF_EXACT = "exact"
CONF_PORTAL = "portal"

# (registry field, signal kind, default confidence)
# Absent/empty fields are skipped — URLs are never invented.
WATCH_FIELDS = (
    ("url", "law_page", None),  # confidence comes from entry.url_confidence
    ("gazette_url", "gazette", CONF_EXACT),
    ("istitlaa_url", "istitlaa", CONF_EXACT),
    ("sector_feed", "sector", CONF_PORTAL),
)

SIGNAL_KEYS = ("status", "final_url", "etag", "last_modified", "content_length")


# ── Registry / state ─────────────────────────────────────────────────────────

def load_registry(registry_path: Path) -> dict:
    """Return {source_id: entry} excluding underscore-prefixed meta keys."""
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {"version": 2, "updated_at": None, "entries": {}}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 2, "updated_at": None, "entries": {}}
    # v1 → v2 migration: old single-fingerprint entries cannot be mapped
    # to per-URL signals, so they are treated as fresh baselines.
    if state.get("version", 1) < 2:
        return {"version": 2, "updated_at": None, "entries": {}}
    state.setdefault("version", 2)
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
        if session is not None:
            resp = session.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        else:
            import requests as rq
            resp = rq.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code in (405, 501):
            if session is not None:
                resp = session.get(url, headers=headers, timeout=timeout,
                                   allow_redirects=True, stream=True)
            else:
                import requests as rq
                resp = rq.get(url, headers=headers, timeout=timeout,
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

def watch_targets(entry: dict) -> list:
    """
    Ordered [{url, kind, confidence}] for every URL field present in the
    registry entry. Absent fields are skipped — URLs are never invented.
    """
    targets = []
    seen = set()
    for field, kind, default_conf in WATCH_FIELDS:
        u = (entry.get(field) or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        if field == "url":
            conf = entry.get("url_confidence", CONF_PORTAL)
        else:
            conf = default_conf
        targets.append({"url": u, "kind": kind, "confidence": conf})
    return targets


def static_review_notes(entry: dict) -> list:
    """Known internal flags — report-only, never affect status or baseline."""
    notes = []
    for key in ("known_amendment_note", "known_discrepancy_note"):
        if entry.get(key):
            notes.append(entry[key])
    return notes


def _signal_of(probe: dict) -> dict:
    return {k: probe.get(k, "") for k in SIGNAL_KEYS}


def _describe_change(old: dict, new: dict) -> str:
    labels = {"status": "HTTP status", "final_url": "final URL", "etag": "ETag",
              "last_modified": "Last-Modified", "content_length": "Content-Length"}
    changes = [f"{labels[k]}: {old.get(k, '')!r} → {new.get(k, '')!r}"
               for k in SIGNAL_KEYS if str(old.get(k, "")) != str(new.get(k, ""))]
    return "; ".join(changes) if changes else "signal bytes differ"


def check_entry(source_id: str, entry: dict, prior_entry: dict | None,
                probe_fn=probe_url, sleep_fn=time.sleep,
                rate_state: dict | None = None) -> dict:
    """
    Check one registry entry against its per-URL baseline.
    probe_fn(url) -> probe dict (injectable for tests).
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
        "flags": static_review_notes(entry),  # report-only
        "targets": watch_targets(entry),
        "probes": [],
        "status": STATUS_OK,
        "detail": "",
    }

    prior_urls = (prior_entry or {}).get("urls", {}) if prior_entry else {}
    is_new_entry = not prior_entry

    for target in result["targets"]:
        url = target["url"]
        if rate_state["halt"]:
            result["probes"].append({"url": url, "kind": target["kind"],
                                     "skipped": True,
                                     "reason": "halted after HTTP 429"})
            continue
        host = urlparse(url).netloc
        last = rate_state["last_hit"].get(host, 0.0)
        wait = RATE_LIMIT_SECONDS - (time.monotonic() - last)
        if wait > 0:
            sleep_fn(wait)
        probe = dict(probe_fn(url))
        probe["kind"] = target["kind"]
        probe["confidence"] = target["confidence"]
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

    # Per-URL fingerprint comparison.
    for probe in ok_probes:
        probe["fingerprint"] = fingerprint_of(
            probe.get("status"), probe.get("final_url", ""), probe.get("etag", ""),
            probe.get("last_modified", ""), probe.get("content_length", ""))
        probe["signal"] = _signal_of(probe)

    exact_changes, portal_changes, fresh = [], [], []
    for probe in ok_probes:
        prev = prior_urls.get(probe["url"])
        if prev is None or not prev.get("fingerprint"):
            fresh.append(probe)
        elif prev["fingerprint"] != probe["fingerprint"]:
            item = (f'[{probe["kind"]}] {probe["url"]} — '
                    f'{_describe_change(prev.get("signal", {}), probe["signal"])}')
            if probe.get("confidence") == CONF_EXACT:
                exact_changes.append(item)
            else:
                portal_changes.append(item)

    if exact_changes:
        result["status"] = STATUS_SUSPECT
        result["detail"] = "Exact-signal change: " + " / ".join(exact_changes)
        if portal_changes:
            result["detail"] += " | Portal-noise (informational): " + " / ".join(portal_changes)
    elif portal_changes:
        result["status"] = STATUS_PORTAL_CHANGED
        result["detail"] = ("Portal-homepage signal moved (weak signal — homepage "
                            "content churns for non-legal reasons): " +
                            " / ".join(portal_changes))
    elif is_new_entry:
        result["status"] = STATUS_NEW
        reached = ", ".join(f'{p["url"]} (HTTP {p.get("status")})' for p in ok_probes)
        result["detail"] = f"Baseline recorded for: {reached}."
    else:
        parts = [f'{p["url"]} (HTTP {p.get("status")})' for p in ok_probes]
        result["detail"] = "No metadata change at: " + ", ".join(parts) + "."
        if fresh:
            result["detail"] += (" Newly tracked URL(s) baselined: " +
                                 ", ".join(p["url"] for p in fresh) + ".")

    if result["flags"]:
        result["detail"] += (f" [internal flags: {len(result['flags'])} — "
                             "see Internal Flags section; report-only]")
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
            results.append({
                "source_id": source_id,
                "name": entry.get("name", source_id),
                "citation": entry.get("citation", ""),
                "source_file": entry.get("source_file", ""),
                "review_priority": entry.get("review_priority", "medium"),
                "flags": static_review_notes(entry),
                "targets": watch_targets(entry),
                "probes": [],
                "status": STATUS_SKIPPED,
                "detail": "Offline mode — network probing skipped.",
            })
            continue
        prior = (state.get("entries") or {}).get(source_id)
        results.append(check_entry(source_id, entry, prior, probe_fn=probe_fn,
                                   sleep_fn=sleep_fn, rate_state=rate_state))
    return results


def summarize(results: list) -> dict:
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    # Only exact-signal changes are actionable. Portal noise and static
    # flags never open an Issue and never freeze the baseline.
    actionable = [r for r in results if r["status"] == STATUS_SUSPECT]
    flagged = [r["source_id"] for r in results if r.get("flags")]
    return {"counts": counts, "actionable": [r["source_id"] for r in actionable],
            "flagged": flagged, "total": len(results)}


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
    for st in (STATUS_SUSPECT, STATUS_PORTAL_CHANGED, STATUS_UNREACHABLE,
               STATUS_NEW, STATUS_OK, STATUS_SKIPPED):
        if summary["counts"].get(st):
            lines.append(f"- {st}: {summary['counts'][st]}")
    if summary.get("flagged"):
        lines.append(f"- entries with internal flags (report-only): {len(summary['flagged'])}")
    lines += ["", "## Findings / النتائج", ""]
    lines += ["| Source | Citation | Status | Detail |",
              "|--------|----------|--------|--------|"]
    for r in results:
        detail = (r.get("detail") or "").replace("\n", " ").replace("|", "/")
        if len(detail) > 300:
            detail = detail[:297] + "…"
        lines.append(f"| {r['source_id']} | {r.get('citation', '')} | "
                     f"**{r['status']}** | {detail} |")

    flagged_results = [r for r in results if r.get("flags")]
    if flagged_results:
        lines += ["", "## Internal Flags / أعلام داخلية (report-only)", "",
                  "_These are known review items tracked separately. They do NOT "
                  "affect statuses, do NOT block the baseline, and do NOT open "
                  "Issues by themselves._",
                  "",
                  "يُتابَع كل علَم عبر Issue تحقق بشرية مستقلة — لا علاقة له بالفحص الأسبوعي.",
                  ""]
        for r in flagged_results:
            lines.append(f"- **{r['source_id']}** (`{r.get('source_file', '')}`)")
            for note in r["flags"]:
                lines.append(f"  - {note}")

    lines += [
        "",
        "## Required human steps / خطوات بشرية مطلوبة",
        "",
        "1. For each SUSPECT: open its exact-confidence URL(s) "
        "(laws.boe.gov.sa → uqn.gov.sa gazette link → named document).",
        "2. Compare decree number + article text against the repo's "
        "`source_file` and `sources/regulation-index.md`.",
        "3. If confirmed: update `sources/regulation-index.md` FIRST, "
        "then `sources/…md`, then datasets (`deprecated`/`superseded` per "
        "`docs/legal-verification-lifecycle.md`); open a PR with official links.",
        "4. Re-run with `--update-state` ONLY after the human verification "
        "decision is recorded.",
        "5. PORTAL_CHANGED needs no action unless a pattern repeats across weeks.",
        "",
        "> تحذير: هذا تقرير إشارات أولي ولا يُعدّ استشارة قانونية. يجب مراجعة "
        "مختص قانوني مرخّص في المملكة العربية السعودية قبل اتخاذ أي إجراء.",
        "> Warning: this is a preliminary signal report, not legal advice. "
        "A licensed legal professional in Saudi Arabia must verify before action.",
    ]
    return "\n".join(lines) + "\n"


def apply_state_updates(state: dict, results: list) -> dict:
    """Fold current per-URL fingerprints into state (call only after human review)."""
    now = _utcnow_iso()
    entries = state.setdefault("entries", {})
    for r in results:
        prev = entries.get(r["source_id"], {})
        ent = dict(prev)
        if not ent.get("first_seen"):
            ent["first_seen"] = now
        ent["last_seen"] = now
        stored_urls = dict(ent.get("urls", {}))
        for probe in r.get("probes", []):
            if not probe.get("ok") or not probe.get("fingerprint"):
                continue
            old = stored_urls.get(probe["url"], {})
            if old.get("fingerprint") and old["fingerprint"] != probe["fingerprint"]:
                if probe.get("confidence") == CONF_EXACT:
                    ent["last_change"] = now
            stored_urls[probe["url"]] = {
                "fingerprint": probe["fingerprint"],
                "kind": probe.get("kind", ""),
                "confidence": probe.get("confidence", ""),
                "signal": probe.get("signal", {}),
                "last_seen": now,
            }
        ent["urls"] = stored_urls
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
                        help="Skip network; list watch targets and internal flags only.")
    parser.add_argument("--update-state", action="store_true",
                        help="Persist fingerprints to state file (after human review).")
    parser.add_argument("--update-state-if-clean", action="store_true",
                        help="Persist fingerprints ONLY when no SUSPECT findings "
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
        print("State NOT updated: SUSPECT findings await human review "
              "(baseline frozen so the signal persists).")

    if summary["actionable"]:
        return 1
    if summary["counts"].get(STATUS_UNREACHABLE) and \
            summary["counts"].get(STATUS_UNREACHABLE) == summary["total"]:
        return 2  # total network failure — infra issue, not a legal signal
    return 0


if __name__ == "__main__":
    sys.exit(main())
