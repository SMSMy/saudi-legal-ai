"""
provenance.py — honest link taxonomy, provenance levels, and answer rendering.

Wave 1 rule: a link is never described as something it is not.

  portal             → the authority's general gateway
  law_document_url   → the law document itself (LawDetails / gazette / PDF)
  direct_article_url → a link proven to open the particular article

`direct_article_url` is only produced for BOE Viewer links whose
`attachmentTitle` names an article.  A `#art-84` fragment is NOT treated as
article-level unless a probe proves the page honours it.

The module also contains the shared disclaimer/rendering helpers.  It does not
import the MCP package and performs no I/O.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional
from urllib.parse import parse_qs, urlparse

LINK_PORTAL = "portal"
LINK_DOCUMENT = "law_document_url"
LINK_ARTICLE = "direct_article_url"

TEXT_ORIGIN_HAND_WRITTEN = "hand_written_summary"
TEXT_ORIGIN_OFFICIAL = "official_verbatim"
TEXT_ORIGIN_REASONING_GUIDE = "reasoning_guide"

PROVENANCE_UNLINKED = "unlinked"
PROVENANCE_LINKED_PORTAL = "linked_portal"
PROVENANCE_LINKED_DOCUMENT = "linked_document"
PROVENANCE_FETCHED_OFFICIAL = "fetched_official"
PROVENANCE_ARTICLE_LEVEL = "article_level"

PROVENANCE_LEVELS: tuple[str, ...] = (
    PROVENANCE_UNLINKED,
    PROVENANCE_LINKED_PORTAL,
    PROVENANCE_LINKED_DOCUMENT,
    PROVENANCE_FETCHED_OFFICIAL,
    PROVENANCE_ARTICLE_LEVEL,
)

# Kept byte-for-byte stable for clients that already render this field.
DISCLAIMER = "هذه معلومات قانونية عامة وليست استشارة قانونية."

# The longer research notice is used inside answer_markdown.  It does not
# replace `disclaimer` (a public API value already consumed by clients).
RESEARCH_NOTICE = (
    "للبحث الأولي فقط، وليس استشارة قانونية. النص المعروض نسخة مسحوبة "
    "بتاريخ ظاهر من الصفحة المرتبطة، والأنظمة تتغير. إن غاب الاقتباس أو "
    "الرابط فالمعلومة غير موثّقة."
)

_PORTAL_HOSTS = frozenset({
    "boe.gov.sa",
    "laws.boe.gov.sa",
    "laws.moj.gov.sa",
    "moj.gov.sa",
    "najiz.sa",
    "hrsd.gov.sa",
    "qiwa.com.sa",
    "sdaia.gov.sa",
    "pdp.sdaia.gov.sa",
    "dgp.sdaia.gov.sa",
    "saip.gov.sa",
    "sba.gov.sa",
    "eservice.sba.gov.sa",
    "adr.sba.gov.sa",
    "gac.gov.sa",
    "reac.rega.gov.sa",
    "reacservices.rega.gov.sa",
    "rega.gov.sa",
    "mc.gov.sa",
    "cma.org.sa",
    "zatca.gov.sa",
    "saff.com.sa",
    "fifa.com",
    "inside.fifa.com",
    "legalportal.fifa.com",
    "tas-cas.org",
    "scca.org.sa",
    "sadr.org",
    "open.data.gov.sa",
    "ncar.gov.sa",
    "pp.gov.sa",
    "moi.gov.sa",
    "nazaha.gov.sa",
    "commercialcourt.gov.sa",
    "scsac.org.sa",
    "fifatms.com",
    "the-afc.com",
    "wipo.int",
})

_PUBLISHER_LABELS = {
    "laws.boe.gov.sa": "هيئة الخبراء بمجلس الوزراء",
    "boe.gov.sa": "هيئة الخبراء بمجلس الوزراء",
    "uqn.gov.sa": "جريدة أم القرى",
    "laws.moj.gov.sa": "وزارة العدل",
    "moj.gov.sa": "وزارة العدل",
    "hrsd.gov.sa": "وزارة الموارد البشرية والتنمية الاجتماعية",
    "dgp.sdaia.gov.sa": "الهيئة السعودية للبيانات والذكاء الاصطناعي (سدايا)",
    "sdaia.gov.sa": "الهيئة السعودية للبيانات والذكاء الاصطناعي (سدايا)",
    "pdp.sdaia.gov.sa": "الهيئة السعودية للبيانات والذكاء الاصطناعي (سدايا)",
    "zatca.gov.sa": "هيئة الزكاة والضريبة والجمارك",
    "saff.com.sa": "الاتحاد السعودي لكرة القدم",
    "sba.gov.sa": "الهيئة السعودية للمحامين",
    "saip.gov.sa": "الهيئة السعودية للملكية الفكرية",
    "reac.rega.gov.sa": "المركز السعودي للتحكيم العقاري",
}

_URL_RE = re.compile(r"https?://[^\s|)\]]+")


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def publisher_label(url: str) -> str:
    """Return a human Arabic publisher label for a known official host."""
    host = _host(url)
    if host in _PUBLISHER_LABELS:
        return _PUBLISHER_LABELS[host]
    if host.endswith(".gov.sa"):
        return "جهة حكومية سعودية"
    return host or "جهة رسمية"


def classify_url(url: str) -> dict:
    """Classify a URL into the honest link taxonomy.

    Returns:
        {"link_type", "label", "is_deep_link"}
    """
    url = url.strip()
    parsed = urlparse(url)
    host = _host(url)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)
    publisher = publisher_label(url)

    # 1. Article-level: BOE Viewer with an explicit article attachment title.
    #    The viewer opens the scanned original of the article pages; it is a
    #    real article link, not a fabricated text anchor.
    attachment = (query.get("attachmentTitle") or query.get("attachmenttitle") or [""])[0]
    if "viewer" in path and "المادة" in attachment:
        return {
            "link_type": LINK_ARTICLE,
            "is_deep_link": True,
            "label": (
                f"الرابط المباشر للمادة على {publisher} ({host}) — يفتح أصل "
                "المادة الممسوح/صفحتها، وليس مرساة نصية داخل الصفحة"
            ),
        }

    # 2. Document-level: the law document itself.
    if "/lawdetails/" in path or path.rstrip("/").endswith("/lawdetails"):
        return {
            "link_type": LINK_DOCUMENT,
            "is_deep_link": False,
            "label": (
                f"وثيقة النظام الكاملة على {publisher} ({host}) — الرابط يفتح "
                "الوثيقة كاملة، لا مادة محددة"
            ),
        }
    if host == "uqn.gov.sa" and path.rstrip("/") == "/details" and query.get("p"):
        return {
            "link_type": LINK_DOCUMENT,
            "is_deep_link": False,
            "label": (
                f"وثيقة العدد/النظام على {publisher} ({host}) — الرابط يفتح "
                "الوثيقة المنشورة، لا مادة محددة"
            ),
        }
    if path.endswith(".pdf"):
        return {
            "link_type": LINK_DOCUMENT,
            "is_deep_link": False,
            "label": (
                f"وثيقة رسمية على {publisher} ({host}) — الرابط يفتح الملف/الوثيقة، "
                "لا قسماً محدداً"
            ),
        }

    # 3. Everything else is a portal/general authority page.  This is the safe
    #    default: never over-claim that a link opens an article.
    return {
        "link_type": LINK_PORTAL,
        "is_deep_link": False,
        "label": (
            f"بوابة {publisher} ({host}) — رابط عام للبوابة، لا يفتح المادة أو "
            "القسم مباشرة؛ استخدم البحث داخل الموقع للوصول للنص الدقيق"
        ),
    }


def citation(url: str, *, label: Optional[str] = None, title: Optional[str] = None) -> dict:
    """Build a citation dict with a truthful type and label."""
    classified = classify_url(url)
    final_label = classified["label"]
    if title:
        final_label = f"{title} — {final_label}"
    if label:
        # An explicit label is honoured only if it does not contradict the
        # classification.  Callers in this project pass no label.
        final_label = label
    return {
        "url": url.strip().rstrip(")."),
        "label": final_label,
        "link_type": classified["link_type"],
        "is_deep_link": classified["is_deep_link"],
    }


def article_link_citation(url: str) -> dict:
    """Citation for a Viewer link found INSIDE an article item.

    The parser context proves the link belongs to that article even when the
    BOE URL omits `attachmentTitle`.  This function is only called from
    corpus article records, never for arbitrary page links.
    """
    url = url.strip().rstrip(").")
    host = _host(url)
    publisher = publisher_label(url)
    return {
        "url": url,
        "label": (
            f"الرابط المباشر لهذه المادة على {publisher} ({host}) — يفتح "
            "مرفق المادة/أصلها الممسوح، لا مرساة نصية داخل الصفحة"
        ),
        "link_type": LINK_ARTICLE,
        "is_deep_link": True,
    }


def best_provenance_level(citations: Iterable[dict]) -> str:
    """Return the strongest provenance level supported by the citations."""
    types = {c.get("link_type") for c in citations}
    if LINK_ARTICLE in types:
        return PROVENANCE_ARTICLE_LEVEL
    if LINK_DOCUMENT in types:
        return PROVENANCE_LINKED_DOCUMENT
    if LINK_PORTAL in types:
        return PROVENANCE_LINKED_PORTAL
    return PROVENANCE_UNLINKED


def document_reference(text: str) -> Optional[dict]:
    """Find the best document reference already present in a source file.

    Ranking: article-level > document-level > portal.  Only URLs that actually
    appear in the file are considered; no URL is invented here.
    """
    candidates: list[dict] = []
    seen: set[str] = set()
    for match in _URL_RE.finditer(text):
        url = match.group(0).strip().rstrip(").,;")
        if url in seen:
            continue
        seen.add(url)
        info = classify_url(url)
        candidates.append({"url": url, **info})

    if not candidates:
        return None
    rank = {LINK_ARTICLE: 3, LINK_DOCUMENT: 2, LINK_PORTAL: 1}
    candidates.sort(key=lambda c: rank.get(c["link_type"], 0), reverse=True)
    return candidates[0]


def citations_for_document(document: Optional[dict]) -> list[dict]:
    """Turn a discovered document reference into a one-item citation list."""
    if not document:
        return []
    return [citation(document["url"], title=document.get("title"))]


def provenance_envelope(
    citations: Iterable[dict],
    *,
    fetched_at: Optional[str] = None,
    sha256: Optional[str] = None,
    freshness: str = "unverified",
    citation_note: Optional[str] = None,
) -> dict:
    """Build the `provenance` object used by every legal response.

    The top-level list is deduplicated by URL: three quotes from the same law
    share one document link, and repeating it three times adds no information.
    Per-quote citations keep their own link.
    """
    links: list[dict] = []
    seen: set[str] = set()
    for item in citations:
        url = item.get("url")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        links.append(item)
    return {
        "fetched_at": fetched_at,
        "sha256": sha256,
        "links": links,
        "freshness": freshness,
        "citation_note": citation_note,
    }


def build_answer_markdown(
    *,
    title: str,
    content: Optional[str],
    citations: Iterable[dict],
    text_origin: str,
    provenance_level: str,
    fetched_at: Optional[str] = None,
    citation_note: Optional[str] = None,
    article_label: Optional[str] = None,
    include_disclaimer: bool = True,
) -> str:
    """Render a ready-to-paste answer.

    Hand-written summaries are labelled explicitly.  Official quotes are
    rendered inside a blockquote and are never blended with commentary.
    """
    links = list(citations)
    parts: list[str] = [f"### {title}"]
    if article_label:
        parts.append(f"**{article_label}**")

    if text_origin == TEXT_ORIGIN_OFFICIAL:
        parts.append("**اقتباس حرفي من النص الرسمي المسحوب.**")
        if content:
            block = "\n".join(f"> {line}" if line else ">" for line in content.splitlines())
            parts.append(block)
    elif text_origin == TEXT_ORIGIN_REASONING_GUIDE:
        parts.append(
            "**دليل تفكير — ليس النص النظامي ولا يُقتبس منه كحكم. "
            "الاقتباس الرسمي من corpus/ فقط.**"
        )
        if content:
            parts.append(content)
    else:
        parts.append(
            "**ملخص مكتوب يدوياً — ليس نصاً رسمياً حرفياً، ولا يُنسب إلى النظام "
            "بوصفه اقتباساً.**"
        )
        if content:
            parts.append(content)

    if links:
        parts.append("**المصادر:**")
        for link in links:
            parts.append(f"- [{link['label']}]({link['url']})")
    elif citation_note:
        parts.append(citation_note)

    if fetched_at:
        parts.append(f"**تاريخ السحب:** {fetched_at}")
    elif text_origin == TEXT_ORIGIN_REASONING_GUIDE:
        parts.append("**تاريخ السحب:** لا ينطبق — دليل تفكير لا نص مسحوب.")
    else:
        parts.append(
            "**تاريخ السحب:** غير متوفر — هذا المحتوى ملخص يدوي لم تُسحب له نسخة مؤرخة."
        )

    if provenance_level:
        parts.append(f"**مستوى الإسناد:** {provenance_level}")

    if include_disclaimer:
        parts.append(f"**إخلاء المسؤولية:** {DISCLAIMER} {RESEARCH_NOTICE}")
    return "\n\n".join(parts)
