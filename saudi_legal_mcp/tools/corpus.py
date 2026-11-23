"""
corpus.py — verbatim article records and article-level retrieval.

The corpus is the only place where `text_origin: official_verbatim` is produced.
Hand-written summaries in `sources/` are complementary commentary and are never
returned as quotes.

Storage layout (one JSON file per instrument):

    saudi_legal_mcp/data/corpus/labor-law.json
    saudi_legal_mcp/data/corpus/civil-transactions-law.json
    saudi_legal_mcp/data/corpus/pdpl.json
    saudi_legal_mcp/data/corpus/pdpl-exec-regulations.json

Each file carries its own `document_url`, `fetched_at`, `fetched_by`,
`source_sha256`, and `articles[]`.  Per-article records carry a hash of the
article text, their own provenance level, and an optional BOE Viewer URL.

No network access happens here.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from saudi_legal_mcp.tools import get_repo_path
from saudi_legal_mcp.tools.arabic import normalize_arabic, synonym_variants, tokenize_query
from saudi_legal_mcp.tools.provenance import (
    DISCLAIMER,
    LINK_ARTICLE,
    LINK_DOCUMENT,
    PROVENANCE_ARTICLE_LEVEL,
    PROVENANCE_FETCHED_OFFICIAL,
    RESEARCH_NOTICE,
    TEXT_ORIGIN_OFFICIAL,
    article_link_citation,
    best_provenance_level,
    build_answer_markdown,
    citation,
    provenance_envelope,
)

# Source IDs whose primary content is a verbatim corpus.  The hand-written
# summary remains available for commentary/topic lookup, but is not used as a
# quote when the corpus answers.
CORPUS_FILES: dict[str, tuple[str, ...]] = {
    "labor-law": ("labor-law",),
    "civil-transactions-law": ("civil-transactions-law",),
    "pdpl": ("pdpl", "pdpl-exec-regulations"),
}


def corpus_dir() -> Path:
    return get_repo_path() / "corpus"


@lru_cache(maxsize=32)
def load_corpus_file(stem: str) -> Optional[dict]:
    """Load one corpus JSON file, or None when absent/invalid."""
    path = corpus_dir() / f"{stem}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("articles"), list):
        return None
    return data


def available_corpus_sources() -> list[str]:
    """Return source IDs that currently have at least one corpus file."""
    return sorted(
        source_id
        for source_id in CORPUS_FILES
        if any(load_corpus_file(stem) for stem in CORPUS_FILES[source_id])
    )


def has_corpus(source_id: str) -> bool:
    return source_id in CORPUS_FILES and any(
        load_corpus_file(stem) for stem in CORPUS_FILES[source_id]
    )


def load_source_corpora(source_id: str) -> list[dict]:
    """Return all corpus instruments for a source ID, in declared order."""
    return [
        corpus
        for stem in CORPUS_FILES.get(source_id, ())
        if (corpus := load_corpus_file(stem)) is not None
    ]


def iter_articles(source_id: str) -> Iterable[dict]:
    """Yield article dicts, each annotated with its parent corpus metadata."""
    for corpus in load_source_corpora(source_id):
        for article in corpus.get("articles", []):
            yield {**article, "_corpus": corpus}


def _article_number(article: dict) -> Optional[str]:
    value = article.get("article")
    if value is None:
        return None
    return str(value).strip()


def get_article(source_id: str, article_number: str | int) -> Optional[dict]:
    """Return one article record by number, preferring in-force text.

    Duplicate numbers are possible on BOE pages when an article was added or
    renumbered.  Records carry `status`/`duplicate`; the last in-force record
    wins.  The earlier one remains available in the corpus file.
    """
    wanted = str(article_number).strip()
    found: Optional[dict] = None
    for article in iter_articles(source_id):
        if _article_number(article) != wanted:
            continue
        if article.get("status") == "canceled":
            continue
        found = article
    return found


def _score_article(article: dict, query_terms: list[str]) -> int:
    """Keyword score over the article label + text + chapter."""
    haystack = normalize_arabic(
        " ".join(
            str(article.get(key, ""))
            for key in ("article_label", "text", "chapter", "instrument")
        ).lower()
    )
    score = 0
    for term in query_terms:
        normalized = normalize_arabic(term.lower())
        matched = False
        for variant in synonym_variants(normalized):
            if variant and variant in haystack:
                matched = True
                break
            if len(variant) > 2 and variant.startswith("ال") and variant[2:] in haystack:
                matched = True
                break
            if len(variant) >= 2 and ("ال" + variant) in haystack:
                matched = True
                break
        if matched:
            score += 1
    return score


def search_articles(
    query: str,
    source_id: str,
    *,
    limit: int = 3,
    article_hints: Optional[Iterable[str]] = None,
) -> list[dict]:
    """Return the best verbatim articles for a query.

    `article_hints` lets the caller resolve a topic through the hand-written
    summary's explicit article references (e.g. "المادة 84") and then return
    the official text for that article.  It never invents a number.
    """
    if not has_corpus(source_id):
        return []

    query_terms = tokenize_query(query)
    results: list[dict] = []
    seen_ids: set[str] = set()

    # 1. Explicit hints from the summary (grounded article references).
    if article_hints:
        for number in article_hints:
            article = get_article(source_id, number)
            if article is None:
                continue
            article_id = article.get("id") or f"{source_id}/art-{number}"
            if article_id in seen_ids:
                continue
            seen_ids.add(article_id)
            results.append({**article, "_corpus": article.get("_corpus") or _find_corpus(source_id, article)})

    # 2. Direct keyword scoring.
    if query_terms:
        scored: list[tuple[int, dict]] = []
        for article in iter_articles(source_id):
            if article.get("status") == "canceled":
                continue
            text = article.get("text") or ""
            if not text.strip():
                continue
            score = _score_article(article, query_terms)
            if score > 0:
                scored.append((score, article))
        scored.sort(key=lambda item: item[0], reverse=True)
        max_score = scored[0][0] if scored else 1
        for score, article in scored:
            article_id = article.get("id") or f"{source_id}/art-{article.get('article')}"
            if article_id in seen_ids:
                continue
            seen_ids.add(article_id)
            enriched = dict(article)
            enriched["relevance_score"] = round(score / max_score, 2)
            results.append(enriched)

    return results[:limit]


def _find_corpus(source_id: str, article: dict) -> Optional[dict]:
    for corpus in load_source_corpora(source_id):
        for candidate in corpus.get("articles", []):
            if candidate is article or candidate.get("id") == article.get("id"):
                return corpus
    return None


def article_citations(article: dict, corpus: Optional[dict] = None) -> list[dict]:
    """Build honest citations for an article record."""
    corpus = corpus or article.get("_corpus") or {}
    links: list[dict] = []
    seen: set[str] = set()

    article_url = article.get("article_url")
    if article_url and article_url not in seen:
        links.append(article_link_citation(article_url))
        seen.add(article_url)

    document_url = article.get("document_url") or corpus.get("document_url")
    if document_url and document_url not in seen:
        links.append(citation(document_url))
        seen.add(document_url)

    return links


def article_record(article: dict) -> dict:
    """Convert a corpus article into a quote record with provenance."""
    corpus = article.get("_corpus") or {}
    citations = article_citations(article, corpus)
    provenance_level = article.get("provenance_level") or (
        PROVENANCE_ARTICLE_LEVEL
        if any(c["link_type"] == LINK_ARTICLE for c in citations)
        else PROVENANCE_FETCHED_OFFICIAL
    )
    fetched_at = article.get("fetched_at") or corpus.get("fetched_at")
    return {
        "id": article.get("id"),
        "article": article.get("article"),
        "article_label": article.get("article_label"),
        "text": article.get("text"),
        "text_origin": TEXT_ORIGIN_OFFICIAL,
        "provenance_level": provenance_level,
        "status": article.get("status", "in_force"),
        "chapter": article.get("chapter"),
        "instrument": article.get("instrument") or corpus.get("instrument"),
        "amendment_history": article.get("amendment_history"),
        "document_url": article.get("document_url") or corpus.get("document_url"),
        "article_url": article.get("article_url"),
        "fetched_at": fetched_at,
        "fetched_by": article.get("fetched_by") or corpus.get("fetched_by"),
        "sha256": article.get("sha256"),
        "citations": citations,
    }


def corpus_answer_markdown(quotes: list[dict], source_title: str) -> str:
    """Build the ready-to-paste answer for verbatim quotes."""
    if not quotes:
        return ""
    parts: list[str] = [f"## اقتباس رسمي — {source_title}"]
    for quote in quotes:
        parts.append(
            build_answer_markdown(
                title=quote.get("article_label") or f"المادة {quote.get('article')}",
                content=quote.get("text"),
                citations=quote.get("citations", []),
                text_origin=TEXT_ORIGIN_OFFICIAL,
                provenance_level=quote.get("provenance_level", ""),
                fetched_at=quote.get("fetched_at"),
                article_label=None,
                include_disclaimer=False,
            )
        )
    parts.append(f"**إخلاء المسؤولية:** {DISCLAIMER} {RESEARCH_NOTICE}")
    return "\n\n".join(parts)


def corpus_envelope(
    source_id: str,
    quotes: list[dict],
    *,
    citation_note: Optional[str] = None,
) -> dict:
    """Return the common fields for a corpus-backed response."""
    corpora = load_source_corpora(source_id)
    first = corpora[0] if corpora else {}
    all_citations = [c for q in quotes for c in q.get("citations", [])]
    fetched_at = first.get("fetched_at")
    return {
        "as_of": (fetched_at or "")[:10] or None,
        "insufficient_evidence": not bool(quotes),
        "quotes": quotes,
        "commentary": [],
        "provenance": provenance_envelope(
            all_citations,
            fetched_at=fetched_at,
            sha256=first.get("source_sha256"),
            freshness="synced" if quotes else "unverified",
            citation_note=citation_note,
        ),
        "answer_markdown": corpus_answer_markdown(
            quotes,
            first.get("title_ar") or source_id,
        ),
        "text_origin": TEXT_ORIGIN_OFFICIAL,
        # Response-level level is only article_level when every quote has a
        # real article link; otherwise the honest level is fetched_official.
        "provenance_level": (
            PROVENANCE_ARTICLE_LEVEL
            if quotes and all(
                q.get("provenance_level") == PROVENANCE_ARTICLE_LEVEL for q in quotes
            )
            else (PROVENANCE_FETCHED_OFFICIAL if quotes else "unlinked")
        ),
        "fetched_at": fetched_at,
        "source_document": (
            {"url": first.get("document_url"), **citation(first["document_url"])}
            if first.get("document_url")
            else None
        ),
        "disclaimer": DISCLAIMER,
    }


def corpus_file_stats(stem: str) -> dict:
    """Counts for one corpus file (no merging). Used to avoid the ambiguous
    pdpl=81 single number: pdpl-law is 43, pdpl-exec-regulations is 38."""
    corpus = load_corpus_file(stem)
    if not corpus:
        return {}
    articles = corpus.get("articles", [])
    return {
        "stem": stem,
        "article_count": len(articles),
        "in_force_count": sum(1 for a in articles if a.get("status") != "canceled"),
        "verbatim_count": sum(
            1 for a in articles if a.get("text_origin") == TEXT_ORIGIN_OFFICIAL
        ),
        "article_url_count": sum(1 for a in articles if a.get("article_url")),
        "fetched_at": corpus.get("fetched_at"),
        "document_url": corpus.get("document_url"),
    }


def corpus_stats(source_id: str) -> dict:
    """Counts used by list_legal_domains and tests."""
    corpora = load_source_corpora(source_id)
    if not corpora:
        return {}
    articles = [a for c in corpora for a in c.get("articles", [])]
    return {
        "instrument_count": len(corpora),
        "article_count": len(articles),
        "in_force_count": sum(1 for a in articles if a.get("status") != "canceled"),
        "verbatim_count": sum(
            1 for a in articles if a.get("text_origin") == TEXT_ORIGIN_OFFICIAL
        ),
        "article_url_count": sum(1 for a in articles if a.get("article_url")),
        "fetched_at": max((c.get("fetched_at") or "" for c in corpora), default=None),
    }


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
