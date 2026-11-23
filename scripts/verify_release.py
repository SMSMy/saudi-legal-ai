"""
verify_release.py — Legal Release Gate (v0.4.12).

Single command that runs the release checks in order and stops at the
first failure:

  1. generate_manifests.py --check   (stale manifests = hard failure)
  2. validate_manifests.py           (SHA/legal-field validation)
  3. pytest tests/ -q                (must stay green; count must not drop)
  4. eval_runner.py                  (metrics compared against the last
                                      canonical baseline — a drop beyond
                                      the tolerance prints a clear warning)

Usage:
  python scripts/verify_release.py

Exit codes:
  0 = all checks passed (warnings allowed)
  1 = a hard gate failed
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Canonical baseline: the last versioned eval snapshot.  Do NOT point
# this at per-run artifacts — see .gitignore's baseline rules.
BASELINE_PATH = REPO_ROOT / "evals" / "metrics" / "results" / "baseline_v04_7_fullcover.json"

# Relative drop (fraction) beyond which a clear warning is printed.
# 0.01 = 1% — warning threshold, NOT a hard failure (the first three
# gates are the hard ones).  Rationale: eval metrics are deterministic
# per code state (no sampling) — run-to-run noise is zero, observed
# repeatedly across sessions (0.8306→0.8306).  1% leaves room for
# intentional source edits that legitimately move recall a little,
# while any real regression screams.
METRIC_DROP_TOLERANCE = 0.01


def _run(step_name: str, cmd: list[str], cwd: Path) -> int:
    print(f"\n[{step_name}] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    if result.returncode != 0:
        print(f"[verify_release] FAILED at step: {step_name}", file=sys.stderr)
        sys.exit(1)
    return result.returncode


def _run_golden_cases() -> None:
    """Phase A golden cases — TEMPORARY until a licensed reviewer confirms
    them (plan 2.4/7).  Used for negative testing (reject the old stale text)
    rather than proving a new operative text.  Any failure is a hard gate
    (sys.exit(1) — the release fails, it is never a warning).

    Coverage note (review Q3): the canonical eval (eval_runner) goes through
    find_legal_provision with prefer_corpus=False — the hand-written summary
    path only — so blocking amended corpus rows cannot move its numbers.
    These golden cases are therefore the ONLY automated evidence for the
    stale-text fix, not the eval metrics.
    """
    import os

    os.environ.setdefault("REPO_PATH", str(REPO_ROOT / "saudi_legal_mcp" / "data"))
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from saudi_legal_mcp.tools.corpus import get_article, load_corpus_file, search_articles
    from saudi_legal_mcp.tools.reasoning import (
        build_legal_brief,
        find_legal_provision,
        search_legal_provision,
    )

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            failures.append(f"{name}: {detail}")

    # — P0: stale bases are tagged and never quoted as in-force —
    for number in ("53", "75", "107", "74"):
        article = get_article("labor-law", number)
        check(
            f"labor-{number} tagged base_not_operative",
            article is not None and article.get("text_status") == "base_not_operative",
            f"got {None if article is None else article.get('text_status')}",
        )
    pdpl_law = load_corpus_file("pdpl") or {}
    pdpl4 = next(
        (a for a in pdpl_law.get("articles", []) if str(a.get("article")) == "4"),
        None,
    )
    check(
        "pdpl-4 tagged base_not_operative",
        pdpl4 is not None and pdpl4.get("text_status") == "base_not_operative",
        f"got {None if pdpl4 is None else pdpl4.get('text_status')}",
    )
    # Positive control: in-force rows stay quotable (no over-blocking).
    labor84 = get_article("labor-law", "84")
    check(
        "labor-84 stays operative",
        labor84 is not None and labor84.get("text_status") == "operative",
        f"got {None if labor84 is None else labor84.get('text_status')}",
    )

    # — B1/B2 model (plan §2): structured ops + v1 composition outcomes —
    labor53 = get_article("labor-law", "53")
    check(
        "labor-53 two validated article ops ordered م/46 then م/44",
        labor53 is not None and [
            (o.get("scope"), o.get("op"), o.get("parse_status"), o.get("instrument"))
            for o in labor53.get("amendments", [])
        ] == [
            ("article", "replace", "validated", "م/46"),
            ("article", "replace", "validated", "م/44"),
        ],
        f"got {None if labor53 is None else labor53.get('amendments')}",
    )
    check(
        "labor-53 consolidated candidate (temporary) with methodology",
        labor53 is not None
        and labor53.get("consolidation_status") == "needs_review"
        and labor53.get("consolidation_method") == "consolidated_from_instruments"
        and bool(labor53.get("consolidated_text"))
        and "مائة وثمانين" in (labor53.get("consolidated_text") or ""),
        f"status={None if labor53 is None else labor53.get('consolidation_status')}",
    )
    labor107 = get_article("labor-law", "107")
    check(
        "labor-107 paragraph op withheld explicitly (v1: no paragraph auto-compose)",
        labor107 is not None
        and labor107.get("consolidation_status") == "needs_review"
        and labor107.get("consolidated_text") is None,
        f"got {None if labor107 is None else (labor107.get('consolidation_status'), bool(labor107.get('consolidated_text')))}",
    )
    labor74 = get_article("labor-law", "74")
    check(
        "labor-74 mixed ops withheld with مكرر targets recorded",
        labor74 is not None
        and labor74.get("consolidation_status") == "needs_review"
        and labor74.get("consolidated_text") is None
        and sorted(
            o.get("target") for o in labor74.get("amendments", []) if "مكرر" in str(o.get("target"))
        ) == ["3 مكرر", "7 مكرر"],
        f"got {None if labor74 is None else ([o.get('target') for o in labor74.get('amendments', [])], labor74.get('consolidation_status'))}",
    )
    check(
        "v1 never marks verified (licensed review or resync only)",
        all(
            a.get("consolidation_status") in ("needs_review", "failed", "not_required")
            for stem in ("labor-law", "pdpl", "civil-transactions-law", "pdpl-exec-regulations")
            for a in (load_corpus_file(stem) or {}).get("articles", [])
        ),
        "a verified status slipped into v1 data",
    )

    for query in (
        "ما الحد الأقصى لفترة التجربة في نظام العمل",
        "كم مدة إشعار إنهاء عقد العمل غير محدد المدة",
    ):
        result = search_legal_provision(query, "labor-law")
        quoted = [q.get("article") for q in result.get("quotes", [])]
        check(
            f"53/75 not quoted for {query[:20]}…",
            not ({"53", "75"} & set(quoted)),
            f"quoted={quoted}",
        )

    # Phase A stale-wins gate: stale outscores quotable → summary + notice.
    for query, number in (
        ("ما الحد الأقصى لفترة التجربة في نظام العمل؟", "53"),
        ("ما مدة إشعار إنهاء العقد غير محدد المدة إذا كان الأجر شهريًا؟", "75"),
    ):
        result = search_legal_provision(query, "labor-law")
        check(
            f"stale-wins fallback for {number}",
            result.get("retrieval_scope") == "summary_after_stale_fallback"
            and number in [n.get("article") for n in result.get("amendment_notices", [])],
            f"scope={result.get('retrieval_scope')} notices={[n.get('article') for n in result.get('amendment_notices', [])]}",
        )

    # — P0 ranking (plan 3.3): template + reported 10-year failure —
    template = [a.get("article") for a in search_articles(
        "لا تسمع الدعوى على المنكر بانقضاء",
        "civil-transactions-law",
        limit=3,
    )]
    check("civil template ranks 295/296/297", template == ["295", "296", "297"], f"got={template}")

    ten_year = search_legal_provision(
        "متى لا تسمع الدعوى على المنكر في الحقوق بعد عشر سنوات ومتى ينقضي الحق بالتقادم المدني",
        "civil-transactions-law",
    )
    top3 = [s.get("article") for s in ten_year.get("matched_sections", [])][:3]
    check("civil 10-year has 295 in top-3", "295" in top3, f"top3={top3}")
    check("civil 10-year has no 31/120/144 hijack", not ({"31", "120", "144"} & set(top3)), f"top3={top3}")

    # — P0 brief (plan 4.3): commercial 5-year rule or explicit abstention —
    summary = find_legal_provision("مدة عدم سماع الدعوى التجارية", "commercial-courts")
    bodies = " ".join(s.get("body", "") for s in summary.get("matched_sections", []))
    check("commercial م24 summary present", "خمس" in bodies, "missing خمس سنوات")
    check(
        "commercial م24 summary is hand-written",
        summary.get("text_origin") == "hand_written_summary" and summary.get("quotes") == [],
        f"origin={summary.get('text_origin')}",
    )
    brief = build_legal_brief(
        scenario="ما مدة عدم سماع الدعوى التجارية من تاريخ نشوء الحق؟",
        domain="commercial-dispute",
        source_id="commercial-courts",
    )
    if brief.get("insufficient_evidence"):
        check("commercial brief abstains cleanly", brief.get("brief") is None, "abstain must have no brief")
    else:
        text = brief.get("brief") or ""
        check("commercial brief gives 5-year rule", "خمس" in text, "missing خمس")
        check(
            "commercial brief gives exception",
            "إقرار" in text or "عذر" in text,
            "missing إقرار/عذر",
        )

    if failures:
        print("\n[verify_release] GOLDEN-CASE FAILURES (temporary, until licensed review):", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        sys.exit(1)
    print("[golden] All Phase A golden cases passed (TEMPORARY — pending licensed review) [OK]")


def main() -> None:
    py = sys.executable

    # ── Gate 1: manifests stale check ────────────────────────────────────────
    _run("manifests --check", [py, "scripts/generate_manifests.py", "--check"], REPO_ROOT)

    # ── Gate 2: manifest validation ──────────────────────────────────────────
    _run("manifest validation", [py, "scripts/validate_manifests.py"], REPO_ROOT)

    # ── Gate 3: unit tests ───────────────────────────────────────────────────
    _run("pytest", [py, "-m", "pytest", "tests/", "-q", "--tb=short"], REPO_ROOT)

    # ── Gate 3.5: Phase A golden cases (temporary, until licensed review) ──
    print("\n[golden] Running Phase A golden cases ...")
    _run_golden_cases()

    # ── Gate 4: eval metrics vs canonical baseline ───────────────────────────
    print("\n[eval] Running eval_runner.py ...")
    eval_result = subprocess.run(
        [py, "evals/metrics/eval_runner.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if eval_result.returncode != 0:
        print("[verify_release] FAILED at step: eval_runner", file=sys.stderr)
        print(eval_result.stderr.strip(), file=sys.stderr)
        sys.exit(1)

    try:
        current = json.loads(eval_result.stdout)
    except (json.JSONDecodeError) as exc:
        print(f"[verify_release] Cannot parse eval_runner output: {exc}", file=sys.stderr)
        sys.exit(1)

    current_precision = current.get("citation_precision_avg")
    current_recall = current.get("source_recall_avg")

    print(
        f"[eval] current: {current.get('total_questions')} questions, "
        f"precision={current_precision}, recall={current_recall}"
    )

    if not BASELINE_PATH.exists():
        print(
            "[verify_release] WARNING: canonical baseline not found — "
            "skipping metric comparison.",
            file=sys.stderr,
        )
    else:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        base_precision = baseline.get("citation_precision_avg")
        base_recall = baseline.get("source_recall_avg")

        warnings: list[str] = []
        if base_precision is not None and current_precision is not None:
            drop = base_precision - current_precision
            if drop > METRIC_DROP_TOLERANCE:
                warnings.append(
                    f"citation_precision dropped {drop:.4f} "
                    f"({base_precision} → {current_precision}) — exceeds {METRIC_DROP_TOLERANCE:.0%} tolerance"
                )
        if base_recall is not None and current_recall is not None:
            drop = base_recall - current_recall
            if drop > METRIC_DROP_TOLERANCE:
                warnings.append(
                    f"source_recall dropped {drop:.4f} "
                    f"({base_recall} → {current_recall}) — exceeds {METRIC_DROP_TOLERANCE:.0%} tolerance"
                )

        if warnings:
            print("\n[verify_release] ⚠ METRIC REGRESSION WARNING:", file=sys.stderr)
            for w in warnings:
                print(f"  - {w}", file=sys.stderr)
            print(
                "  Investigate before release — a drop beyond tolerance must be explained, not ignored.",
                file=sys.stderr,
            )
        else:
            print("[verify_release] Metrics within tolerance of canonical baseline [OK]")

    print("\n[verify_release] All release gates passed [OK]")


if __name__ == "__main__":
    main()
