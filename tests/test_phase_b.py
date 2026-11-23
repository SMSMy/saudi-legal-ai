"""
test_phase_b.py — Phase B acceptance (plan §2/§7/§9-ب).

Covers the structured amendments[] model + v1 composition:
  - schema, ordering, and per-article outcomes for 53/74/75/107 + PDPL-4;
  - v1 rules: article-scope chains compose to a *candidate* (still
    needs_review — never verified, never quoted); paragraph/insert,
    lexical, restructure, cancel and renumber rows are explicitly
    withheld (needs_review) or refused (failed);
  - typo display fixes never touch text/sha256 (§2.5);
  - golden values stay TEMPORARY until licensed review.
"""
from __future__ import annotations

import hashlib

from saudi_legal_mcp.tools.amendments import compose
from saudi_legal_mcp.tools.corpus import (
    article_record,
    get_article,
    iter_articles,
    load_corpus_file,
)
from saudi_legal_mcp.tools.reasoning import search_legal_provision


def _law(num: str) -> dict:
    a = get_article("labor-law", num)
    assert a is not None
    return a


def _ops(article: dict) -> list[dict]:
    ops = article.get("amendments") or []
    assert ops, f"art-{article.get('article')}: amendments[] must be non-empty"
    return ops


def test_amendments_schema_and_fields():
    required = {
        "op_id", "scope", "target", "op", "insert_after", "quoted_text",
        "instrument", "issued_on_hijri", "issued_on_iso",
        "effective_on_hijri", "effective_on_iso", "effective_order",
        "parse_status",
    }
    for stem in ("labor-law", "pdpl"):
        corpus = load_corpus_file(stem)
        assert corpus, stem
        for article in corpus.get("articles", []):
            if article.get("status") != "amended":
                continue
            for op in _ops(article):
                missing = required - set(op.keys())
                assert not missing, f"{stem} art-{article.get('article')}: {missing}"
                assert op["parse_status"] in ("validated", "needs_review", "failed")


def test_ops_ordered_by_effective_date():
    for num in ("53", "75", "74"):
        ops = _ops(_law(num))
        keys = [(o.get("effective_on_iso") or "9999", o.get("effective_order", 0)) for o in ops]
        assert keys == sorted(keys), f"art-{num}: ops not in effective order"


def test_53_two_validated_article_replaces_with_correct_dates():
    ops = _ops(_law("53"))
    assert [(o["scope"], o["op"], o["parse_status"]) for o in ops] == [
        ("article", "replace", "validated"),
        ("article", "replace", "validated"),
    ]
    assert ops[0]["instrument"] == "م/46" and ops[0]["effective_on_iso"] == "2015-03-26"
    assert ops[1]["instrument"] == "م/44" and ops[1]["effective_on_iso"] == "2025-02-19"


def test_53_consolidated_candidate_temporary():
    a = _law("53")
    assert a["consolidation_status"] == "needs_review"
    assert a["consolidation_method"] == "consolidated_from_instruments"
    text = a["consolidated_text"]
    assert text and "مائة وثمانين" in text  # temporary golden content
    assert text.strip() != (a["text"] or "").strip()
    assert a["consolidation_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_75_consolidated_candidate_temporary():
    a = _law("75")
    assert a["consolidation_status"] == "needs_review"
    text = a["consolidated_text"]
    assert text and "ستين" in text and "ثلاثين" in text  # temporary golden content
    assert a["consolidation_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_107_paragraph_replace_withheld_explicitly():
    a = _law("107")
    ops = _ops(a)
    assert any(
        o["scope"] == "paragraph" and o["op"] == "replace" and o["target"] == "1"
        and o["parse_status"] == "validated"
        for o in ops
    ), [ (o["scope"], o["op"], o.get("target")) for o in ops ]
    assert a["consolidation_status"] == "needs_review"
    assert a["consolidated_text"] is None
    assert "الفقرة" in (a["consolidation_note"] or "")


def test_74_mixed_ops_withheld_with_mkr_targets():
    a = _law("74")
    ops = _ops(a)
    para4 = [o for o in ops if o.get("target") == "4" and o["scope"] == "paragraph"]
    assert para4 and para4[0]["instrument"] == "م/134"
    assert para4[0]["effective_on_iso"] == "2019-07-30"
    mkrs = sorted(o.get("target") for o in ops if "مكرر" in str(o.get("target")))
    assert mkrs == ["3 مكرر", "7 مكرر"]
    assert a["consolidation_status"] == "needs_review"
    assert a["consolidated_text"] is None


def test_pdpl4_single_article_replace_candidate():
    corpus = load_corpus_file("pdpl")
    a = next(x for x in corpus["articles"] if str(x.get("article")) == "4")
    ops = _ops(a)
    assert len(ops) == 1
    assert (ops[0]["scope"], ops[0]["op"], ops[0]["parse_status"]) == (
        "article", "replace", "validated",
    )
    assert ops[0]["instrument"] == "م/148"
    assert a["consolidation_status"] == "needs_review"
    assert a["consolidated_text"] and "الحق في العلم" in a["consolidated_text"]


def test_no_verified_status_in_v1():
    for stem in ("labor-law", "pdpl"):
        corpus = load_corpus_file(stem)
        for article in corpus.get("articles", []):
            assert article.get("consolidation_status") in (
                "needs_review", "failed", "not_required",
            ), f"{stem} art-{article.get('article')}"
            if article.get("consolidation_status") != "needs_review":
                assert article.get("consolidated_text") is None


def test_in_force_rows_need_no_consolidation():
    a = get_article("labor-law", "84")
    assert a is not None
    assert a["consolidation_status"] == "not_required"
    assert a["consolidated_text"] is None


def test_restructure_rows_refuse_explicitly():
    for num in ("12", "13", "14"):
        a = _law(num)
        assert a["consolidation_status"] in ("needs_review", "failed")
        assert a["consolidated_text"] is None
        assert any(o.get("target") == "restructure" for o in _ops(a)), num


def test_cancel_rows_withheld_not_composed():
    corpus = load_corpus_file("pdpl")
    a32 = next(x for x in corpus["articles"] if str(x.get("article")) == "32")
    assert any(o.get("op") == "cancel" for o in _ops(a32))
    assert a32["consolidation_status"] == "needs_review"
    assert a32["consolidated_text"] is None


def test_quotes_carry_ops_but_never_composed_text():
    for num in ("53", "75", "107", "74"):
        rec = article_record(_law(num))
        assert rec["is_operative"] is False
        assert rec["amendments"], num
        assert "consolidated_text" not in rec
        assert rec["consolidation_status"] == "needs_review"


def test_stale_still_never_quoted_with_model_present():
    result = search_legal_provision("ما الحد الأقصى لفترة التجربة؟", "labor-law")
    assert [q.get("article") for q in result.get("quotes", [])] == []
    assert "53" in [n.get("article") for n in result.get("amendment_notices", [])]


def test_typo_display_fix_never_touches_text_or_sha():
    a = _law("234")
    assert a.get("display_text") and a.get("display_note")
    assert "شهرًا" in a["display_text"]
    assert "شهاً" not in a["display_text"]
    assert a["display_text"] != a["text"]
    assert (
        hashlib.sha256(a["text"].encode("utf-8")).hexdigest() == a["sha256"]
    )


def test_effective_not_before_issued_where_both_known():
    for stem in ("labor-law", "pdpl"):
        corpus = load_corpus_file(stem)
        for article in corpus.get("articles", []):
            for op in article.get("amendments", []):
                iso_e, iso_i = op.get("effective_on_iso"), op.get("issued_on_iso")
                if iso_e and iso_i:
                    assert iso_e >= iso_i, (
                        f"{stem} art-{article.get('article')} {op.get('op_id')}: "
                        f"effective {iso_e} < issued {iso_i}"
                    )


def test_notice_cites_structured_latest_operation():
    result = search_legal_provision("ما الحد الأقصى لفترة التجربة؟", "labor-law")
    notices = result.get("amendment_notices", [])
    n53 = next(n for n in notices if n.get("article") == "53")
    assert n53.get("operation") == "استبدال كامل للمادة"
    assert n53.get("instrument") == "م/44"
    assert n53.get("effective_on_iso") == "2025-02-19"
