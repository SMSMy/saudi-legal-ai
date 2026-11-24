"""Phase C: relevance gate (C1), decisive-summary merge (C2a), did-you-mean (C2b).

C1: a verbatim quote survives only when the summary top-1 section (human-written
topical prose, majority term agreement >= 0.5) names its article number.
Otherwise the pool falls back to the summary path: no unrelated official quotes.
C2a: a confident decisive summary section rides along AFTER the quotes.
C2b: unknown source_id suggests the closest registered source.
"""
from saudi_legal_mcp.tools.reasoning import search_legal_provision
from saudi_legal_mcp.tools.sources import read_source

HIJACK_ARTICLES = {"85", "11", "13", "14", "21", "50"}

VAGUE_QUERIES = [
    "ما مدة عدم سماع الدعوى التجارية العامة",
    "المدة العامة لعدم سماع الدعوى التجارية",
    "مدة عدم سماع الدعوى التجارية",
]


def test_vague_limitation_queries_yield_no_unrelated_quotes():
    """Reported Q6-set2 failure: vague queries quoted arts 85/11/13 as official.
    After C1, no unrelated verbatim quote may appear."""
    for query in VAGUE_QUERIES:
        result = search_legal_provision(query, "commercial-courts")
        quoted = [q.get("article") for q in result.get("quotes", [])]
        assert not (set(quoted) & HIJACK_ARTICLES), (
            f"{query!r}: hijacked quotes {quoted}"
        )
        assert result.get("retrieval_scope") != "verbatim_corpus" or "24" in quoted, (
            f"{query!r}: verbatim scope without the anchored article"
        )


def test_hint_anchored_quote_survives_alone():
    """'المادة 24 خمس سنوات' keeps ONLY the corroborated quote; 21/50 dropped."""
    result = search_legal_provision("المادة 24 خمس سنوات", "commercial-courts")
    quoted = [q.get("article") for q in result.get("quotes", [])]
    assert quoted == ["24"], f"expected anchored ['24'], got {quoted}"
    assert result.get("dropped_unanchored_quotes") == ["21", "50"]
    assert result.get("summary_supplement") is True


def test_civil_golden_query_untouched_by_gate():
    """Gate-inactivity pin: the civil golden query has no topical summary
    majority (top-1 conf 0.45), so keyword recall must be preserved verbatim."""
    result = search_legal_provision(
        "متى لا تسمع الدعوى على المنكر في الحقوق بعد عشر سنوات ومتى ينقضي الحق بالتقادم المدني",
        "civil-transactions-law",
    )
    top = [s.get("article") for s in result.get("matched_sections", [])][:3]
    assert "295" in top
    assert not ({"31", "120", "144"} & set(top))
    assert result.get("dropped_unanchored_quotes", []) == []
    assert result.get("summary_supplement", False) is False


def test_merge_rule_decisive_summary_rides_along():
    """Reported Q7 displacement: art-156 quote alone never says 'no minimum'.
    After C2a the decisive LLC summary section rides along, both labeled."""
    result = search_legal_provision(
        "هل يوجد حد أدنى لرأس مال الشركة ذات المسؤولية المحدودة",
        "companies-law",
    )
    quoted = [q.get("article") for q in result.get("quotes", [])]
    assert "156" in quoted
    assert result.get("summary_supplement") is True
    origins = [s.get("text_origin") for s in result.get("matched_sections", [])]
    assert "hand_written_summary" in origins
    assert "official_verbatim" in origins
    bodies = " ".join(s.get("body", "") for s in result.get("matched_sections", []))
    assert "حد أدنى" in bodies


def test_unknown_source_id_suggests_correction():
    """Q4-UX: the pdpl-exec-regulations FILE stem is not a source_id;
    the error must suggest pdpl instead of dead-ending."""
    for call in (
        lambda: search_legal_provision("تسرب", "pdpl-exec-regulations"),
        lambda: read_source("pdpl-exec-regulations"),
    ):
        result = call()
        assert "error" in result
        assert result.get("did_you_mean") == ["pdpl"], result
        assert "pdpl" in result.get("valid_options", [])
