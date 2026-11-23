"""
test_phase_a.py — Phase A acceptance (plan 9, المرحلة أ).

Covers:
  1. text_status tagging for amended rows + no official quoting of 53/75.
  2. Unified ranking (3.2): 295/296/297 top-3, no 31/120/144 hijack.
  3. Commercial courts م24 summary + build_legal_brief gate.
  4. Skill-alone abstention gate.

Golden values below are TEMPORARY until a licensed reviewer confirms them
(plan 2.4/7); they are used for negative testing (reject the old) rather
than proving the new operative text.
"""
from __future__ import annotations

from saudi_legal_mcp.tools.corpus import get_article, iter_articles, search_articles
from saudi_legal_mcp.tools.reasoning import (
    build_legal_brief,
    find_legal_provision,
    search_legal_provision,
)


# ── 1. text_status tagging + negative quoting (53/75) ───────────────────────

def test_labor_53_tagged_and_stale():
    a = get_article("labor-law", "53")
    assert a is not None
    assert a.get("status") == "amended"
    assert a.get("text_status") == "base_not_operative"
    assert "تسعين يوم" in a.get("text", "")
    assert a.get("amendment_history")


def test_labor_75_tagged_and_stale():
    a = get_article("labor-law", "75")
    assert a is not None
    assert a.get("status") == "amended"
    assert a.get("text_status") == "base_not_operative"
    assert a.get("amendment_history")


def test_stale_53_75_never_quoted_as_operative():
    """The old 90-day / 30-15 texts must never appear as operative quotes."""
    for query in (
        "ما الحد الأقصى لفترة التجربة في نظام العمل",
        "كم مدة إشعار إنهاء عقد العمل غير محدد المدة",
    ):
        result = search_legal_provision(query, "labor-law")
        for quote in result.get("quotes", []):
            assert quote.get("article") not in ("53", "75"), (
                f"stale article {quote.get('article')} quoted as operative"
            )
            assert quote.get("text_status") != "base_not_operative"
        # Direct hinted search must also exclude them.
        hinted = search_articles(query, "labor-law", limit=3, article_hints=["53", "75"])
        assert [a.get("article") for a in hinted if a.get("article") in ("53", "75")] == []


def test_all_amended_rows_are_tagged_base_not_operative():
    for source_id in ("labor-law", "pdpl"):
        for article in iter_articles(source_id):
            if article.get("status") == "amended":
                assert article.get("text_status") == "base_not_operative", (
                    f"{source_id} art-{article.get('article')}"
                )
            elif article.get("status") in ("in_force", "added"):
                assert article.get("text_status") == "operative", (
                    f"{source_id} art-{article.get('article')}"
                )


# ── 2. Unified ranking (plan 3.2/3.3) ───────────────────────────────────────

def test_added_articles_have_no_later_amendment():
    """Q1 guard (review): an added row is operative only while its history
    holds no later-dated operation.  All recorded ops must share a single
    decree date (audited 2026-11-23: labor 11/131/233/234/235/242 each carry
    one addition decree only).  A future ingest that appends a later-dated
    op to an added row fails loudly here instead of silently quoting stale
    text as operative."""
    from saudi_legal_mcp.tools.corpus import load_corpus_file
    for stem in ("labor-law", "pdpl"):
        corpus = load_corpus_file(stem)
        assert corpus, stem
        for article in corpus.get("articles", []):
            if article.get("status") == "added":
                dates = {i.get("date") for i in article.get("amendment_instruments", [])}
                assert len(dates) <= 1, (
                    f"{stem} art-{article.get('article')}: ops span {sorted(dates)} — "
                    "retag base_not_operative"
                )


def test_civil_template_query_returns_295_296_297():
    """Shared limitation template must rank the whole section first."""
    query = "لا تسمع الدعوى على المنكر بانقضاء"
    got = [a.get("article") for a in search_articles(query, "civil-transactions-law", limit=3)]
    assert got == ["295", "296", "297"]


def test_civil_ten_year_query_has_295_and_no_hint_hijack():
    """Reported failure: hints 31/120/144 occupied all seats (limit=3)."""
    query = "متى لا تسمع الدعوى على المنكر في الحقوق بعد عشر سنوات ومتى ينقضي الحق بالتقادم المدني"
    result = search_legal_provision(query, "civil-transactions-law")
    top = [s.get("article") for s in result.get("matched_sections", [])][:3]
    assert "295" in top
    assert not {"31", "120", "144"} & set(top)


def test_commercial_courts_ranking_not_structure_only():
    """A limitation query must surface the م24 section, not court structure."""
    result = find_legal_provision("مدة عدم سماع الدعوى التجارية", "commercial-courts")
    assert result.get("insufficient_evidence") is False
    bodies = " ".join(s.get("body", "") for s in result.get("matched_sections", []))
    assert "خمس" in bodies


# ── 3. م24 summary + brief gate (plan 4.3/5) ────────────────────────────────

def test_commercial_m24_summary_is_hand_written_not_verbatim():
    result = find_legal_provision("مدة عدم سماع الدعوى التجارية خمس سنوات", "commercial-courts")
    assert result.get("insufficient_evidence") is False
    assert result.get("text_origin") == "hand_written_summary"
    assert result.get("quotes") == []
    bodies = " ".join(s.get("body", "") for s in result.get("matched_sections", []))
    assert "خمس سنوات" in bodies
    assert "المادة 24" in bodies or "مادة 24" in bodies
    assert "إقرار" in bodies or "عذر" in bodies
    for section in result.get("matched_sections", []):
        assert section.get("text_origin") == "hand_written_summary"


def test_build_legal_brief_commercial_gives_five_years_or_abstains():
    result = build_legal_brief(
        scenario="ما مدة عدم سماع الدعوى التجارية من تاريخ نشوء الحق؟",
        domain="commercial-dispute",
        source_id="commercial-courts",
    )
    if result.get("insufficient_evidence"):
        assert result.get("brief") is None
    else:
        brief = result.get("brief") or ""
        assert "خمس" in brief
        assert "إقرار" in brief or "عذر" in brief


def test_stale_wins_falls_back_to_summary_with_notice():
    """Plan §1.4/§2.3: stale 53 outscores every quotable row → the corpus
    cannot answer.  Fall back to the summary (the record) with an amendment
    notice — never weak operative excerpts, never the old text as operative."""
    result = search_legal_provision(
        "ما الحد الأقصى لفترة التجربة في نظام العمل؟", "labor-law"
    )
    assert result.get("retrieval_scope") == "summary_after_stale_fallback"
    notices = result.get("amendment_notices", [])
    assert [n.get("article") for n in notices] and "53" in [n.get("article") for n in notices]
    assert [q.get("article") for q in result.get("quotes", [])] == []
    bodies = " ".join(s.get("body", "") for s in result.get("matched_sections", []))
    assert "180" in bodies  # the record (م/44 rule) is shown
    # The old number may still appear inside the explanatory record/notice —
    # what must never happen is quoting it as an operative official text
    # (asserted above via quotes == [] and scope != verbatim_corpus).


def test_notice_query_falls_back_with_notice_75():
    result = search_legal_provision(
        "ما مدة إشعار إنهاء العقد غير محدد المدة إذا كان الأجر شهريًا؟",
        "labor-law",
    )
    assert result.get("retrieval_scope") == "summary_after_stale_fallback"
    assert "75" in [n.get("article") for n in result.get("amendment_notices", [])]
    assert [q.get("article") for q in result.get("quotes", [])] == []


def test_tie_keeps_corpus_without_notices():
    """EOSB: stale 54 ties operative best (3=3) → corpus kept, 84 quoted."""
    result = search_legal_provision("كيف تحسب مكافأة نهاية الخدمة؟", "labor-law")
    assert result.get("retrieval_scope") == "verbatim_corpus"
    assert "84" in [q.get("article") for q in result.get("quotes", [])]
    assert result.get("amendment_notices", []) == []


def test_brief_carries_amendment_notice_not_stale_quote():
    result = build_legal_brief(
        scenario="ما الحد الأقصى لفترة التجربة في نظام العمل؟",
        domain="labor-law-analysis",
        source_id="labor-law",
    )
    assert result.get("insufficient_evidence") is False
    assert "53" in [n.get("article") for n in result.get("amendment_notices", [])]
    brief = result.get("brief") or ""
    assert "تنبيه تعديل" in brief
    # No operative quote anywhere in the fallback brief (the old number may
    # still appear inside the explanatory record/notice — never as a quote).
    assert "اقتباس رسمي حرفي" not in brief
    assert "180" in brief


def test_skill_alone_does_not_cancel_statutory_insufficient():
    """Plan 4.2: generic skill text is not evidence for a statutory ruling."""
    result = build_legal_brief(
        scenario="xyzxyz123 zzz",
        domain="labor-law-analysis",
        source_id="labor-law",
    )
    assert result.get("insufficient_evidence") is True
    assert result.get("brief") is None
