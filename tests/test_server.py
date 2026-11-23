"""
test_server.py — MCP tool registration regression tests.

Lesson (2026-08-12): build_legal_brief and find_legal_provision were
fully implemented in tools/reasoning.py since v0.3 but NEVER registered
as MCP tools — real OpenClaw agents had only 7 tools for the entire
project lifetime.  These tests lock the registration so dead-code
regression is impossible to miss again.
"""
import asyncio

import pytest

EXPECTED_TOOL_NAMES = {
    "get_legal_skill",
    "get_regulation_source",
    "get_legal_context",
    "search_contract_risks",
    "list_legal_domains",
    "get_source_status",
    "report_source_issue",
    "search_legal_provision",   # v0.4.6 — was dead code
    "get_legal_brief",          # v0.4.6 — was dead code
}


@pytest.fixture(scope="module")
def registered_tools() -> list[str]:
    from saudi_legal_mcp.server import mcp
    tools = asyncio.run(mcp.list_tools())
    return [t.name for t in tools]


def test_nine_tools_registered(registered_tools):
    names = set(registered_tools)
    missing = EXPECTED_TOOL_NAMES - names
    assert not missing, (
        f"Registered tools missing: {sorted(missing)}. "
        "Dead-code regression: tools exist in tools/*.py but are not "
        "exposed via @mcp.tool() in server.py."
    )
    assert len(names) == len(EXPECTED_TOOL_NAMES), (
        f"Unexpected extra tools: {sorted(names - EXPECTED_TOOL_NAMES)}"
    )


def test_search_legal_provision_confidence_gate():
    """v0.4.7: weak sections (conf < 0.7) must be excluded, not warned."""
    from saudi_legal_mcp.server import search_legal_provision

    result = search_legal_provision(
        query="المهل الزمنية اعتراض الدائنين",
        source_id="bankruptcy-law",
    )
    if result.get("insufficient_evidence"):
        return  # acceptable outcome — gate may refuse everything

    for s in result.get("matched_sections", []):
        assert s["match_confidence"] >= 0.7, (
            f"Section below threshold leaked through the gate: "
            f"conf={s['match_confidence']}, heading={s['heading']}"
        )
    assert "excluded_low_confidence_count" in result



def test_list_legal_domains_reports_provenance_distribution_not_verified_count():
    """Wave 1: verified_count was a false maturity gate.  The tool now reports
    the actual link/provenance mix."""
    from saudi_legal_mcp.server import list_legal_domains

    result = list_legal_domains()
    assert "verified_count" not in result
    distribution = result["provenance_distribution"]
    assert set(distribution) == {
        "unlinked",
        "linked_portal",
        "linked_document",
        "fetched_official",
        "article_level",
    }
    assert sum(distribution.values()) == result["regulation_count"]
    assert result["corpus_sources"] == [
        "civil-transactions-law",
        "labor-law",
        "pdpl",
    ]
    coverage = result["corpus_coverage"]
    assert coverage["labor-law"]["article_count"] == 245
    assert coverage["civil-transactions-law"]["article_count"] == 721
    assert coverage["pdpl"]["article_count"] == 43 + 38
    # pdpl must not be displayed as one ambiguous number: per-file split.
    files = result["corpus_files"]
    assert files["pdpl"]["article_count"] == 43
    assert files["pdpl-exec-regulations"]["article_count"] == 38
    assert files["labor-law"]["article_count"] == 245
    assert files["civil-transactions-law"]["article_count"] == 721

    labor = result["provenance_by_source"]["labor-law"]
    assert labor["dominant_provenance_level"] == "fetched_official"
    assert labor["provenance_levels"]["article_level"] == coverage["labor-law"]["article_url_count"]
    assert labor["provenance_levels"]["fetched_official"] > labor["provenance_levels"]["article_level"]
    assert "provenance_level" not in labor
    assert result["article_level_articles"] == 3


def test_server_search_tool_returns_verbatim_corpus_quote():
    """The registered tool, not only the internal function, must return the
    verbatim article and its document link."""
    from saudi_legal_mcp.server import search_legal_provision

    result = search_legal_provision("مكافأة نهاية الخدمة", "labor-law")
    assert result["insufficient_evidence"] is False
    assert result["retrieval_scope"] == "verbatim_corpus"
    article_84 = [q for q in result["quotes"] if q["article"] == "84"]
    assert article_84
    assert article_84[0]["text_origin"] == "official_verbatim"
    assert article_84[0]["fetched_at"]
    assert "laws.boe.gov.sa" in result["answer_markdown"]


def test_instructions_carry_drafting_rules_contract():
    """The four drafting rules must be delivered in the default
    instructions (empirically proven to reach clients via the MCP
    initialize handshake).  Guards the discovery-#5 contract."""
    from saudi_legal_mcp.server import mcp
    instr = mcp.instructions or ""
    assert "DRAFTING RULES" in instr
    assert "معلومة عامة خارج قاعدة المعرفة الموثَّقة" in instr
    assert "غير موثَّق" in instr
    assert "citation_note" in instr
    assert "insufficient_evidence" in instr
    # context-bloat guard: default guidance stays compact
    assert len(instr) < 2000, f"instructions grew too large: {len(instr)}"



def test_answer_drafting_rules_present_in_tool_docstrings():
    """v0.4.15 guard: OpenClaw surfaces tool descriptions to the model
    (empirically verified), NOT the MCP instructions field.  The four
    drafting rules must therefore live in the docstrings of every
    text-producing tool — deletion from any of them fails this test."""
    from saudi_legal_mcp import server
    required_tools = {
        "get_regulation_source",
        "search_legal_provision",
        "get_legal_brief",
    }
    markers = (
        "DRAFTING RULES",
        "معلومة عامة خارج قاعدة المعرفة الموثَّقة",
        "غير موثَّق",
        "citation_note",
        "insufficient_evidence",
    )
    for name in required_tools:
        fn = getattr(server, name, None)
        assert fn is not None, f"tool {name} not found in server module"
        doc = fn.__doc__ or ""
        missing = [m for m in markers if m not in doc]
        assert not missing, (
            f"{name} docstring missing drafting-rule markers: {missing}"
        )
