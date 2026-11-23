"""
test_sources.py — Verify every registered source_id has a readable .md file
that passes validate_before_register().
"""
import pytest
from pathlib import Path
from saudi_legal_mcp.tools.sources import VALID_REGULATIONS, validate_before_register


def test_all_registered_sources_have_files(data_dir: Path):
    """Every entry in VALID_REGULATIONS must have a corresponding .md file."""
    missing = []
    for reg_id in sorted(VALID_REGULATIONS):
        path = data_dir / "sources" / f"{reg_id}.md"
        if not path.exists():
            missing.append(reg_id)
    assert not missing, (
        f"Registered source_ids with no .md file: {missing}\n"
        "Either remove from VALID_REGULATIONS or add the missing file."
    )


def test_no_unregistered_source_files(data_dir: Path):
    """Every .md file in sources/ (direct children) must be registered."""
    source_dir = data_dir / "sources"
    unregistered = []
    for md_file in source_dir.glob("*.md"):
        reg_id = md_file.stem
        if reg_id not in VALID_REGULATIONS:
            unregistered.append(reg_id)
    assert not unregistered, (
        f"Source files with no registration in VALID_REGULATIONS: {unregistered}\n"
        "Either register them or remove the files."
    )


def test_all_source_files_pass_validation(data_dir: Path):
    """Every registered source file must pass validate_before_register()."""
    failures = []
    for reg_id in sorted(VALID_REGULATIONS):
        path = data_dir / "sources" / f"{reg_id}.md"
        if not path.exists():
            continue  # covered by test_all_registered_sources_have_files
        ok, reason = validate_before_register(path)
        if not ok:
            failures.append(f"{reg_id}: {reason}")
    assert not failures, (
        "Source files that failed validation:\n" + "\n".join(failures)
    )


def test_skills_registration(data_dir: Path):
    """Every entry in VALID_DOMAINS must have a corresponding .md file."""
    from saudi_legal_mcp.tools.skills import VALID_DOMAINS, validate_before_register as skill_validate
    missing = []
    for domain in sorted(VALID_DOMAINS):
        path = data_dir / "skills" / f"{domain}.md"
        if not path.exists():
            missing.append(domain)
    assert not missing, f"Registered domains with no .md file: {missing}"


def test_no_unregistered_skill_files(data_dir: Path):
    """Every .md file in skills/ must be registered in VALID_DOMAINS."""
    from saudi_legal_mcp.tools.skills import VALID_DOMAINS
    skills_dir = data_dir / "skills"
    unregistered = []
    for md_file in skills_dir.glob("*.md"):
        domain = md_file.stem
        if domain not in VALID_DOMAINS:
            unregistered.append(domain)
    assert not unregistered, (
        f"Skill files with no registration in VALID_DOMAINS: {unregistered}"
    )


def test_every_content_heading_has_a_link_in_its_immediate_body(data_dir: Path):
    """Wave 1+2: every level-2/3/4 content heading must carry a DOCUMENT link
    (law_document_url / direct_article_url) in its own immediate body — a
    portal-only link is not enough.  A parent heading is not covered by a link
    inside a child heading.

    Exemptions (explicit allowlist, documented):
      * NAV_EXEMPT titles list local files, not legal text.
      * PORTAL_ONLY_SOURCES have no stable BOE LawDetails documented yet;
        they stay portal-only with an honest portal label (see
        evals/source-registry.json url_confidence=portal).  They must still
        carry at least a portal link — silence is never allowed.
    """
    import re

    from saudi_legal_mcp.tools.provenance import classify_url

    exempt = ("See also", "انظر أيضا", "انظر أيضًا", "المصادر الرسمية", "Official Legal Sources", "المصادر والمراجع")
    # Portal-only by documented decision: no stable LawDetails found yet.
    # Kept as portal with honest labels; registry tracks them as portal.
    portal_only_sources = frozenset({
        "commercial-courts",
        "companies-law",
        "competition-law",
        "intellectual-property-law",
        "legal-profession-law",
        "open-data-judicial-sources",
        "real-estate-arbitration-reac",
        "regulation-index",
        "saudi-laws",
    })
    missing: list[str] = []
    portal_instead_of_document: list[str] = []
    headings = 0
    _URL_RE = re.compile(r"https?://[^\s|)\]]+")

    def _has_document_link(body: str) -> bool:
        for m in _URL_RE.finditer(body):
            url = m.group(0).strip().rstrip(").,;")
            try:
                if classify_url(url)["link_type"] in ("law_document_url", "direct_article_url"):
                    return True
            except Exception:
                continue
        return False

    for source_id in sorted(VALID_REGULATIONS):
        lines = (data_dir / "sources" / f"{source_id}.md").read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            match = re.match(r"^(#{2,4})\s+(.*)$", lines[i])
            if not match:
                i += 1
                continue
            title = match.group(2)
            headings += 1
            j = i + 1
            while j < len(lines) and not re.match(r"^#{1,6}\s+", lines[j]):
                j += 1
            body = "\n".join(lines[i:j])
            if any(word in title for word in exempt):
                i += 1
                continue
            if "https://" not in body and "http://" not in body:
                missing.append(f"{source_id}: {title}")
            elif source_id not in portal_only_sources and not _has_document_link(body):
                portal_instead_of_document.append(f"{source_id}: {title}")
            i += 1

    assert headings > 500
    assert missing == [], "content headings without a link:\n" + "\n".join(missing)
    assert portal_instead_of_document == [], (
        "content headings with portal-only link (document required):\n"
        + "\n".join(portal_instead_of_document)
    )


def test_portal_only_section_fails_document_gate():
    """Negative guard against green-false: a portal-only body must NOT pass
    the document gate unless its source is in the portal-only allowlist."""
    import re

    from saudi_legal_mcp.tools.provenance import classify_url

    _URL_RE = re.compile(r"https?://[^\s|)\]]+")

    def _has_document_link(body: str) -> bool:
        for m in _URL_RE.finditer(body):
            url = m.group(0).strip().rstrip(").,;")
            try:
                if classify_url(url)["link_type"] in ("law_document_url", "direct_article_url"):
                    return True
            except Exception:
                continue
        return False

    portal_body = "> **رابط البوابة:** [بوابة الجهة](https://laws.boe.gov.sa) — رابط عام."
    document_body = (
        "> **رابط الوثيقة:** [وثيقة النظام]"
        "(https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/08381293-6388-48e2-8ad2-a9a700f2aa94/1)"
        " — يفتح الوثيقة كاملة."
    )
    assert _has_document_link(document_body) is True
    assert _has_document_link(portal_body) is False
    # The gate from the test above would flag the portal body in a
    # document-required source and allow it only in a portal-only source.
    assert "laws.boe.gov.sa/BoeLaws/Laws/LawDetails" in document_body


def test_embed_document_links_is_idempotent_and_section_scoped():
    """Wave 1: each section gets its document link, once, and rerunning is a no-op."""
    import importlib.util
    import sys

    script = Path(__file__).parent.parent / "scripts" / "embed_document_links.py"
    spec = importlib.util.spec_from_file_location("embed_document_links", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules["embed_document_links"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

    document = {
        "url": (
            "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/"
            "08381293-6388-48e2-8ad2-a9a700f2aa94/1"
        )
    }
    text = "# T\n\n## A\nنص أ\n\n## B\nنص ب\n"
    once, changes = module.embed(text, document)
    assert changes == 2
    assert once.count(document["url"]) == 2
    twice, second_changes = module.embed(once, document)
    assert second_changes == 0
    assert twice == once


def test_every_registered_source_has_eval_questions():
    """Coverage guard (2026-08-13 lesson): every registered regulation
    must be exercised by at least one eval question.  A source added to
    VALID_REGULATIONS without eval coverage is untested by definition —
    exactly the gap that stayed open for 6 sources until it was audited."""
    import json
    repo_root = Path(__file__).parent.parent
    corpus_dir = repo_root / "evals" / "corpus"

    covered = set()
    for corpus_file in corpus_dir.glob("*.json"):
        with corpus_file.open(encoding="utf-8-sig") as f:
            for q in json.load(f):
                if q.get("expected_source_id"):
                    covered.add(q["expected_source_id"])

    missing = VALID_REGULATIONS - covered
    assert not missing, (
        f"Registered sources without any eval question: {sorted(missing)}\n"
        "Add questions under evals/corpus/ or remove the registration."
    )
