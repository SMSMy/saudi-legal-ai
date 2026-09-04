# tests/test_regulation_watch.py
"""
Tests for scripts/check_regulation_updates.py (v2).
Saudi Legal AI Framework — regulation-watch (metadata-only) checker.

All network probing is mocked via injected probe_fn — no real HTTP.
v2: per-URL fingerprints, exact/portal confidence, static flags are
report-only (never a status, never blocking the baseline).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import check_regulation_updates as rw


# ── Helpers ──────────────────────────────────────────────────────────────────

LAW_URL = "https://example.gov.sa/law/99"
SECTOR_URL = "https://example.gov.sa/sector-feed"


def _entry(**over):
    base = {
        "name": "نظام تجريبي",
        "decree": "م/99",
        "date": "1440هـ",
        "url": LAW_URL,
        "url_confidence": "exact",
        "citation": "Test Law (Royal Decree M/99 1440H)",
        "source_file": "sources/test-law.md",
        "review_priority": "medium",
        "monitor": {"enabled": True, "signals": ["boe_law_page"]},
    }
    base.update(over)
    return base


def _probe_ok(url, status=200, final=None, etag='"abc"', lm="Wed, 01 Jan 2025 00:00:00 GMT",
              length="1234"):
    return {"ok": True, "url": url, "status": status,
            "final_url": final or url, "etag": etag,
            "last_modified": lm, "content_length": length}


def _probe_fail(url):
    return {"ok": False, "url": url, "error": "ConnectionError: blocked"}


def _no_sleep(s):
    return None


def _prior_for(probe_dicts):
    """Build a v2 prior entry from {url: probe} with matching fingerprints."""
    urls = {}
    for url, p in probe_dicts.items():
        urls[url] = {
            "fingerprint": rw.fingerprint_of(
                p["status"], p["final_url"], p["etag"],
                p["last_modified"], p["content_length"]),
            "signal": {k: p[k] for k in rw.SIGNAL_KEYS},
        }
    return {"urls": urls}


# ── Fingerprint ──────────────────────────────────────────────────────────────

def test_fingerprint_changes_when_headers_change():
    a = rw.fingerprint_of(200, "https://x/law", '"a"', "D1", "10")
    b = rw.fingerprint_of(200, "https://x/law", '"b"', "D1", "10")
    assert a != b


def test_fingerprint_stable_for_same_headers():
    assert (rw.fingerprint_of(200, "https://x/law", '"a"', "D1", "10") ==
            rw.fingerprint_of(200, "https://x/law", '"a"', "D1", "10"))


def test_fingerprint_ignores_body_by_design():
    # Signature takes headers only — there is no body parameter at all.
    import inspect
    assert "body" not in inspect.signature(rw.fingerprint_of).parameters


# ── Watch targets ────────────────────────────────────────────────────────────

def test_watch_targets_include_gazette_plus_istitlaa_when_present():
    e = _entry(gazette_url="https://uqn.gov.sa/details?p=1",
               istitlaa_url="https://istitlaa.example/doc.pdf",
               sector_feed=SECTOR_URL)
    targets = rw.watch_targets(e)
    by_kind = {t["kind"]: t for t in targets}
    assert by_kind["law_page"]["confidence"] == "exact"
    assert by_kind["gazette"]["confidence"] == "exact"
    assert by_kind["istitlaa"]["confidence"] == "exact"
    assert by_kind["sector"]["confidence"] == "portal"


def test_watch_targets_skip_absent_fields_honestly():
    targets = rw.watch_targets(_entry())
    assert [t["url"] for t in targets] == [LAW_URL]


def test_watch_targets_dedupe_repeated_urls():
    targets = rw.watch_targets(_entry(sector_feed=LAW_URL))
    assert len(targets) == 1


# ── Entry states ─────────────────────────────────────────────────────────────

def test_first_seen_entry_is_new_not_suspect():
    res = rw.check_entry("t", _entry(), None,
                         probe_fn=_probe_ok, sleep_fn=_no_sleep)
    assert res["status"] == rw.STATUS_NEW


def test_identical_signals_are_ok():
    probe = _probe_ok(LAW_URL)
    prior = _prior_for({LAW_URL: probe})
    res = rw.check_entry("t", _entry(), prior,
                         probe_fn=lambda u: dict(probe, url=u), sleep_fn=_no_sleep)
    assert res["status"] == rw.STATUS_OK


def test_changed_exact_etag_is_suspect():
    prior = _prior_for({LAW_URL: _probe_ok(LAW_URL, etag='"old"')})
    res = rw.check_entry("t", _entry(), prior,
                         probe_fn=_probe_ok, sleep_fn=_no_sleep)
    assert res["status"] == rw.STATUS_SUSPECT
    assert "ETag" in res["detail"]
    assert LAW_URL in res["detail"]


def test_second_url_change_detected_not_just_first_probe():
    # Regression: v1 fingerprinted only the first successful probe.
    law_probe = _probe_ok(LAW_URL)
    sector_probe = _probe_ok(SECTOR_URL)
    prior = _prior_for({LAW_URL: law_probe, SECTOR_URL: sector_probe})

    def probe(u):
        if u == SECTOR_URL:
            return _probe_ok(u, etag='"changed"')
        return _probe_ok(u)

    entry = _entry(sector_feed=SECTOR_URL)  # sector confidence = portal
    res = rw.check_entry("t", entry, prior, probe_fn=probe, sleep_fn=_no_sleep)
    assert res["status"] == rw.STATUS_PORTAL_CHANGED
    assert SECTOR_URL in res["detail"]


def test_portal_only_change_is_not_actionable():
    law_probe = _probe_ok(LAW_URL)
    sector_probe = _probe_ok(SECTOR_URL)
    prior = _prior_for({LAW_URL: law_probe, SECTOR_URL: sector_probe})

    def probe(u):
        if u == SECTOR_URL:
            return _probe_ok(u, etag='"changed"')
        return _probe_ok(u)

    entry = _entry(sector_feed=SECTOR_URL)
    res = rw.check_entry("t", entry, prior, probe_fn=probe, sleep_fn=_no_sleep)
    s = rw.summarize([res])
    assert res["status"] == rw.STATUS_PORTAL_CHANGED
    assert s["actionable"] == []


def test_exact_change_wins_over_portal_noise():
    prior = _prior_for({LAW_URL: _probe_ok(LAW_URL, etag='"old"'),
                        SECTOR_URL: _probe_ok(SECTOR_URL, etag='"old2"')})

    def probe(u):
        return _probe_ok(u, etag='"new"')

    entry = _entry(sector_feed=SECTOR_URL)
    res = rw.check_entry("t", entry, prior, probe_fn=probe, sleep_fn=_no_sleep)
    assert res["status"] == rw.STATUS_SUSPECT
    assert "Portal-noise" in res["detail"]


def test_unreachable_does_not_claim_law_change():
    res = rw.check_entry("t", _entry(), {"urls": {LAW_URL: {"fingerprint": "x" * 32}}},
                         probe_fn=_probe_fail, sleep_fn=_no_sleep)
    assert res["status"] == rw.STATUS_UNREACHABLE
    assert "SUSPECT" not in res["status"]


def test_static_flag_does_not_change_status_or_block_baseline():
    # Regression: v1 escalated flags to NEEDS_HUMAN_REVIEW and froze the baseline.
    res = rw.check_entry("t", _entry(known_amendment_note="تعديل م/21 لعام 1447هـ"),
                         None, probe_fn=_probe_ok, sleep_fn=_no_sleep)
    assert res["status"] == rw.STATUS_NEW
    assert res["flags"] == ["تعديل م/21 لعام 1447هـ"]

    probe = _probe_ok(LAW_URL)
    prior = _prior_for({LAW_URL: probe})
    res = rw.check_entry("t", _entry(known_discrepancy_note="فرق تاريخ"),
                         prior, probe_fn=lambda u: dict(probe, url=u),
                         sleep_fn=_no_sleep)
    assert res["status"] == rw.STATUS_OK
    s = rw.summarize([res])
    assert s["actionable"] == []
    assert s["flagged"] == ["t"]


def test_rate_limit_halts_further_probes():
    calls = []

    def probe(u):
        calls.append(u)
        if len(calls) == 1:
            p = _probe_ok(u)
            p.update({"status": 429, "rate_limited": True})
            return p
        return _probe_ok(u)

    res = rw.check_entry("t", _entry(sector_feed=SECTOR_URL),
                         None, probe_fn=probe, sleep_fn=_no_sleep)
    assert any(p.get("skipped") for p in res["probes"])
    assert len(calls) == 1


# ── Offline + registry ───────────────────────────────────────────────────────

def test_offline_lists_targets_and_flags_without_status_change():
    registry = {"a": _entry(known_amendment_note="x"), "b": _entry()}
    results = rw.run_checks(registry, {"entries": {}}, offline=True)
    by_id = {r["source_id"]: r for r in results}
    assert by_id["a"]["status"] == rw.STATUS_SKIPPED
    assert by_id["a"]["flags"] == ["x"]
    assert by_id["b"]["status"] == rw.STATUS_SKIPPED
    assert by_id["a"]["targets"][0]["url"] == LAW_URL


def test_disabled_entries_are_skipped():
    registry = {"a": _entry(monitor={"enabled": False})}
    assert rw.run_checks(registry, {"entries": {}}, offline=True) == []


def test_real_registry_loads_and_has_expected_keys():
    repo = Path(__file__).parent.parent
    registry = rw.load_registry(repo / "evals" / "source-registry.json")
    for key in ("labor_law", "arbitration_law", "companies_law",
                "pdpl_exec_regs", "zatca_e_invoicing_regs"):
        assert key in registry
    # Backward-compat: original url/date values preserved for eval validator.
    assert registry["labor_law"]["url"] == \
        "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/2569bd58-299f-4318-ab93-a9a700f26cf9/1"
    assert registry["labor_law"]["date"] == "1426/08/23هـ"
    # v2.1: real gazette URL wired where documented.
    assert registry["whistleblower_law"]["gazette_url"] == \
        "https://uqn.gov.sa/details?p=24614"


def test_real_registry_offline_run_reports_five_flags_without_actionable():
    repo = Path(__file__).parent.parent
    registry = rw.load_registry(repo / "evals" / "source-registry.json")
    results = rw.run_checks(registry, {"entries": {}}, offline=True)
    assert len(results) == 20
    s = rw.summarize(results)
    assert s["actionable"] == []
    assert len(s["flagged"]) == 5


def test_whistleblower_watches_three_urls():
    repo = Path(__file__).parent.parent
    registry = rw.load_registry(repo / "evals" / "source-registry.json")
    targets = rw.watch_targets(registry["whistleblower_law"])
    kinds = sorted(t["kind"] for t in targets)
    assert kinds == ["gazette", "law_page", "sector"]


# ── Verified official links (review: monitor the law page, not the portal) ──

VERIFIED_LAW_PAGES = {
    "commercial_courts_law": "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/38334008-3b70-4c6c-b3af-aba3016a8061/1",
    "pdpl_law": "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/b7cfae89-828e-4994-b167-adaa00e37188/1",
    "competition_law": "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/e3605c0d-ef87-4cff-b5da-aa3f0102bbb4/1",
    "e_transactions_law": "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/6f509360-2c39-4358-ae2a-a9a700f2ed16/1",
    "commercial_agency_law": "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/b19a8aa6-7b50-43f0-ab8c-a9a700f1a446/1",
}

VERIFIED_GAZETTE_URLS = {
    "whistleblower_law": "https://uqn.gov.sa/details?p=24614",
    "pdpl_exec_regs": "https://uqn.gov.sa/details?p=23595",
}

# Law entries honestly remaining on portal homepages (no verified law page
# found; the bankruptcy implementing-regulation page is NOT used as a
# substitute for the law itself). Update this set when links are verified.
HONEST_PORTAL_PRIMARIES = {"bankruptcy_law", "ip_copyright_law", "legal_profession_law"}


def test_verified_law_pages_are_exact():
    repo = Path(__file__).parent.parent
    registry = rw.load_registry(repo / "evals" / "source-registry.json")
    for source_id, url in VERIFIED_LAW_PAGES.items():
        entry = registry[source_id]
        assert entry["url"] == url, source_id
        assert entry["url_confidence"] == "exact", source_id


def test_companies_law_tracks_current_boe_guid():
    # BOE rotated the Companies Law page GUID (old 10d19e91 superseded).
    # Registry and eval case must agree — validate_cases.py enforces it.
    repo = Path(__file__).parent.parent
    registry = rw.load_registry(repo / "evals" / "source-registry.json")
    url = registry["companies_law"]["url"]
    assert url == "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/a8376aea-1bc3-49d4-9027-aed900b555af/1"
    assert "10d19e91" not in url
    cases = json.loads((repo / "evals" / "cases" / "contracts-companies.json").read_text(encoding="utf-8"))
    assert cases[0]["source_url"] == url


def test_verified_gazette_urls_are_watched():
    repo = Path(__file__).parent.parent
    registry = rw.load_registry(repo / "evals" / "source-registry.json")
    for source_id, url in VERIFIED_GAZETTE_URLS.items():
        entry = registry[source_id]
        assert entry.get("gazette_url") == url, source_id
        kinds = [t["kind"] for t in rw.watch_targets(entry)]
        assert "gazette" in kinds, source_id


def test_portal_gap_is_exactly_the_documented_set():
    repo = Path(__file__).parent.parent
    registry = rw.load_registry(repo / "evals" / "source-registry.json")
    law_kinds = {"law_page"}
    portal_primaries = {
        sid for sid, e in registry.items()
        if e.get("url_confidence") == "portal"
        and any(t["kind"] in law_kinds for t in rw.watch_targets(e))
        and not any(t["kind"] in ("gazette", "istitlaa") for t in rw.watch_targets(e))
    }
    # Sector/rulebook entries (reac/saff/fifa) track named documents, not
    # Royal-Decree law pages — they are exact by nature, not part of the gap.
    assert portal_primaries == HONEST_PORTAL_PRIMARIES


# ── State + summary ──────────────────────────────────────────────────────────

def test_state_update_records_per_url_baseline_then_detects_change():
    state = {"version": 2, "entries": {}}
    res_new = rw.check_entry("t", _entry(), None,
                             probe_fn=_probe_ok, sleep_fn=_no_sleep)
    assert res_new["status"] == rw.STATUS_NEW
    state = rw.apply_state_updates(state, [res_new])
    stored = state["entries"]["t"]["urls"][LAW_URL]
    assert stored["fingerprint"] == res_new["probes"][0]["fingerprint"]

    res_ok = rw.check_entry("t", _entry(), state["entries"]["t"],
                            probe_fn=_probe_ok, sleep_fn=_no_sleep)
    assert res_ok["status"] == rw.STATUS_OK

    res_sus = rw.check_entry("t", _entry(), state["entries"]["t"],
                             probe_fn=lambda u: _probe_ok(u, etag='"changed"'),
                             sleep_fn=_no_sleep)
    assert res_sus["status"] == rw.STATUS_SUSPECT
    state = rw.apply_state_updates(state, [res_sus])
    assert state["entries"]["t"]["last_change"]


def test_old_v1_state_is_discarded_as_baseline():
    v1 = {"version": 1, "entries": {"t": {"fingerprint": "abc", "signal": {}}}}
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "state.json"
        p.write_text(json.dumps(v1), encoding="utf-8")
        loaded = rw.load_state(p)
    assert loaded == {"version": 2, "updated_at": None, "entries": {}}


def test_signals_snapshot_ignores_bookkeeping():
    # Weekly CI must tell "URL signals moved" apart from "a week passed":
    # last_seen / consecutive_unreachable churn alone must not count.
    base = {"entries": {"t": {
        "first_seen": "2026-09-04T00:00:00Z", "last_seen": "2026-09-04T00:00:00Z",
        "consecutive_unreachable": 0,
        "urls": {LAW_URL: {"fingerprint": "ab" * 16, "kind": "law_page"}}}}}
    aged = {"entries": {"t": {
        "first_seen": "2026-09-04T00:00:00Z", "last_seen": "2026-09-11T00:00:00Z",
        "consecutive_unreachable": 3,
        "urls": {LAW_URL: {"fingerprint": "ab" * 16, "kind": "law_page"}}}}}
    assert rw.signals_snapshot(base) == rw.signals_snapshot(aged)
    moved = {"entries": {"t": {"urls": {LAW_URL: {"fingerprint": "cd" * 16}}}}}
    assert rw.signals_snapshot(base) != rw.signals_snapshot(moved)


def test_summarize_actionable_only_suspect():
    results = [{"source_id": "a", "status": rw.STATUS_OK, "flags": ["x"]},
               {"source_id": "b", "status": rw.STATUS_SUSPECT, "flags": []},
               {"source_id": "c", "status": rw.STATUS_PORTAL_CHANGED, "flags": []}]
    s = rw.summarize(results)
    assert s["total"] == 3
    assert s["actionable"] == ["b"]
    assert s["flagged"] == ["a"]


def test_report_contains_flags_section_disclaimer_and_bilingual_header():
    results = [{"source_id": "a", "citation": "C", "status": rw.STATUS_OK,
                "detail": "d", "flags": ["تعديل مشتبه"]},
               {"source_id": "b", "citation": "C", "status": rw.STATUS_OK,
                "detail": "d", "flags": []}]
    md = rw.render_markdown(results, rw.summarize(results))
    assert "Regulation Watch" in md
    assert "تقرير مراقبة الأنظمة" in md
    assert "not legal advice" in md
    assert "لا يُعدّ استشارة قانونية" in md
    assert "Internal Flags" in md
    assert "report-only" in md


# ── CLI: --update-state-if-clean ─────────────────────────────────────────────

def _write_registry(tmp_path: Path, flagged: bool = False) -> Path:
    ent = {"name": "X", "decree": "م/1", "date": "1400هـ",
           "url": "https://example.gov.sa/x",
           "citation": "X (M/1)", "source_file": "",
           "review_priority": "low",
           "monitor": {"enabled": True, "signals": []}}
    if flagged:
        ent["known_amendment_note"] = "تعديل مشتبه"
    p = tmp_path / "registry.json"
    p.write_text(json.dumps({"x": ent}), encoding="utf-8")
    return p


def test_cli_flags_do_not_block_baseline_or_exit_code(tmp_path):
    # Regression for the weekly-freeze bug: static flags must not yield
    # exit 1 and must not prevent --update-state-if-clean.
    reg = _write_registry(tmp_path, flagged=True)
    state = tmp_path / "state.json"
    code = rw.main(["--offline", "--registry", str(reg), "--state", str(state),
                    "--update-state-if-clean", "--json"])
    assert code == 0
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["entries"]["x"]["last_seen"]
