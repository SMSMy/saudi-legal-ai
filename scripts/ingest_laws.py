"""
ingest_laws.py — explicit, local-only ingestion of Saudi law pages into corpus/.

This script is NOT imported by the retrieval server.  It is the only place in
the repository that performs network I/O for legal text, and it runs only when
a human invokes it.

Examples (from inside the Kingdom; BOE is blocked from GitHub CI):

    python scripts/ingest_laws.py --source labor-law
    python scripts/ingest_laws.py --source civil-transactions-law
    python scripts/ingest_laws.py --source pdpl --source pdpl-exec-regulations

Re-parsing a saved page (no network):

    python scripts/ingest_laws.py --source labor-law --input saved.html

Safety gate: a page is rejected if the parser finds no article structure, an
unexpectedly low article count, an empty in-force article, or HTML tags in the
article text.  Nothing is written unless the whole page passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from saudi_legal_mcp.tools.article_numbers import parse_arabic_article_number  # noqa: E402

try:
    from bs4 import BeautifulSoup, Tag  # noqa: E402
except ImportError:  # pragma: no cover - optional ingest dependency
    print(
        "ERROR: beautifulsoup4 is required for ingestion.\n"
        "Install it with: pip install beautifulsoup4",
        file=sys.stderr,
    )
    raise SystemExit(2)

ALLOWED_HOSTS = {
    "laws.boe.gov.sa",
    "www.boe.gov.sa",
    "boe.gov.sa",
    "uqn.gov.sa",
    "www.uqn.gov.sa",
}

SOURCES = {
    "labor-law": {
        "url": "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/08381293-6388-48e2-8ad2-a9a700f2aa94/1",
        "kind": "boe",
        "title_ar": "نظام العمل",
        "instrument": "المرسوم الملكي م/51 بتاريخ 23/8/1426هـ وتعديلاته",
        "publisher": "هيئة الخبراء بمجلس الوزراء",
        "min_articles": 200,
        "max_articles": 270,
    },
    "pdpl": {
        "url": "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/b7cfae89-828e-4994-b167-adaa00e37188/1",
        "kind": "boe",
        "title_ar": "نظام حماية البيانات الشخصية",
        "instrument": "المرسوم الملكي م/19 بتاريخ 9/2/1443هـ",
        "publisher": "هيئة الخبراء بمجلس الوزراء",
        "min_articles": 30,
        "max_articles": 60,
    },
    "civil-transactions-law": {
        "url": "https://uqn.gov.sa/details?p=23125",
        "kind": "uqn",
        "title_ar": "نظام المعاملات المدنية",
        "instrument": "المرسوم الملكي م/191 بتاريخ 29/11/1444هـ",
        "publisher": "جريدة أم القرى",
        "min_articles": 700,
        "max_articles": 730,
    },
    "pdpl-exec-regulations": {
        "url": "https://uqn.gov.sa/details?p=23595",
        "kind": "uqn",
        "title_ar": "اللائحة التنفيذية لنظام حماية البيانات الشخصية",
        "instrument": "قرار رئيس مجلس إدارة سدايا رقم (298/م/ق) بتاريخ 1445/2/22هـ",
        "publisher": "جريدة أم القرى",
        "min_articles": 30,
        "max_articles": 60,
    },
}

_WS_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u00ad", "").replace("\u0640", "").replace("\u200f", "")
    value = value.replace("\u00a0", " ")
    return _WS_RE.sub(" ", value).strip()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def corpus_content_sha256(articles: list[dict]) -> str:
    """Stable digest of article content/status/links (ignores fetch timestamps)."""
    payload = [
        {
            "article": a.get("article"),
            "text_sha256": a.get("sha256"),
            "status": a.get("status"),
            "article_url": a.get("article_url"),
        }
        for a in articles
    ]
    return sha256_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def fetch(url: str, timeout: int = 90) -> bytes:
    host = urlparse(url).netloc.lower()
    if host not in ALLOWED_HOSTS:
        raise SystemExit(f"Refusing to fetch non-allowlisted host: {host}")
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "ar,en;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - allowlist checked
        final_host = urlparse(response.geturl()).netloc.lower()
        if final_host not in ALLOWED_HOSTS:
            raise SystemExit(f"Redirected outside allowlist: {final_host}")
        data = response.read(6_000_000)
    if len(data) >= 6_000_000:
        raise SystemExit("Page exceeds 6 MB limit; refusing to ingest.")
    return data


def _is_article_heading(text: str) -> bool:
    return clean_text(text).startswith("المادة")


def _first_article_heading(item: Tag) -> Optional[str]:
    for heading in item.find_all("h3"):
        text = clean_text(heading.get_text(" ", strip=True))
        if _is_article_heading(text):
            return text
    return None


def _direct_html_containers(item: Tag) -> list[Tag]:
    """Return HTMLContainer nodes that are current text, not amendment popups."""
    containers: list[Tag] = []
    for node in item.find_all("div", class_="HTMLContainer"):
        if node.find_parent(class_="popup-list") is not None:
            continue
        if node.find_parent(class_="article_btns") is not None:
            continue
        containers.append(node)
    return containers


def _popup_text(item: Tag) -> Optional[str]:
    popup = item.select_one(".popup-list")
    if popup is None:
        return None
    text = clean_text(popup.get_text("\n", strip=True))
    return text or None


def _article_url(item: Tag, base_url: str) -> Optional[str]:
    for link in item.find_all("a", href=True):
        href = link.get("href", "")
        if "/Viewer/" not in href:
            continue
        if link.find_parent(class_="popup-list") is not None:
            continue
        return urljoin(base_url, href)
    return None


def _chapter_for(item: Tag) -> Optional[str]:
    for heading in item.find_all_previous("h3"):
        text = clean_text(heading.get_text(" ", strip=True))
        if not text:
            continue
        if text.startswith(("الباب", "الفصل", "الفرع", "القسم")):
            return text
        if _is_article_heading(text):
            # We reached the previous article before a structural heading.
            continue
    return None


_INSTRUCTION_MARKERS = (
    "ليكون النص",
    "لتكون بالنص",
    "ليكون بالنص",
    "إضافة مادة",
    "أضيفت هذه المادة",
)


def extract_operative_text(text: str) -> tuple[str, Optional[str]]:
    """Extract the article text from a BOE amendment/add instruction.

    Some BOE pages expose an added article as:
        "- إضافة مادة تحمل الرقم (...) ليكون النص كالآتي: " النص " ..."
    Storing that instruction as the article text is wrong even though its hash
    is stable.  This function returns (operative_text, amendment_note).  If no
    instruction shape is found, it returns the original text unchanged.
    """
    cleaned = clean_text(text)
    if not any(marker in cleaned for marker in _INSTRUCTION_MARKERS):
        return cleaned, None

    markers = (
        "بالنص الآتي:",
        "بالنص الآتي :",
        "النص كالآتي:",
        "النص كالآتي :",
        "ليكون النص كالآتي:",
        "لتكون بالنص الآتي:",
        "ليكون النص كالآتي :",
        "لتكون بالنص الآتي :",
    )
    start = -1
    for marker in markers:
        idx = cleaned.find(marker)
        if idx != -1:
            start = idx + len(marker)
            break
    if start == -1:
        return cleaned, None

    quote_start = -1
    for quote in ('"', "“", "«"):
        idx = cleaned.find(quote, start)
        if idx != -1 and (quote_start == -1 or idx < quote_start):
            quote_start = idx
    if quote_start == -1:
        return cleaned, None

    quote_end = -1
    for quote in ('"', "”", "»"):
        idx = cleaned.rfind(quote)
        if idx > quote_start:
            quote_end = max(quote_end, idx)
    if quote_end == -1:
        return cleaned, None

    operative = clean_text(cleaned[quote_start + 1:quote_end]).lstrip("- ").strip()
    if len(operative) < 20:
        return cleaned, None
    if any(marker in operative for marker in ("ليكون النص", "لتكون بالنص", "إضافة مادة")):
        return cleaned, None
    return operative, cleaned


def _instrument_history(history: Optional[str]) -> list[dict]:
    if not history:
        return []
    found: list[dict] = []
    pattern = re.compile(
        r"(?:المرسوم الملكي|مرسوم ملكي|قرار)[^()]{0,40}?(?:رقم\s*)?"
        r"\(\s*([^)]+?)\s*\)[^()]{0,40}?"
        r"(?:وتاريخ|الصادر بتاريخ|بتاريخ)\s*"
        r"([0-9]{1,4}\s*/\s*[0-9]{1,2}\s*/\s*[0-9]{1,4})(?:\s*هـ?)?"
    )
    for match in pattern.finditer(history):
        instrument = re.sub(r"\s*/\s*", "/", clean_text(match.group(1)))
        date = re.sub(r"\s*/\s*", "/", clean_text(match.group(2)))
        parts = date.split("/")
        if len(parts) == 3 and len(parts[0]) <= 2 and len(parts[2]) >= 4:
            # BOE uses both Y/M/D and D/M/Y; store Y/M/D consistently.
            date = "/".join((parts[2], parts[1], parts[0]))
        item = {"instrument": instrument, "date": date}
        if item not in found:
            found.append(item)
    return found


def parse_boe(html_bytes: bytes, source: dict, source_key: str) -> dict:
    soup = BeautifulSoup(html_bytes, "html.parser", from_encoding="utf-8")
    items = soup.select("div.article_item")
    if not items:
        raise ValueError("No div.article_item found — parser did not recognize the page.")

    entries: list[dict] = []
    skipped_headings = 0
    empty_in_force = 0
    duplicate_numbers = 0
    seen_numbers: dict[str, int] = {}

    for item in items:
        title = _first_article_heading(item)
        if title is None:
            skipped_headings += 1
            continue
        number = parse_arabic_article_number(title)
        if number is None:
            # Parenthetical old-number notes are history, not current articles.
            if "حاليا" in clean_text(title):
                continue
            raise ValueError(f"Unparseable article heading: {title!r}")

        if item.find(["script", "style", "iframe", "object", "embed"]):
            raise ValueError(
                f"Active content found inside article {number}; refusing to ingest."
            )

        classes = item.get("class") or []
        canceled = "canceled-article" in classes
        changed = "changed-article" in classes
        containers = _direct_html_containers(item)
        text = clean_text("\n".join(c.get_text("\n", strip=True) for c in containers))
        if not text:
            # Some BOE pages put the current text in a direct <p>.
            paragraphs = [
                p for p in item.find_all("p", recursive=False)
                if p.find_parent(class_="popup-list") is None
            ]
            text = clean_text("\n".join(p.get_text("\n", strip=True) for p in paragraphs))

        history = _popup_text(item)
        if not text and history:
            # Do not invent: if the page only exposes history, keep it as a
            # non-quotable record rather than presenting amendment prose as law.
            text = ""

        if not canceled and not text:
            empty_in_force += 1
        if _TAG_RE.search(text):
            raise ValueError(f"HTML tag survived in article {number}: {text[:120]!r}")

        raw_text = text
        status = "canceled" if canceled else ("amended" if changed else "in_force")
        addition_marker = clean_text(f"{text[:200]} {history or ''}")
        addition_marker = re.sub(r"[\u064B-\u0652\u0670]", "", addition_marker)
        if "أضيفت هذه المادة" in addition_marker or "إضافة مادة" in addition_marker:
            status = "added"

        amendment_note: Optional[str] = None
        if status in ("added", "amended"):
            operative, amendment_note = extract_operative_text(text)
            if amendment_note is not None:
                text = operative
                if not text:
                    empty_in_force += 1

        # The original amendment/add instruction must survive.  When BOE has
        # no popup (e.g. articles 233-235), the extracted instruction itself is
        # the history; it is never moved out of `amendment_history`.
        effective_history = history or amendment_note
        instruments = _instrument_history(
            " ".join(part for part in (effective_history, raw_text) if part)
        )
        article = {
            "id": f"{source_key}/art-{number}",
            "article": str(number),
            "article_label": title.rstrip(" :"),
            "text": text,
            "text_origin": "official_verbatim",
            "status": status,
            "chapter": _chapter_for(item),
            "instrument": source["instrument"],
            "amendment_history": effective_history,
            "amendment_note": amendment_note,
            "amendment_instruments": instruments,
            "article_url": _article_url(item, source["url"]),
            "document_url": source["url"],
            "fetched_at": None,  # filled at corpus level
            "fetched_by": "local",
            "sha256": sha256_text(text),
        }

        key = str(number)
        if key in seen_numbers:
            duplicate_numbers += 1
            previous_index = seen_numbers[key]
            previous = entries[previous_index]
            # Prefer the later "added" version if the page appends a replacement;
            # otherwise keep the first (the earlier entry is the operative one).
            if status == "added" and previous.get("status") != "added":
                previous["duplicate_of"] = article["id"]
                article["duplicate_versions"] = [previous]
                entries[previous_index] = article
            else:
                previous.setdefault("duplicate_versions", []).append(article)
            continue

        seen_numbers[key] = len(entries)
        entries.append(article)

    if len(entries) < source["min_articles"] or len(entries) > source["max_articles"]:
        raise ValueError(
            f"Article count {len(entries)} outside safety range "
            f"{source['min_articles']}..{source['max_articles']}"
        )
    if empty_in_force:
        raise ValueError(f"{empty_in_force} in-force articles have empty text.")

    instruction_left = [
        a["article"] for a in entries
        if any(marker in a.get("text", "") for marker in _INSTRUCTION_MARKERS)
    ]
    if instruction_left:
        raise ValueError(
            "Amendment instruction survived as article text: "
            + ", ".join(instruction_left[:10])
        )

    fetched_at = datetime.now(timezone.utc).isoformat()
    for article in entries:
        article["fetched_at"] = fetched_at

    return {
        "schema_version": "1.0",
        "law": source_key,
        "title_ar": source["title_ar"],
        "instrument": source["instrument"],
        "publisher": source["publisher"],
        "document_url": source["url"],
        "fetched_at": fetched_at,
        "fetched_by": "local",
        "source_sha256": hashlib.sha256(html_bytes).hexdigest(),
        "content_sha256": corpus_content_sha256(entries),
        "provenance_level": "fetched_official",
        "article_entries": len(items),
        "article_count": len(entries),
        "skipped_headings": skipped_headings,
        "duplicate_numbers_merged": duplicate_numbers,
        "articles": entries,
        "safety": {
            "parser": "boe_article_item_v1",
            "empty_in_force_articles": empty_in_force,
            "html_tags_in_text": False,
            "article_count_ok": True,
        },
    }


def parse_uqn(html_bytes: bytes, source: dict, source_key: str) -> dict:
    soup = BeautifulSoup(html_bytes, "html.parser", from_encoding="utf-8")
    desc = soup.select_one("div.article-desc")
    if desc is None:
        raise ValueError("No div.article-desc found — parser did not recognize the page.")
    lines = [clean_text(line) for line in desc.get_text("\n", strip=True).splitlines()]
    lines = [line for line in lines if line]

    entries: list[dict] = []
    current: Optional[dict] = None
    chapter: Optional[str] = None
    empty_in_force = 0

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        text = clean_text("\n".join(current.pop("_body")))
        current["text"] = text
        current["sha256"] = sha256_text(text)
        if not text:
            nonlocal empty_in_force
            empty_in_force += 1
        entries.append(current)
        current = None

    for line in lines:
        if line.startswith("المادة"):
            number_part = line.split(":", 1)[0]
            number = parse_arabic_article_number(number_part)
            if number is None:
                raise ValueError(f"Unparseable article heading: {line!r}")
            flush()
            title_part = line.split(":", 1)[1].strip() if ":" in line else ""
            current = {
                "id": f"{source_key}/art-{number}",
                "article": str(number),
                "article_label": line.rstrip(" :"),
                "article_title": title_part,
                "text_origin": "official_verbatim",
                "status": "in_force",
                "chapter": chapter,
                "instrument": source["instrument"],
                "amendment_history": None,
                "amendment_instruments": [],
                "article_url": None,
                "document_url": source["url"],
                "fetched_at": None,
                "fetched_by": "local",
                "_body": [],
            }
            continue

        if line.startswith(("الباب", "باب", "الفصل", "الفرع", "القسم", "التمهيد")):
            flush()
            chapter = line
            continue

        if current is not None:
            current["_body"].append(line)

    flush()

    if len(entries) < source["min_articles"] or len(entries) > source["max_articles"]:
        raise ValueError(
            f"Article count {len(entries)} outside safety range "
            f"{source['min_articles']}..{source['max_articles']}"
        )
    if empty_in_force:
        raise ValueError(f"{empty_in_force} in-force articles have empty text.")
    numbers = [int(a["article"]) for a in entries]
    if sorted(numbers) != list(range(1, len(entries) + 1)):
        raise ValueError("Article numbers are not contiguous from 1; refusing to ingest.")

    fetched_at = datetime.now(timezone.utc).isoformat()
    for article in entries:
        article["fetched_at"] = fetched_at
        if _TAG_RE.search(article["text"]):
            raise ValueError(f"HTML tag survived in article {article['article']}")

    return {
        "schema_version": "1.0",
        "law": source_key,
        "title_ar": source["title_ar"],
        "instrument": source["instrument"],
        "publisher": source["publisher"],
        "document_url": source["url"],
        "fetched_at": fetched_at,
        "fetched_by": "local",
        "source_sha256": hashlib.sha256(html_bytes).hexdigest(),
        "content_sha256": corpus_content_sha256(entries),
        "provenance_level": "fetched_official",
        "article_count": len(entries),
        "articles": entries,
        "safety": {
            "parser": "uqn_article_desc_v1",
            "empty_in_force_articles": empty_in_force,
            "html_tags_in_text": False,
            "contiguous_numbers": True,
        },
    }


def write_corpus(source_key: str, corpus: dict, out_dir: Path) -> Path:
    """Write the corpus, preserving the previous version on change.

    A changed page never replaces history silently: the previous successful
    file is copied to `versions/<source>/<fetched_at>.json`, and the new file
    points at it through `supersedes`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{source_key}.json"

    if out_path.exists():
        try:
            previous = json.loads(out_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous = None

        if previous:
            same_content = previous.get("content_sha256") == corpus.get("content_sha256")
            if same_content:
                # The legal text did not change (the page bytes may still differ
                # because of chrome/session tokens).  Update the fetch stamp but
                # do not create a meaningless version.
                corpus["supersedes"] = previous.get("supersedes")
            else:
                versions_dir = out_dir / "versions" / source_key
                versions_dir.mkdir(parents=True, exist_ok=True)
                stamp = re.sub(
                    r"[^0-9A-Za-z_.-]+",
                    "-",
                    str(previous.get("fetched_at") or "unknown"),
                ).strip("-")
                version_path = versions_dir / f"{stamp or 'unknown'}.json"
                if not version_path.exists():
                    version_path.write_text(
                        json.dumps(previous, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                corpus["supersedes"] = {
                    "fetched_at": previous.get("fetched_at"),
                    "source_sha256": previous.get("source_sha256"),
                    "content_sha256": previous.get("content_sha256"),
                    "version_file": str(version_path.relative_to(out_dir)).replace("\\", "/"),
                }

    out_path.write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest official Saudi law pages into corpus/.")
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        choices=sorted(SOURCES),
        help="Source key to ingest (repeatable).",
    )
    parser.add_argument(
        "--input",
        help="Optional saved HTML file to parse instead of fetching (single source only).",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "saudi_legal_mcp" / "data" / "corpus"),
        help="Output corpus directory.",
    )
    args = parser.parse_args()

    if args.input and len(args.source) != 1:
        parser.error("--input can only be used with exactly one --source")

    out_dir = Path(args.out)
    for source_key in args.source:
        source = SOURCES[source_key]
        if args.input:
            html_bytes = Path(args.input).read_bytes()
        else:
            print(f"[ingest] fetching {source['url']}", file=sys.stderr)
            html_bytes = fetch(source["url"])

        if source["kind"] == "boe":
            corpus = parse_boe(html_bytes, source, source_key)
        else:
            corpus = parse_uqn(html_bytes, source, source_key)

        path = write_corpus(source_key, corpus, out_dir)
        print(
            f"[ingest] {source_key}: {corpus['article_count']} articles "
            f"({corpus['safety']['empty_in_force_articles']} empty) -> {path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
