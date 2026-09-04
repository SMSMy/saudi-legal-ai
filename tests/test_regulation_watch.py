# tests/test_regulation_watch.py
"""
Tests for scripts/check_regulation_updates.py
Saudi Legal AI Framework — regulation-watch (metadata-only) checker.

All network probing is mocked via injected probe_fn — no real HTTP.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import check_regulation_updates as rw


# ── Helpers ──────────────────────────────────────────────────────────────────

def _entry(**over):
    base = {
        "name": "نظام تجريبي",
        "decree": "م/99",
        "date": "1440هـ",
        "url": "https://example.gov.sa/law/99",
        "citation": "Test Law (Royal Decree M/99 1440H)",
        "source_file": "sources/test-law.md",
        "url_confidence": "exact",
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


# ── Entry states ─────────────────────────────────────────────────────────────

def test_first_seen_entry_is_new_not_suspect():
    res = rw.check_entry("t", _entry(), None,
                         probe_fn=_probe_ok, sleep_fn=_no_sleep)
    assert res["status"] == rw.STATUS_NEW


def test_identical_signal_is_ok():
    probe = _probe_ok("https://example.gov.sa/law/99")
    fp = rw.fingerprint_of(200, probe["final_url"], probe["etag"],
                           probe["last_modified"], probe["content_length"])
    prior = {"fingerprint": fp, "signal": {
        "status": 200, "final_url": probe["final_url"], "etag": probe["etag"],
        "last_modified": probe["last_modified"], "content_length": probe["content_length"]}}
    res = rw.check_entry("t", _entry(), prior,
                         probe_fn=lambda u: dict(probe, url=u), sleep_fn=_no_sleep)
    assert res["status"] == rw.STATUS_OK


def test_changed_etag_is_suspect():
    prior = {"fingerprint": "deadbeef" * 4,
             "signal": {"status": 200, "final_url": "https://example.gov.sa/law/99",
                        "etag": '"old"', "last_modified": "D1", "content_length": "10"}}
    res = rw.check_entry("t", _entry(), prior,
                         probe_fn=_probe_ok, sleep_fn=_no_sleep)
    assert res["status"] == rw.STATUS_SUSPECT
    assert "ETag" in res["detail"]


def test_unreachable_does_not_claim_law_change():
    res = rw.check_entry("t", _entry(), {"fingerprint": "x" * 32},
                         probe_fn=_probe_fail, sleep_fn=_no_sleep)
    assert res["status"] == rw.STATUS_UNREACHABLE
    assert "SUSPECT" not in res["status"]


def test_static_amendment_note_escalates_to_human_review():
    res = rw.check_entry("t", _entry(known_amendment_note="تعديل م/21 لعام 1447هـ"),
                         None, probe_fn=_probe_ok, sleep_fn=_no_sleep)
    assert res["status"] == rw.STATUS_NEEDS_REVIEW


def test_rate_limit_halts_further_probes():
    calls = []

    def probe(u):
        calls.append(u)
        if len(calls) == 1:
            p = _probe_ok(u)
            p.update({"status": 429, "rate_limited": True})
            return p
        return _probe_ok(u)

    res = rw.check_entry("t", _entry(sector_feed="https://example.gov.sa/feed"),
                         None, probe_fn=probe, sleep_fn=_no_sleep)
    assert any(p.get("skipped") for p in res["probes"])
    assert len(calls) == 1


# ── Offline + registry ───────────────────────────────────────────────────────

def test_offline_reports_static_flags_only():
    registry = {"a": _entry(known_amendment_note="x"), "b": _entry()}
    results = rw.run_checks(registry, {"entries": {}}, offline=True)
    by_id = {r["source_id"]: r for r in results}
    assert by_id["a"]["status"] == rw.STATUS_NEEDS_REVIEW
    assert by_id["b"]["status"] == rw.STATUS_SKIPPED


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


def test_real_registry_offline_run_has_five_reviews():
    repo = Path(__file__).parent.parent
    registry = rw.load_registry(repo / "evals" / "source-registry.json")
    results = rw.run_checks(registry, {"entries": {}}, offline=True)
    assert len(results) == 20
    assert sum(1 for r in results if r["status"] == rw.STATUS_NEEDS_REVIEW) == 5


# ── State + summary ──────────────────────────────────────────────────────────

def test_state_update_records_baseline_then_detects_change():
    state = {"version": 1, "entries": {}}
    res_new = rw.check_entry("t", _entry(), None,
                             probe_fn=_probe_ok, sleep_fn=_no_sleep)
    assert res_new["status"] == rw.STATUS_NEW
    state = rw.apply_state_updates(state, [res_new])
    assert state["entries"]["t"]["fingerprint"] == res_new["fingerprint"]

    res_ok = rw.check_entry("t", _entry(), state["entries"]["t"],
                            probe_fn=_probe_ok, sleep_fn=_no_sleep)
    assert res_ok["status"] == rw.STATUS_OK

    res_sus = rw.check_entry("t", _entry(), state["entries"]["t"],
                             probe_fn=lambda u: _probe_ok(u, etag='"changed"'),
                             sleep_fn=_no_sleep)
    assert res_sus["status"] == rw.STATUS_SUSPECT


def test_summarize_actionable():
    results = [{"source_id": "a", "status": rw.STATUS_OK},
               {"source_id": "b", "status": rw.STATUS_SUSPECT},
               {"source_id": "c", "status": rw.STATUS_NEEDS_REVIEW}]
    s = rw.summarize(results)
    assert s["total"] == 3
    assert sorted(s["actionable"]) == ["b", "c"]


def test_report_contains_disclaimer_and_bilingual_header():
    results = [{"source_id": "a", "citation": "C", "status": rw.STATUS_OK, "detail": "d"}]
    md = rw.render_markdown(results, rw.summarize(results))
    assert "Regulation Watch" in md
    assert "تقرير مراقبة الأنظمة" in md
    assert "does not constitute legal advice" in md or "not legal advice" in md
    assert "لا يُعدّ استشارة قانونية" in md


# ── CLI: --update-state-if-clean ─────────────────────────────────────────────

def _write_registry(tmp_path: Path) -> Path:
    reg = {"x": {"name": "X", "decree": "م/1", "date": "1400هـ",
                 "url": "https://example.gov.sa/x",
                 "citation": "X (M/1)", "source_file": "",
                 "review_priority": "low",
                 "monitor": {"enabled": True, "signals": []}}}
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(reg), encoding="utf-8")
    return p


def test_cli_update_state_if_clean_freezes_on_actionable(tmp_path):
    reg = _write_registry(tmp_path)
    state = tmp_path / "state.json"
    code = rw.main(["--offline", "--registry", str(reg), "--state", str(state),
                    "--update-state-if-clean", "--json"])
    assert code == 0  # no static flags → clean → state written
    saved = json.loads(state.read_text(encoding="utf-8"))["entries"]
    assert "x" in saved and "fingerprint" not in saved  # offline: check-in only

    reg2_data = {"x": {"name": "X", "decree": "م/1", "date": "1400هـ",
                       "url": "https://example.gov.sa/x",
                       "citation": "X (M/1)", "source_file": "",
                       "review_priority": "low",
                       "known_amendment_note": "تعديل مشتبه",
                       "monitor": {"enabled": True, "signals": []}}}
    reg.write_text(json.dumps(reg2_data), encoding="utf-8")
    code = rw.main(["--offline", "--registry", str(reg), "--state", str(state),
                    "--update-state-if-clean", "--json"])
    assert code == 1  # actionable → frozen, no crash
