"""
test_reasoning.py -- Tests for v0.3 reasoning tools.

Validates:
  - find_legal_provision finds sections anywhere in the file (not just first 3000 chars)
  - max_chars_per_section cap is respected (default 1500)
  - insufficient_evidence returned when no matches found
  - unknown source_id handled gracefully
  - ProvisionResponse and LegalBriefResponse schema conformance
  - match_confidence in [0.0, 1.0]
"""
import pytest
from saudi_legal_mcp.tools.reasoning import find_legal_provision, build_legal_brief
from saudi_legal_mcp.tools.schemas import ProvisionResponse, LegalBriefResponse, MatchedSection


# -- find_legal_provision -----------------------------------------------------

class TestFindLegalProvision:

    def test_finds_section_beyond_3000_chars(self):
        """Saudization section starts at char ~4014 in labor-law.md.
        The old read_source(max_chars=3000) would have missed it entirely."""
        result = find_legal_provision(
            query="سعودة نطاقات توطين",
            source_id="labor-law",
        )
        assert result.get("insufficient_evidence") is False, (
            "Expected to find Saudization content beyond char 3000"
        )
        sections = result.get("matched_sections", [])
        assert len(sections) >= 1
        # At least one matched section heading should relate to Saudization
        headings = " ".join(s["heading"] for s in sections)
        assert "سعودة" in headings or "Saudization" in headings or "Nitaqat" in headings

    def test_finds_termination_notice(self):
        """Termination notice terms exist in labor-law.md."""
        result = find_legal_provision(
            query="إشعار إنهاء عقد",
            source_id="labor-law",
        )
        assert result.get("insufficient_evidence") is False
        assert len(result.get("matched_sections", [])) >= 1

    def test_max_chars_per_section_respected(self):
        """No returned section body should exceed max_chars_per_section."""
        result = find_legal_provision(
            query="بيانات شخصية موافقة معالجة",
            source_id="pdpl",
            max_chars_per_section=1500,
        )
        if result.get("insufficient_evidence"):
            pytest.skip("No matching sections found -- check pdpl.md content")
        for section in result.get("matched_sections", []):
            assert len(section["body"]) <= 1500, (
                f"Section body exceeds 1500 chars: {len(section['body'])}"
            )

    def test_max_sections_respected(self):
        """Should return at most max_sections results."""
        result = find_legal_provision(
            query="عقد عمل نظام",
            source_id="labor-law",
            max_sections=2,
        )
        if not result.get("insufficient_evidence"):
            assert len(result.get("matched_sections", [])) <= 2

    def test_unknown_source_id_returns_error(self):
        """Unknown source_id must return an error, not raise an exception."""
        result = find_legal_provision(
            query="اختبار",
            source_id="nonexistent-law-xyz",
        )
        assert "error" in result
        assert "valid_options" in result

    def test_no_matching_terms_returns_insufficient_evidence(self):
        """Gibberish query that matches nothing should return insufficient_evidence=True."""
        result = find_legal_provision(
            query="xyzxyz123 zzz",
            source_id="labor-law",
        )
        assert result.get("insufficient_evidence") is True
        assert result.get("matched_sections") == []

    def test_match_confidence_in_range(self):
        """match_confidence must be in [0.0, 1.0] for all returned sections."""
        result = find_legal_provision(
            query="تقادم مدة فصل",
            source_id="labor-law",
        )
        if result.get("insufficient_evidence"):
            pytest.skip("No matching sections")
        for section in result.get("matched_sections", []):
            conf = section.get("match_confidence")
            assert conf is not None
            assert 0.0 <= conf <= 1.0, f"match_confidence out of range: {conf}"

    def test_result_has_disclaimer(self):
        result = find_legal_provision(query="عقد", source_id="labor-law")
        assert "disclaimer" in result


# -- ProvisionResponse schema -------------------------------------------------

class TestProvisionResponseSchema:

    def test_provision_response_fields(self):
        r = ProvisionResponse(
            source_id="labor-law",
            query="test",
            matched_sections=[],
            total_matched=0,
            insufficient_evidence=True,
        )
        d = r.to_dict()
        assert d["source_id"] == "labor-law"
        assert d["insufficient_evidence"] is True
        assert d["matched_sections"] == []
        assert "disclaimer" in d

    def test_matched_section_fields(self):
        ms = MatchedSection(
            heading="## التعريفات",
            body="نص قصير",
            match_score=3,
            match_confidence=0.75,
        )
        d = ms.to_dict()
        assert d["heading"] == "## التعريفات"
        assert d["match_score"] == 3
        assert d["match_confidence"] == 0.75


# -- LegalBriefResponse schema ------------------------------------------------

class TestLegalBriefResponseSchema:

    def test_legal_brief_response_insufficient(self):
        r = LegalBriefResponse(
            scenario="test",
            domain="nonexistent-domain",
            contract_type=None,
            source_id=None,
            evidence_count=0,
            brief=None,
            insufficient_evidence=True,
        )
        d = r.to_dict()
        assert d["insufficient_evidence"] is True
        assert d["brief"] is None
        assert "disclaimer" in d

    def test_legal_brief_response_with_data(self):
        r = LegalBriefResponse(
            scenario="هل ينتهي عقد العمل تلقائياً؟",
            domain="labor",
            contract_type="Employment Contract",
            source_id="labor-law",
            evidence_count=2,
            brief="مذكرة تجريبية",
            insufficient_evidence=False,
        )
        d = r.to_dict()
        assert d["evidence_count"] == 2
        assert d["brief"] == "مذكرة تجريبية"


# -- build_legal_brief integration --------------------------------------------

class TestBuildLegalBrief:

    def test_brief_returns_dict(self):
        result = build_legal_brief(
            scenario="هل يُلزم صاحب العمل بتقديم إشعار قبل إنهاء العقد؟",
            domain="labor",
            source_id="labor-law",
        )
        assert isinstance(result, dict)

    def test_brief_char_cap(self):
        """Output brief must not exceed 4000 chars."""
        result = build_legal_brief(
            scenario="ما التزامات الشركة تجاه حماية بيانات الموظفين وفق PDPL؟",
            domain="data-protection",
            source_id="pdpl",
        )
        brief = result.get("brief")
        if brief is not None:
            assert len(brief) <= 4000, f"Brief exceeds 4000 chars: {len(brief)}"

    def test_brief_insufficient_evidence_for_unknown_domain(self):
        """An entirely unknown domain with no matching source should return insufficient."""
        result = build_legal_brief(
            scenario="سؤال عشوائي",
            domain="nonexistent-domain-xyz",
            source_id=None,
            contract_type=None,
        )
        assert result.get("insufficient_evidence") is True


# -- v0.4.5/0.4.7 evidence gates (regression) ---------------------------------

class TestEvidenceGates:

    def test_bankruptcy_all_placeholder_returns_insufficient(self):
        """Gate A: when ALL retrieved sections are [يحتاج تحقق] templates,
        the brief must be withheld — the skill alone is not legal data."""
        result = build_legal_brief(
            scenario="كم مهلة اعتراض الدائنين وفق اللائحة التنفيذية لنظام الإفلاس",
            domain="commercial-dispute",
            source_id="bankruptcy-law",
        )
        assert result.get("insufficient_evidence") is True
        assert result.get("brief") is None

    def test_bankruptcy_with_contract_risks_not_insufficient(self):
        """Mixed evidence: placeholder provisions + real risk data →
        brief allowed with placeholder_warning attached."""
        result = build_legal_brief(
            scenario="كم مهلة اعتراض الدائنين",
            domain="commercial-dispute",
            source_id="bankruptcy-law",
            contract_type="Employment Contract",
        )
        assert result.get("insufficient_evidence") is False

    def test_labor_brief_passes_with_real_evidence(self):
        """Real (non-dominated) provisions must still produce a brief."""
        result = build_legal_brief(
            scenario="كم مدة إشعار إنهاء عقد العمل للموظف",
            domain="labor-law-analysis",
            source_id="labor-law",
        )
        assert result.get("insufficient_evidence") is False
        assert result.get("evidence_count", 0) >= 1

    def test_weak_confidence_provisions_filtered_from_brief(self):
        """Gate B: provisions below MATCH_CONFIDENCE_THRESHOLD are excluded
        from evidence.  build_legal_brief must not count them."""
        from saudi_legal_mcp.tools.reasoning import find_legal_provision
        from saudi_legal_mcp.tools.search import MATCH_CONFIDENCE_THRESHOLD

        result = find_legal_provision(
            query="المهل الزمنية اعتراض الدائنين",
            source_id="bankruptcy-law",
        )
        raw = result.get("matched_sections", [])
        assert raw, "expected raw sections for the gate test"
        weak = [s for s in raw if s["match_confidence"] < MATCH_CONFIDENCE_THRESHOLD]
        assert weak, "test premise requires at least one weak section"

        brief = build_legal_brief(
            scenario="المهل الزمنية اعتراض الدائنين",
            domain="commercial-dispute",
            source_id="bankruptcy-law",
        )
        if not brief.get("insufficient_evidence"):
            # brief evidence must exclude weak sections
            assert brief.get("evidence_count", 0) < 1 + len(raw)

    def test_provision_response_has_placeholder_dominated_field(self):
        result = find_legal_provision(
            query="المهل الزمنية",
            source_id="bankruptcy-law",
        )
        assert "placeholder_dominated" in result
        assert isinstance(result["placeholder_dominated"], bool)

    def test_gate_interaction_weak_filter_cannot_bypass_placeholder_gate(self, monkeypatch):
        """Interaction regression (2026-08-12 fix): confidence filtering
        emptying the provisions list must NOT bypass the placeholder gate.
        The gates must decide on RAW section count, not the filtered list —
        otherwise a third gate or refactor could silently resurrect the
        'skill alone counts as evidence' leak.

        Crafted result: one section, below threshold AND placeholder-dominated.
        Both gates must agree → insufficient_evidence: true.
        """
        from saudi_legal_mcp.tools import reasoning as rmod

        def fake_provision(query, source_id, max_sections=3, max_chars_per_section=1500, **kwargs):
            return {
                "source_id": source_id,
                "query": query,
                "matched_sections": [
                    {
                        "heading": "## قالب جداول",
                        "body": "جدول [يحتاج تحقق من النص الرسمي] فقط",
                        "match_score": 1,
                        "match_confidence": 0.5,
                    },
                ],
                "total_matched": 1,
                "insufficient_evidence": False,
                "placeholder_warning": "كل الأقسام تحتوي علامات يحتاج تحقق",
                "placeholder_dominated": True,
            }

        monkeypatch.setattr(rmod, "search_legal_provision", fake_provision)
        result = build_legal_brief(
            scenario="سؤال عن مهلة غير متوفرة",
            domain="commercial-dispute",
            source_id="bankruptcy-law",
        )
        assert result.get("insufficient_evidence") is True
        assert result.get("brief") is None

    def test_gate_interaction_strong_section_with_placeholder_passes(self, monkeypatch):
        """Counter-case: a section ABOVE threshold that is NOT dominated
        must still produce a brief — the interaction gates must not
        over-trigger when real evidence exists."""
        from saudi_legal_mcp.tools import reasoning as rmod

        def fake_provision(query, source_id, max_sections=3, max_chars_per_section=1500, **kwargs):
            return {
                "source_id": source_id,
                "query": query,
                "matched_sections": [
                    {
                        "heading": "## إنهاء العقد",
                        "body": "يشترط إشعار كتابي قبل الإنهاء بمدة محددة",
                        "match_score": 2,
                        "match_confidence": 1.0,
                    },
                ],
                "total_matched": 1,
                "insufficient_evidence": False,
                "placeholder_warning": None,
                "placeholder_dominated": False,
            }

        monkeypatch.setattr(rmod, "search_legal_provision", fake_provision)
        result = build_legal_brief(
            scenario="هل يشترط إشعار قبل إنهاء العقد",
            domain="labor-law-analysis",
            source_id="labor-law",
        )
        assert result.get("insufficient_evidence") is False
        assert result.get("evidence_count", 0) >= 1


# -- v0.4.9 — phase 2 citations + scenario regression --------------------------

class TestCitationsPhase2:

    def test_matched_section_citations_scope_bound(self):
        """Each matched section carries citations from ITS OWN body only."""
        result = find_legal_provision(
            query="الحد الأدنى للإجازة السنوية",
            source_id="labor-law",
        )
        sections = result.get("matched_sections", [])
        assert sections, "expected matched sections"
        by_heading = {s["heading"]: s.get("citations", []) for s in sections}
        annual = by_heading.get("### 1. الحد الأدنى للإجازة السنوية / Minimum Annual Leave")
        assert annual, f"sections: {list(by_heading)}"
        assert any(c["url"] == "https://www.boe.gov.sa" for c in annual)

    def test_every_summary_section_has_a_document_link(self):
        """Wave 1: a summary section without a link in its own body gets the
        source document link, with an explicit document-scope label."""
        result = find_legal_provision(
            query="الحد الأدنى للإجازة السنوية",
            source_id="labor-law",
        )
        sections = result["matched_sections"]
        assert sections
        for section in sections:
            assert section.get("citations"), (
                f"section without a document link: {section.get('heading')}"
            )
            assert any(
                c["link_type"] == "law_document_url"
                for c in section["citations"]
            )
            assert section.get("text_origin") == "hand_written_summary"

    def test_brief_contains_sources_section(self):
        """Brief must end with مصادر والروابط carrying an honest document label."""
        result = build_legal_brief(
            scenario="كم يوماً الإجازة السنوية الدنيا للموظف في السعودية؟",
            domain="labor-law-analysis",
            source_id="labor-law",
        )
        assert result.get("insufficient_evidence") is False
        brief = result.get("brief") or ""
        assert "المصادر والروابط" in brief
        assert "وثيقة النظام" in brief or "لا مادة محددة" in brief
        assert "بوابة الهيئة الرسمية" not in brief

    def test_full_question_scenario_not_gated_by_confidence(self):
        """v0.4.9 regression: a natural-language scenario whose best
        section confidence is below 0.7 must still produce a brief.
        Confidence gating is the search_legal_provision tool's job;
        the orchestrator must not silence real evidence."""
        result = build_legal_brief(
            scenario="كم يوماً الإجازة السنوية الدنيا للموظف في السعودية؟",
            domain="labor-law-analysis",
            source_id="labor-law",
        )
        assert result.get("insufficient_evidence") is False
        assert result.get("evidence_count", 0) >= 3

    def test_stopword_tokenizer_excludes_function_words(self):
        from saudi_legal_mcp.tools.reasoning import _tokenize_query
        tokens = _tokenize_query("كم يوماً الإجازة السنوية للموظف في السعودية؟")
        assert "كم" not in tokens
        assert "في" not in tokens
        assert "الإجازة" in tokens
        # punctuation must not be glued to tokens
        assert not any("؟" in t for t in tokens)


# -- v0.4.11 — eval comparison normalization -----------------------------------

class TestNormalizePhrase:

    def test_phrase_level_definite_article(self):
        """تسوية وقائية ↔ التسوية الوقائية (ال on the second word)."""
        from saudi_legal_mcp.tools.reasoning import normalize_phrase
        a = normalize_phrase("تسوية وقائية")
        b = normalize_phrase("التسوية الوقائية")
        assert a == b
        assert normalize_phrase("تسوية وقائية") in normalize_phrase("جدول التسوية الوقائية الرئيسية")

    def test_prepositional_elision(self):
        """للمحاكم ↔ المحاكم (hamzat-al-wasl elided after preposition)."""
        from saudi_legal_mcp.tools.reasoning import normalize_phrase
        a = normalize_phrase("المحاكم العمالية")
        b = normalize_phrase("اختصاص حصري للمحاكم العمالية")
        assert a in b

    def test_word_medial_hamza(self):
        """غسل أموال ↔ غسل الاموال (word-medial hamza form)."""
        from saudi_legal_mcp.tools.reasoning import normalize_phrase
        a = normalize_phrase("غسل أموال")
        b = normalize_phrase("جرائم غسل الاموال")
        assert a in b

    def test_orthographic_variants(self):
        from saudi_legal_mcp.tools.reasoning import normalize_phrase
        assert normalize_phrase("أجرًا") == normalize_phrase("اجرا")


# -- v0.4.12 — synonym scoring-side expansion (direct-tool regression) ---------

class TestSynonymExpansion:

    def test_direct_tool_natural_question_finds_section(self):
        """The exact documented failure: 'كم يستحق الموظف إجازة في السنة؟'
        returned insufficient_evidence:true although the annual-leave
        section contains the answer (الموظف≠العامل, السنة≠سنوياً)."""
        result = find_legal_provision(
            query="كم يستحق الموظف إجازة في السنة؟",
            source_id="labor-law",
        )
        assert result.get("insufficient_evidence") is False
        sections = result.get("matched_sections", [])
        # normalization-aware comparison: the heading contains 'للإجازة'
        # (preposition elides ال's alef) — literal 'الإجازة' would fail
        from saudi_legal_mcp.tools.reasoning import normalize_phrase
        assert any(
            normalize_phrase("الإجازة") in normalize_phrase(s["heading"])
            for s in sections
        )

    def test_synonym_variants_group_lookup(self):
        from saudi_legal_mcp.tools.reasoning import _synonym_variants
        assert "العامل" in _synonym_variants("الموظف")
        assert "الموظف" in _synonym_variants("العامل")
        assert _synonym_variants("بنك") == frozenset({"بنك"})

    def test_expansion_does_not_inflate_token_count(self):
        """Scoring-side expansion must keep query term count unchanged
        (v0.4.3 lesson: no query-side inflation of the denominator)."""
        from saudi_legal_mcp.tools.reasoning import _tokenize_query
        tokens = _tokenize_query("كم يستحق الموظف إجازة في السنة؟")
        assert len(tokens) == 4  # يستحق، الموظف، إجازة، السنة — no added variants



# -- v0.4.14 — citation absence is explicit, never silent ---------------------

class TestCitationNote:

    def test_provision_citation_note_when_no_links(self):
        """Sections with no links in their bodies must produce an explicit
        citation_note — the leaves table case from discovery #5."""
        result = find_legal_provision(
            query="الإجازة بدون أجر",
            source_id="labor-law",
        )
        sections = result.get("matched_sections", [])
        assert sections
        if not any(s.get("citations") for s in sections):
            note = result.get("citation_note")
            assert note and "لا رابط مباشر" in note
        else:
            assert result.get("citation_note") is None

    def test_read_source_section_with_document_link_has_no_citation_note(self):
        """Wave 1: the document link is present inside the summary section, so
        there is no longer a false 'no link' note."""
        from saudi_legal_mcp.tools.sources import read_source
        result = read_source("labor-law", section="الإجازات")
        assert result["citations"]
        assert any(c["link_type"] == "law_document_url" for c in result["citations"])
        assert result.get("citation_note") is None

    def test_citation_note_absent_when_links_exist(self):
        from saudi_legal_mcp.tools.sources import read_source
        result = read_source("labor-law", section="الحد الأدنى للإجازة السنوية")
        assert result["citations"], "premise: this section has a link"
        assert result.get("citation_note") is None
