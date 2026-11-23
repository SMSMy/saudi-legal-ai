"""
test_tools.py — Smoke tests for the 5 existing MCP tools.
Tests retrieval behaviour only — no external API calls, no LLM.
"""
import json
import pytest
from saudi_legal_mcp.tools.sources import read_source, VALID_REGULATIONS
from saudi_legal_mcp.tools.skills import read_skill, VALID_DOMAINS
from saudi_legal_mcp.tools.search import find_risks


# ---------------------------------------------------------------------------
# read_source
# ---------------------------------------------------------------------------

def test_read_source_metadata_only():
    """Default call returns metadata dict without full content."""
    result = read_source("labor-law")
    assert isinstance(result, dict)
    assert result["source_id"] == "labor-law"
    assert "verification_status" in result
    assert "disclaimer" in result
    # Default: include_content=False → content should be None
    assert result["content"] is None


def test_read_source_with_content():
    """include_content=True returns non-empty text."""
    result = read_source("labor-law", include_content=True)
    assert result["content"] is not None
    assert len(result["content"]) > 0


def test_read_source_content_truncation():
    """max_chars is respected."""
    result = read_source("civil-transactions-law", include_content=True, max_chars=500)
    assert result["content"] is not None
    assert len(result["content"]) <= 500
    # Large file should be truncated
    assert result["content_truncated"] is True


def test_read_source_unknown_regulation():
    """Unknown regulation returns error dict, not exception."""
    result = read_source("nonexistent-law")
    assert "error" in result
    assert "valid_options" in result


def test_read_source_all_registered():
    """All registered sources can be read without error."""
    errors = []
    for reg_id in VALID_REGULATIONS:
        result = read_source(reg_id)
        if "error" in result:
            errors.append(f"{reg_id}: {result['error']}")
    assert not errors, f"Sources that returned errors:\n" + "\n".join(errors)


# ---------------------------------------------------------------------------
# read_skill
# ---------------------------------------------------------------------------

def test_read_skill_metadata_only():
    """Default call returns metadata dict without full content."""
    result = read_skill("labor-law-analysis")
    assert isinstance(result, dict)
    assert result["domain"] == "labor-law-analysis"
    assert result["content"] is None


def test_read_skill_with_content():
    """include_content=True returns non-empty text."""
    result = read_skill("labor-law-analysis", include_content=True)
    assert result["content"] is not None
    assert len(result["content"]) > 0


def test_read_skill_unknown_domain():
    """Unknown domain returns error dict, not exception."""
    result = read_skill("nonexistent-domain")
    assert "error" in result
    assert "valid_options" in result


def test_read_skill_all_registered():
    """All registered domains can be read without error."""
    errors = []
    for domain in VALID_DOMAINS:
        result = read_skill(domain)
        if "error" in result:
            errors.append(f"{domain}: {result['error']}")
    assert not errors, f"Skills that returned errors:\n" + "\n".join(errors)


def test_sports_dispute_now_accessible():
    """sports-dispute was previously unregistered — must now be readable."""
    result = read_skill("sports-dispute")
    assert "error" not in result
    assert result["domain"] == "sports-dispute"


def test_competition_law_now_accessible():
    """competition-law was previously unregistered — must now be readable."""
    result = read_source("competition-law")
    assert "error" not in result
    assert result["source_id"] == "competition-law"


def test_zatca_now_accessible():
    """zatca-e-invoicing was previously unregistered — must now be readable."""
    result = read_source("zatca-e-invoicing")
    assert "error" not in result


def test_ip_law_now_accessible():
    """intellectual-property-law was previously unregistered — must now be readable."""
    result = read_source("intellectual-property-law")
    assert "error" not in result


# ---------------------------------------------------------------------------
# find_risks (search_contract_risks)
# ---------------------------------------------------------------------------

def test_find_risks_returns_valid_dict_structure():
    """find_risks returns a dict (not JSON string) with expected keys. v0.3 contract."""
    data = find_risks()
    assert isinstance(data, dict), "find_risks must return dict, not str"
    assert "total_found" in data
    assert "risks" in data
    assert isinstance(data["risks"], list)
    assert "disclaimer" in data
    # match_confidence is None for exact matches (no fuzzy), float only for fuzzy
    assert data.get("match_confidence") is None or isinstance(data["match_confidence"], float)


def test_find_risks_filter_by_contract_type():
    """Filtering by contract_type reduces results."""
    all_risks = find_risks()["total_found"]
    filtered = find_risks(contract_type="Employment Contract")
    assert filtered["total_found"] <= all_risks
    for risk in filtered["risks"]:
        assert risk["risk_level"] in {"critical", "high", "medium", "low"}


def test_find_risks_filter_by_level():
    """Filtering by risk_level returns only that level (case-insensitive)."""
    result = find_risks(risk_level="critical")
    for risk in result["risks"]:
        assert risk["risk_level"] == "critical"


def test_find_risks_each_risk_has_required_fields():
    """Every risk entry must have the mandatory fields."""
    required = {"risk_level", "category", "clause_text",
                "risk_reason", "saudi_legal_note",
                "recommended_revision", "related_regulation",
                "requires_escalation"}
    result = find_risks(risk_level="high")
    for risk in result["risks"]:
        missing = required - risk.keys()
        assert not missing, f"Risk entry missing fields: {missing}"


def test_find_risks_fuzzy_category_sets_confidence():
    """When category_fuzzy=True, match_confidence is set (not None) if results found."""
    result = find_risks(contract_type="SaaS Agreement", category="Jurisdiction Dispute", category_fuzzy=True)
    if result["total_found"] > 0:
        assert result["match_confidence"] is not None
        assert 0.0 <= result["match_confidence"] <= 1.0


def test_find_risks_exact_category_no_confidence():
    """When category_fuzzy=False (default), match_confidence is always None."""
    result = find_risks(contract_type="SaaS Agreement")
    assert result["match_confidence"] is None



def test_every_contract_type_has_field_tested_risk():
    """Coverage guard (2026-08-13 lesson): all 11 contract types must have
    at least one field_tested risk.  The original expansion left 4 types
    untouched and the gap was only found by external audit — not by tests."""
    import csv
    from saudi_legal_mcp.tools import get_repo_path

    csv_path = get_repo_path() / "datasets" / "saudi-contract-risk-dataset.csv"
    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    field_tested_types = {
        r["contract_type"] for r in rows
        if r.get("verification_status") == "field_tested"
    }
    all_types = {r["contract_type"] for r in rows}
    missing = all_types - field_tested_types
    assert not missing, (
        f"Contract types without any field_tested risk: {sorted(missing)}"
    )



# ---------------------------------------------------------------------------
# v0.4.8 — section-scoped citations (links)
# ---------------------------------------------------------------------------

def test_read_source_section_returns_its_own_link():
    """The annual-leave section carries its own document link."""
    result = read_source("labor-law", section="الحد الأدنى للإجازة السنوية")
    urls = [c["url"] for c in result["citations"]]
    assert any("LawDetails/08381293" in url for url in urls)

def test_read_source_section_without_body_link_gets_document_link():
    """Wave 1 acceptance: a section without a link in its own body must still
    carry the source document link when that document is known — but the label
    must say it opens the document, not this section."""
    result = read_source("labor-law", section="نطاقات")
    assert result["citations"], "document link must not be silently dropped"
    document = [c for c in result["citations"] if c["link_type"] == "law_document_url"]
    assert document, result["citations"]
    assert "لا مادة محددة" in document[0]["label"] or "لا هذا القسم" in document[0]["label"]

def test_read_source_metadata_only_no_citations():
    """Metadata-only request retrieves no content → no citations."""
    result = read_source("labor-law")
    assert result["citations"] == []

def test_citations_have_explicit_link_type():
    """Every citation must carry url + label + link_type from the honest set."""
    allowed = {"portal", "law_document_url", "direct_article_url"}
    result = read_source("pdpl", include_content=True)
    assert result["citations"]
    for c in result["citations"]:
        assert "url" in c and c["url"].startswith("https://")
        assert "link_type" in c
        assert c["link_type"] in allowed
    assert any(c["link_type"] == "law_document_url" for c in result["citations"])

def test_extract_links_unit_scoped_to_text():
    """_extract_links extracts only from the passed text (no file access).
    An unknown authority page is a portal, never a law document."""
    from saudi_legal_mcp.tools.sources import _extract_links
    text = "| **الرابط الرسمي** | https://example.gov.sa |"
    links = _extract_links(text)
    assert len(links) == 1
    assert links[0]["url"] == "https://example.gov.sa"
    assert links[0]["link_type"] == "portal"
    assert "example.gov.sa" in links[0]["label"]
    assert "بوابة" in links[0]["label"]
    assert "استخدم البحث داخل الموقع" in links[0]["label"]

def test_lawdetails_url_is_document_not_portal():
    """Wave 1 acceptance: a LawDetails URL is the law document, not the portal."""
    from saudi_legal_mcp.tools.provenance import classify_url
    info = classify_url(
        "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/"
        "08381293-6388-48e2-8ad2-a9a700f2aa94/1"
    )
    assert info["link_type"] == "law_document_url"
    assert info["is_deep_link"] is False
    assert "بوابة" not in info["label"]
    assert "مادة محددة" in info["label"]

def test_viewer_article_url_is_direct_article():
    """direct_article_url is reserved for a link that opens the article."""
    from saudi_legal_mcp.tools.provenance import classify_url
    info = classify_url(
        "https://laws.boe.gov.sa/BoeLaws/Laws/Viewer/"
        "c5caee1f-a619-489e-876c-b20800d59dc1?attachmentTitle=المادة الثانية"
    )
    assert info["link_type"] == "direct_article_url"
    assert info["is_deep_link"] is True
    assert "المادة" in info["label"]

def test_extract_links_fallback_document_when_no_body_link():
    """A no-link section with a known document returns the document citation,
    not an empty list, and the label is explicit about the scope."""
    from saudi_legal_mcp.tools.sources import _extract_links
    document = {
        "url": (
            "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/"
            "08381293-6388-48e2-8ad2-a9a700f2aa94/1"
        )
    }
    links = _extract_links("سطر بلا أي رابط في جسمه", document=document)
    assert len(links) == 1
    assert links[0]["link_type"] == "law_document_url"
    assert "لا مادة محددة" in links[0]["label"]

def test_extract_links_dedup_and_no_link_case():
    from saudi_legal_mcp.tools.sources import _extract_links
    text = (
        "نص عادي بلا روابط.\n"
        "| **الرابط الرسمي** | https://example.gov.sa |\n"
        "| **الرابط الرسمي** | https://example.gov.sa |\n"
    )
    links = _extract_links(text)
    assert len(links) == 1
    assert _extract_links("سطر بلا أي رابط") == []



# ---------------------------------------------------------------------------
# v0.4.9 — human-readable status explanation (no raw internal terms)
# ---------------------------------------------------------------------------

def test_read_source_has_status_explanation():
    """User-facing answers must carry plain-Arabic status explanation."""
    result = read_source("labor-law", include_content=True)
    assert "verification_status_explanation" in result
    explanation = result["verification_status_explanation"]
    assert explanation and len(explanation) > 5
    assert "field_tested" not in explanation

def test_skill_is_reasoning_guide_not_statute_text():
    """A skill is a reasoning guide: no quotes and no official_verbatim origin."""
    result = read_skill("labor-law-analysis", include_content=True)
    assert result["text_origin"] == "reasoning_guide"
    assert result["quotes"] == []
    assert result["provenance_level"] == "unlinked"
    assert "دليل تفكير" in result["answer_markdown"]


def test_skill_status_explanation_not_applicable():
    result = read_skill("labor-law-analysis", include_content=True)
    assert "verification_status_explanation" in result
    assert "استدلالي" in result["verification_status_explanation"]
    assert "field_tested" not in result["verification_status_explanation"]

def test_human_status_mapping():
    from saudi_legal_mcp.tools.schemas import human_status
    ft = human_status("field_tested")
    assert "field_tested" not in ft
    assert "محامٍ" in ft
    assert human_status("not_applicable") != human_status("unverified")
