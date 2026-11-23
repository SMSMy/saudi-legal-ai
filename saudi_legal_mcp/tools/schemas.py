"""
schemas.py -- Saudi Legal AI MCP Server
Dataclass schemas for all tool responses (v0.2 + v0.3).

All response types are defined here with runtime validation via __post_init__.
Tools return dataclasses converted to dict (asdict()) -- NOT json.dumps() strings.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

_DISCLAIMER = "هذه معلومات قانونية عامة وليست استشارة قانونية."

_VALID_VERIFICATION_STATUSES = frozenset({
    "unverified", "field_tested", "verified", "review_due", "outdated", "disputed", "not_applicable",
})

_VALID_ISSUE_TYPES = frozenset({
    "outdated", "missing_article", "incorrect_citation", "broken_url",
})

# v0.4.9 — human-readable Arabic explanations for internal status terms.
# Raw terms (field_tested, verification_status...) must NEVER reach the
# user-facing answer verbatim.  Tools attach the explanation alongside
# the raw value; the rendering agent must use the explanation.
_STATUS_EXPLANATIONS = {
    "unverified": "لم يُراجع بعد — لا تستخدمه في إجابة جازمة",
    "field_tested": "جُرِّب تقنياً ونجح في الاختبارات الآلية، لكنه لم يُراجع من محامٍ مرخّص بعد — استخدمه للتوجيه العام فقط",
    "verified": "راجعه مختص قانوني مرخّص",
    "review_due": "تجاوز موعد المراجعة الدورية — يحتاج إعادة فحص قبل الاعتماد",
    "outdated": "قد لا يعكس آخر التعديلات النظامية — يحتاج تحقق من المصدر الرسمي",
    "disputed": "هناك خلاف حول دقته — لا تعتمد عليه وحدك",
    "not_applicable": "محتوى استدلالي توجيهي — لا يخضع لسلم التحقق التشريعي أصلاً",
}


def human_status(status: str) -> str:
    """Return the plain-Arabic explanation for a raw status value."""
    return _STATUS_EXPLANATIONS.get(status, "غير مُتحقَّق منه بعد")


# -- 1. SourceResponse --------------------------------------------------------

@dataclass
class SourceResponse:
    """Returned by read_source() / get_regulation_source()."""
    source_id: str
    verification_status: str
    content: Optional[str]
    content_available: bool
    content_truncated: bool
    citations: list[dict] = field(default_factory=list)
    retrieval_hint: Optional[str] = None
    # v0.4.9: plain-Arabic explanation — the agent must surface THIS,
    # never the raw verification_status term, in user-facing text.
    verification_status_explanation: Optional[str] = None
    disclaimer: str = _DISCLAIMER
    # Wave 1 (2026-11-23): provenance envelope.  Summary files are marked
    # hand_written_summary and never presented as official verbatim text.
    text_origin: str = "hand_written_summary"
    provenance_level: str = "unlinked"
    fetched_at: Optional[str] = None
    provenance: dict = field(default_factory=dict)
    source_document: Optional[dict] = None
    answer_markdown: Optional[str] = None
    quotes: list[dict] = field(default_factory=list)
    commentary: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.verification_status not in _VALID_VERIFICATION_STATUSES:
            raise ValueError(
                f"invalid verification_status '{self.verification_status}'. "
                f"Must be one of: {sorted(_VALID_VERIFICATION_STATUSES)}"
            )

    def to_dict(self) -> dict:
        return asdict(self)


# -- 2. SkillResponse ---------------------------------------------------------

@dataclass
class SkillResponse:
    """Returned by read_skill() / get_legal_skill()."""
    domain: str
    verification_status: str
    content: Optional[str]
    content_available: bool
    content_truncated: bool
    retrieval_hint: Optional[str] = None
    # v0.4.9: plain-Arabic explanation for user-facing rendering.
    verification_status_explanation: Optional[str] = None
    disclaimer: str = _DISCLAIMER

    def __post_init__(self) -> None:
        if self.verification_status not in _VALID_VERIFICATION_STATUSES:
            raise ValueError(
                f"invalid verification_status '{self.verification_status}'. "
                f"Must be one of: {sorted(_VALID_VERIFICATION_STATUSES)}"
            )

    def to_dict(self) -> dict:
        return asdict(self)


# -- 3. RiskResponse ----------------------------------------------------------

@dataclass
class RiskResponse:
    """Returned by find_risks() / search_contract_risks().

    match_confidence is set when fuzzy/partial category matching was used.
    None means exact match was applied (no ambiguity).
    float in [0.0, 1.0] signals partial match -- callers must NOT treat as exact.

    excluded_low_confidence_count: number of dataset rows that matched the category
    query in fuzzy mode but fell below MATCH_CONFIDENCE_THRESHOLD and were excluded.
    Non-zero means there IS related data, but the engine judged it too weak to surface.
    Callers can use this to prompt the user: "هناك مخاطر ذات صلة جزئية — حدّد الفئة أكثر".
    """
    query: dict
    total_found: int
    risks: list[dict]
    data_source: str
    match_confidence: Optional[float] = None
    excluded_low_confidence_count: int = 0
    disclaimer: str = _DISCLAIMER

    def to_dict(self) -> dict:
        return asdict(self)



# -- 4. ManifestResponse ------------------------------------------------------

@dataclass
class ManifestResponse:
    """Returned by read_manifest() / get_source_status()."""
    source_id: str
    verification_status: str
    metadata_status: str
    sha256: Optional[str]
    generated_at: Optional[str]
    review_due_at: Optional[str]
    verified_by: Optional[str]
    verified_at: Optional[str]

    def __post_init__(self) -> None:
        if self.verification_status not in _VALID_VERIFICATION_STATUSES:
            raise ValueError(
                f"invalid verification_status '{self.verification_status}'. "
                f"Must be one of: {sorted(_VALID_VERIFICATION_STATUSES)}"
            )

    def to_dict(self) -> dict:
        return asdict(self)


# -- 5. SourceStatusResponse --------------------------------------------------

@dataclass
class SourceStatusResponse:
    """Returned by get_source_status()."""
    source_id: str
    verification_status: str
    warning: Optional[str]  # None if no warning; caller should surface this to user
    # v0.4.9: plain-Arabic explanation — user-facing text must use this.
    verification_status_explanation: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# -- 6. ReportIssueResponse ---------------------------------------------------

@dataclass
class ReportIssueResponse:
    """Returned by report_source_issue()."""
    report_id: str
    written: bool
    path: Optional[str]  # None if ENABLE_LOCAL_REPORTS=false

    def to_dict(self) -> dict:
        return asdict(self)


# -- 7. MatchedSection (v0.3) -------------------------------------------------

@dataclass
class MatchedSection:
    """A single regulation section matched by find_legal_provision().

    match_confidence in [0.0, 1.0]: ratio of query_terms found in this section.
    match_score is the raw hit count (integer).
    body is capped at max_chars_per_section (default 1500) by the caller.

    v0.4.9: citations holds the links found inside THIS section's body
    (scope-bound — never whole-file links).  Each citation carries
    url + label + link_type (see _extract_links in sources.py).
    """
    heading: str
    body: str
    match_score: int
    match_confidence: float
    citations: list[dict] = field(default_factory=list)
    # Wave 1/2: a section is either a hand-written summary or a verbatim
    # article.  The consumer must render them differently.
    text_origin: str = "hand_written_summary"
    provenance_level: str = "unlinked"
    fetched_at: Optional[str] = None
    article: Optional[str] = None
    article_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# -- 8. ProvisionResponse (v0.3) ----------------------------------------------

@dataclass
class ProvisionResponse:
    """Returned by find_legal_provision().

    insufficient_evidence=True when no sections matched any query term.
    matched_sections is empty in that case.

    placeholder_warning (v0.4.5): set when matched_sections contain
    [يحتاج تحقق] markers indicating incomplete/not-yet-verified data.
    Consumers (LLM, build_legal_brief) should treat such evidence with
    appropriate caution — the section headings are relevant but the
    data cells may be structural placeholders.

    placeholder_dominated (v0.4.5): True when EVERY substantive section
    contains [يحتاج تحقق] markers.  This is a stronger signal than
    placeholder_warning alone — the entire retrieval result is tainted.

    citation_note (v0.4.14): set when matched sections carry no direct
    link — the rendering agent must relay this so verification-absence
    is explicit in the user-facing answer, never silent.
    """
    source_id: str
    query: str
    matched_sections: list[dict]
    total_matched: int
    insufficient_evidence: bool
    placeholder_warning: Optional[str] = None
    placeholder_dominated: bool = False
    citation_note: Optional[str] = None
    disclaimer: str = _DISCLAIMER
    # Wave 1/2 envelope.  `quotes` is the only place where official_verbatim
    # text is exposed; summary sections are not quotes.
    as_of: Optional[str] = None
    text_origin: str = "hand_written_summary"
    provenance_level: str = "unlinked"
    fetched_at: Optional[str] = None
    provenance: dict = field(default_factory=dict)
    answer_markdown: Optional[str] = None
    quotes: list[dict] = field(default_factory=list)
    commentary: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# -- 9. LegalBriefResponse (v0.3) ---------------------------------------------

@dataclass
class LegalBriefResponse:
    """Returned by build_legal_brief().

    Orchestrates skill + provisions + risks into a single capped brief.
    insufficient_evidence=True when all sources returned no usable evidence.
    brief is None in that case.
    evidence_count reflects the number of distinct evidence items used.
    """
    scenario: str
    domain: str
    contract_type: Optional[str]
    source_id: Optional[str]
    evidence_count: int
    brief: Optional[str]  # capped at 4000 chars by caller
    insufficient_evidence: bool
    disclaimer: str = _DISCLAIMER
    text_origin: str = "hand_written_summary"
    provenance_level: str = "unlinked"
    fetched_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)
