"""
reasoning.py — section retrieval, article-level retrieval, and legal briefs.

Canonical public function: `search_legal_provision`.
Legacy raw-summary alias: `find_legal_provision` (kept for internal callers and
existing evals; it is a thin preset over the same implementation).

Resolution order:
  1. If a verbatim corpus exists for the source, search it and return
     `quotes` with `text_origin: official_verbatim`.
  2. If the corpus does not answer, use the hand-written summary.  Summary
     sections are explicitly marked `text_origin: hand_written_summary` and are
     never presented as official quotes.
"""
from __future__ import annotations

import re
from dataclasses import asdict
from typing import Optional

from saudi_legal_mcp.tools import get_repo_path
from saudi_legal_mcp.tools.arabic import (
    ARABIC_STOPWORDS,
    SYNONYM_GROUPS,
    normalize_arabic,
    normalize_phrase,
    strip_diacritics,
    strip_placeholders,
    synonym_variants,
    tokenize_query,
)
from saudi_legal_mcp.tools.article_numbers import parse_arabic_article_number
from saudi_legal_mcp.tools.corpus import (
    article_record,
    corpus_envelope,
    has_corpus,
    search_articles,
)
from saudi_legal_mcp.tools.provenance import (
    DISCLAIMER,
    PROVENANCE_LINKED_DOCUMENT,
    PROVENANCE_LINKED_PORTAL,
    PROVENANCE_UNLINKED,
    TEXT_ORIGIN_HAND_WRITTEN,
    TEXT_ORIGIN_OFFICIAL,
    best_provenance_level,
    build_answer_markdown,
    document_reference,
    provenance_envelope,
)
from saudi_legal_mcp.tools.schemas import LegalBriefResponse, MatchedSection, ProvisionResponse
from saudi_legal_mcp.tools.skills import read_skill
from saudi_legal_mcp.tools.sources import VALID_REGULATIONS, _extract_links
from saudi_legal_mcp.tools.search import MATCH_CONFIDENCE_THRESHOLD, find_risks

# Backwards-compatible module-level aliases (tests and third-party callers
# imported these private helpers before the arabic.py extraction).
_normalize_arabic = normalize_arabic
_strip_diacritics = strip_diacritics
_tokenize_query = tokenize_query
_synonym_variants = synonym_variants
_strip_placeholders = strip_placeholders

# Constants
_MAX_CHARS_PER_SECTION = 1500
_MAX_SECTIONS_RETURNED = 3
_BRIEF_MAX_CHARS = 4000

_ARABIC_NUMBER_HINT_RE = re.compile(r"المادة\s*(?:رقم\s*)?([0-9\u0660-\u0669]{1,3})")
_ARABIC_WORD_HINT_RE = re.compile(r"المادة\s+([^\n|،.:]{2,40})")


def _split_into_sections(text: str) -> list[dict]:
    """Split markdown text into sections by heading level (## or ###)."""
    lines = text.splitlines()
    sections: list[dict] = []
    current_heading = "(preamble)"
    current_level = 0
    current_body: list[str] = []

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            if current_body or current_heading != "(preamble)":
                sections.append({
                    "heading": current_heading,
                    "body": "\n".join(current_body).strip(),
                    "level": current_level,
                })
            j = 0
            while j < len(line) and line[j] == "#":
                j += 1
            current_level = j
            current_heading = line.strip()
            current_body = []
        else:
            current_body.append(line)

    if current_body or current_heading != "(preamble)":
        sections.append({
            "heading": current_heading,
            "body": "\n".join(current_body).strip(),
            "level": current_level,
        })

    return sections


def _score_section(section: dict, query_terms: list[str]) -> int:
    """Return hit count of query_terms found in section heading + body."""
    haystack = normalize_arabic(
        (section["heading"] + " " + section["body"]).lower()
    )
    score = 0
    for term in query_terms:
        t = normalize_arabic(term.lower())
        matched = False
        for variant in synonym_variants(t):
            if variant in haystack:
                matched = True
                break
            if len(variant) > 2 and variant[:2] == "ال" and variant[2:] in haystack:
                matched = True
                break
            if len(variant) >= 2 and ("ال" + variant) in haystack:
                matched = True
                break
        if matched:
            score += 1
    return score


def _is_arabic(s: str) -> bool:
    """True if string consists entirely of Arabic-script characters."""
    return bool(re.fullmatch(r"[\u0600-\u06ff]+", s))


def _summary_search(
    query: str,
    source_id: str,
    max_sections: int = _MAX_SECTIONS_RETURNED,
    max_chars_per_section: int = _MAX_CHARS_PER_SECTION,
) -> dict:
    """Raw keyword retrieval over a hand-written summary file."""
    source_path = get_repo_path() / "sources" / f"{source_id}.md"
    full_text = source_path.read_text(encoding="utf-8")
    document = document_reference(full_text)
    sections = _split_into_sections(full_text)

    query_terms = tokenize_query(query)
    if not query_terms:
        return {
            "source_id": source_id,
            "query": query,
            "matched_sections": [],
            "total_matched": 0,
            "insufficient_evidence": True,
            "disclaimer": DISCLAIMER,
        }

    scored = sorted(
        [(s, _score_section(s, query_terms)) for s in sections],
        key=lambda x: x[1],
        reverse=True,
    )
    hits = [(s, score) for s, score in scored if score > 0]

    # Exclude sections whose score comes entirely from [يحتاج تحقق] markers.
    substantive_hits: list[tuple[dict, int]] = []
    for section, score in hits:
        stripped = strip_placeholders(section["body"])
        stripped_score = _score_section(
            {"heading": section["heading"], "body": stripped},
            query_terms,
        )
        if stripped_score == 0:
            continue
        substantive_hits.append((section, score))

    if not substantive_hits:
        return {
            "source_id": source_id,
            "query": query,
            "matched_sections": [],
            "total_matched": 0,
            "insufficient_evidence": True,
            "disclaimer": DISCLAIMER,
        }

    top = substantive_hits[:max_sections]
    matched: list[dict] = []
    any_placeholder = False
    all_placeholder = len(top) > 0

    for section, score in top:
        has_marker = "يحتاج تحقق" in section["body"]
        if has_marker:
            any_placeholder = True
        else:
            all_placeholder = False
        body = section["body"][:max_chars_per_section]
        confidence = round(score / max(len(query_terms), 1), 2)
        citations = _extract_links(section["body"], document=document)
        matched.append(asdict(MatchedSection(
            heading=section["heading"],
            body=body,
            match_score=score,
            match_confidence=confidence,
            citations=citations,
            text_origin=TEXT_ORIGIN_HAND_WRITTEN,
            provenance_level=best_provenance_level(citations),
        )))

    placeholder_warning: Optional[str] = None
    if all_placeholder:
        placeholder_warning = (
            "جميع الأقسام المسترجعة تحتوي على علامات [يحتاج تحقق] "
            "تشير إلى معلومات غير مكتملة أو لم تُراجع بعد. "
            "هذه الأدلة غير كافية للإجابة."
        )
    elif any_placeholder:
        placeholder_warning = (
            "بعض الأقسام المسترجعة تحتوي على علامات [يحتاج تحقق] "
            "تشير إلى معلومات غير مكتملة أو لم تُراجع بعد."
        )

    citation_note: Optional[str] = None
    if matched and not any(s.get("citations") for s in matched):
        citation_note = (
            "لا رابط مباشر متاح للأقسام المسترجعة تحديداً — تحقق من النص "
            "الرسمي عبر بوابة هيئة الخبراء (boe.gov.sa) بنفسك."
        )

    return {
        "source_id": source_id,
        "query": query,
        "matched_sections": matched,
        "total_matched": len(hits),
        "insufficient_evidence": False,
        "placeholder_warning": placeholder_warning,
        "citation_note": citation_note,
        "placeholder_dominated": all_placeholder,
        "text_origin": TEXT_ORIGIN_HAND_WRITTEN,
        "provenance_level": best_provenance_level(
            [c for s in matched for c in s.get("citations", [])]
        ),
        "fetched_at": None,
    }


def _extract_article_hints(query: str, source_id: str) -> list[str]:
    """Resolve a topic through summary article references (grounded hints).

    The summary contains sentences like "المادة 84 من نظام العمل".  We use
    those explicit references only; we never guess an article number.
    """
    try:
        summary = _summary_search(query, source_id, max_sections=3)
    except Exception:
        return []
    if summary.get("insufficient_evidence"):
        return []

    hints: list[str] = []
    for section in summary.get("matched_sections", []):
        haystack = f"{section.get('heading', '')}\n{section.get('body', '')}"
        for match in _ARABIC_NUMBER_HINT_RE.finditer(haystack):
            value = match.group(1).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
            if value not in hints:
                hints.append(value)
        for match in _ARABIC_WORD_HINT_RE.finditer(haystack):
            number = parse_arabic_article_number(match.group(1))
            if number and str(number) not in hints:
                hints.append(str(number))
    return hints[:3]


def search_legal_provision(
    query: str,
    source_id: str,
    max_sections: int = _MAX_SECTIONS_RETURNED,
    max_chars_per_section: int = _MAX_CHARS_PER_SECTION,
    *,
    apply_confidence_gate: bool = False,
    prefer_corpus: bool = True,
) -> dict:
    """Search a source for the best legal provisions.

    Corpus-first: when a verbatim corpus exists, results carry
    `text_origin: "official_verbatim"` and a real document/article URL.
    Otherwise the hand-written summary is searched and explicitly marked.

    `apply_confidence_gate` applies the legacy 0.7 relative-score gate to
    SUMMARY sections only.  It is not applied to verbatim articles: a verbatim
    article with one matching term is still a real quote, not a probability.
    """
    if source_id not in VALID_REGULATIONS:
        return {
            "error": f"Unknown source_id '{source_id}'.",
            "valid_options": sorted(VALID_REGULATIONS),
            "disclaimer": DISCLAIMER,
        }

    source_path = get_repo_path() / "sources" / f"{source_id}.md"
    if not source_path.exists():
        return {
            "error": f"Source file not found: {source_path.name}",
            "source_id": source_id,
            "disclaimer": DISCLAIMER,
        }

    if prefer_corpus and has_corpus(source_id):
        hints = _extract_article_hints(query, source_id)
        articles = search_articles(
            query,
            source_id,
            limit=max_sections,
            article_hints=hints,
        )
        if articles:
            quotes = [article_record(article) for article in articles]
            matched_sections: list[dict] = []
            for quote in quotes:
                relevance = next(
                    (
                        article.get("relevance_score")
                        for article in articles
                        if article.get("id") == quote.get("id")
                    ),
                    None,
                )
                matched_sections.append(asdict(MatchedSection(
                    heading=f"## {quote.get('article_label') or 'المادة ' + str(quote.get('article'))}",
                    body=quote.get("text") or "",
                    match_score=max(1, int(round((relevance or 1.0) * 100))),
                    match_confidence=float(relevance if relevance is not None else 1.0),
                    citations=quote.get("citations", []),
                    text_origin=TEXT_ORIGIN_OFFICIAL,
                    provenance_level=quote.get("provenance_level"),
                    fetched_at=quote.get("fetched_at"),
                    article=quote.get("article"),
                    article_id=quote.get("id"),
                )))

            result = {
                "source_id": source_id,
                "query": query,
                "matched_sections": matched_sections,
                "total_matched": len(quotes),
                "insufficient_evidence": False,
                "placeholder_warning": None,
                "placeholder_dominated": False,
                "citation_note": None,
                "excluded_low_confidence_count": 0,
                "retrieval_scope": "verbatim_corpus",
            }
            result.update(corpus_envelope(source_id, quotes))
            return result

    # ── Summary fallback ────────────────────────────────────────────────────
    result = _summary_search(
        query,
        source_id,
        max_sections=max_sections,
        max_chars_per_section=max_chars_per_section,
    )
    if result.get("insufficient_evidence"):
        return result

    sections = result.get("matched_sections", [])
    if apply_confidence_gate:
        strong = [
            s for s in sections
            if s.get("match_confidence", 0.0) >= MATCH_CONFIDENCE_THRESHOLD
        ]
        dropped = len(sections) - len(strong)
        result["excluded_low_confidence_count"] = dropped
        if not strong:
            result["matched_sections"] = []
            result["total_matched"] = 0
            result["insufficient_evidence"] = True
            result["placeholder_warning"] = (
                "أفضل الأقسام المطابقة كانت دون عتبة الثقة (0.7) — لا دليل كافٍ."
            )
            return result
        result["matched_sections"] = strong
        sections = strong
    else:
        result["excluded_low_confidence_count"] = 0

    all_citations = [c for s in sections for c in s.get("citations", [])]
    result["provenance"] = provenance_envelope(
        all_citations,
        fetched_at=None,
        sha256=None,
        freshness="unverified",
        citation_note=result.get("citation_note"),
    )
    result["answer_markdown"] = build_answer_markdown(
        title=f"{source_id} — نتائج البحث",
        content="\n\n".join(
            f"{s.get('heading', '')}\n{s.get('body', '')}" for s in sections
        ),
        citations=all_citations,
        text_origin=TEXT_ORIGIN_HAND_WRITTEN,
        provenance_level=result.get("provenance_level", PROVENANCE_UNLINKED),
        fetched_at=None,
        citation_note=result.get("citation_note"),
    )
    result["quotes"] = []
    result["commentary"] = []
    result["as_of"] = None
    result["disclaimer"] = DISCLAIMER
    return result


def find_legal_provision(
    query: str,
    source_id: str,
    max_sections: int = _MAX_SECTIONS_RETURNED,
    max_chars_per_section: int = _MAX_CHARS_PER_SECTION,
) -> dict:
    """Legacy raw-summary alias (no corpus, no confidence gate).

    Kept for `evals/`, internal brief assembly, and third-party callers.  New
    code should call `search_legal_provision`.
    """
    return search_legal_provision(
        query=query,
        source_id=source_id,
        max_sections=max_sections,
        max_chars_per_section=max_chars_per_section,
        apply_confidence_gate=False,
        prefer_corpus=False,
    )


def build_legal_brief(
    scenario: str,
    domain: str,
    contract_type: Optional[str] = None,
    source_id: Optional[str] = None,
) -> dict:
    """Orchestrate a brief from skill + provisions + risks.

    When a verbatim corpus answers, the brief carries the official quote and
    its link; the summary is not substituted for the quote.
    """
    evidence_parts: list[str] = []

    skill_result = read_skill(domain, include_content=True)
    skill_summary: str = ""
    if isinstance(skill_result, dict) and not skill_result.get("error"):
        skill_summary = (skill_result.get("content") or "")[:800]
        if skill_summary:
            evidence_parts.append(f"[skill:{domain}]")

    provisions: list[dict] = []
    quotes: list[dict] = []
    prov_placeholder_warning: Optional[str] = None
    prov_placeholder_dominated: bool = False
    prov_raw_count: int = 0
    if source_id:
        prov_result = search_legal_provision(
            scenario,
            source_id,
            apply_confidence_gate=False,
            prefer_corpus=True,
        )
        if not prov_result.get("insufficient_evidence"):
            raw_sections = prov_result.get("matched_sections", [])
            prov_raw_count = len(raw_sections)
            provisions = list(raw_sections)
            quotes = list(prov_result.get("quotes", []))
            prov_placeholder_warning = prov_result.get("placeholder_warning")
            prov_placeholder_dominated = prov_result.get("placeholder_dominated", False)
            for p in provisions:
                evidence_parts.append(f"[provision:{source_id}:{p.get('heading','')}]")

    risks: list[dict] = []
    if contract_type:
        risk_result = find_risks(contract_type=contract_type)
        raw_risks = risk_result.get("risks", [])
        resp_confidence = risk_result.get("match_confidence")
        confidence_ok = (
            resp_confidence is None
            or resp_confidence >= MATCH_CONFIDENCE_THRESHOLD
        )
        if confidence_ok:
            for r in raw_risks[:3]:
                reg = r.get("related_regulation", "")
                if reg:
                    evidence_parts.append(f"[risk:{contract_type}]")
            risks = raw_risks[:3]

    if not evidence_parts:
        return {
            "scenario": scenario,
            "domain": domain,
            "insufficient_evidence": True,
            "brief": None,
            "disclaimer": "لا يوجد دليل كافٍ لإصدار مذكرة قانونية. يرجى الاستعانة بمحامٍ مرخّص.",
        }

    has_data = prov_raw_count > 0 or bool(risks)
    data_all_placeholder = (
        prov_raw_count > 0
        and prov_placeholder_dominated
        and not bool(risks)
    )
    if has_data and data_all_placeholder:
        return {
            "scenario": scenario,
            "domain": domain,
            "contract_type": contract_type,
            "source_id": source_id,
            "insufficient_evidence": True,
            "brief": None,
            "placeholder_warning": prov_placeholder_warning,
            "disclaimer": (
                "جميع النصوص النظامية المسترجعة تحتوي على علامات [يحتاج تحقق] "
                "تشير إلى معلومات غير مكتملة. لا يمكن إصدار مذكرة قانونية بهذا "
                "الدليل. يرجى الاستعانة بمحامٍ مرخّص."
            ),
        }

    sections_text = ""
    if not quotes:
        for p in provisions:
            clean_heading = p.get("heading", "").lstrip("#").strip()
            sections_text += f"\n**{clean_heading}**\n{p.get('body','')[:400]}\n"

    quotes_text = ""
    if quotes:
        for q in quotes:
            sources = "، ".join(
                f"[{c['label']}]({c['url']})" for c in q.get("citations", [])
            )
            quotes_text += (
                f"\n> **{q.get('article_label') or 'المادة ' + str(q.get('article'))}** — "
                f"اقتباس رسمي حرفي.\n>\n"
                + "\n".join(f"> {line}" for line in (q.get("text") or "").splitlines())
                + f"\n>\n> {sources}\n"
            )

    risks_text = ""
    for r in risks:
        risks_text += f"- [{r.get('risk_level','').upper()}] {r.get('risk_reason','')[:200]}\n"

    sources_text = ""
    seen_sources: set[str] = set()
    for p in provisions:
        for c in p.get("citations", []):
            url = c.get("url", "")
            if url and url not in seen_sources:
                seen_sources.add(url)
                label = c.get("label") or url
                sources_text += f"- [{label}]({url})\n"
    if not sources_text:
        for r in risks[:3]:
            reg = r.get("related_regulation", "")
            if reg and reg not in seen_sources:
                seen_sources.add(reg)
                sources_text += f"- {reg}\n"

    sources_block = ""
    if sources_text:
        sources_block = f"\n### المصادر والروابط\n{sources_text}\n"

    brief = (
        f"## مذكرة قانونية مختصرة\n"
        f"**السيناريو:** {scenario}\n\n"
        f"### السياق المجالي ({domain})\n{skill_summary[:400]}\n\n"
        f"### النصوص النظامية ذات الصلة\n{sections_text}\n"
        f"{quotes_text}"
        f"### المخاطر التعاقدية\n{risks_text}\n"
        f"{sources_block}"
        f"\n*الأدلة المستخدمة: {len(evidence_parts)} مصدر(اً)*"
    )[:_BRIEF_MAX_CHARS]

    response = asdict(LegalBriefResponse(
        scenario=scenario,
        domain=domain,
        contract_type=contract_type,
        source_id=source_id,
        evidence_count=len(evidence_parts),
        brief=brief,
        insufficient_evidence=False,
    ))
    if prov_placeholder_warning:
        response["placeholder_warning"] = prov_placeholder_warning
    if quotes:
        response["text_origin"] = TEXT_ORIGIN_OFFICIAL
        response["provenance_level"] = quotes[0].get("provenance_level")
        response["fetched_at"] = quotes[0].get("fetched_at")
    else:
        response["text_origin"] = TEXT_ORIGIN_HAND_WRITTEN
        response["provenance_level"] = PROVENANCE_LINKED_DOCUMENT if any(
            p.get("citations") for p in provisions
        ) else PROVENANCE_UNLINKED
        response["fetched_at"] = None
    response["disclaimer"] = DISCLAIMER
    return response
