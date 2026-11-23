"""
amendments.py — structured amendment operations and v1 composition.

Pure local logic (no network): the composer works ONLY on the structured
`amendments[]` rows built by scripts/build_amendments.py from the corpus
histories.  It never fetches, never guesses, and never presents composed
text as an official verbatim quote.

Plan (v1) composition rules:
  - article/replace or article/insert with validated parse → composed
    candidate, but consolidation_status stays `needs_review` until a
    licensed review or an official resync.  `verified` is never assigned
    by code in v1.
  - paragraph/*, insert-position rows, word substitutions, multi-article
    restructures → consolidation_status `needs_review` (paragraph ops
    require per-case documented human review — no exception).
  - any failed op → consolidation_status `failed` (composition refused).
  - in_force rows and pure addition rows → `not_required`.
"""
from __future__ import annotations

import hashlib
import math
from typing import Optional

# Operations the v1 composer is allowed to apply automatically.
_V1_AUTO_SCOPES = ("article",)
_V1_AUTO_OPS = ("replace", "insert")

_VALID_STATUSES = ("needs_review", "failed", "not_required")


def hijri_to_iso(year: int, month: int, day: int) -> str:
    """Arithmetic (Kuwaiti algorithm) Hijri → ISO Gregorian.

    Validated against the Saudi-announced Ramadan 1 1446 = 2025-03-01.
    Deterministic and local; documented as arithmetic (may differ ±1 day
    from tabular Umm al-Qura in edge months — ordering is unaffected).
    """
    jd = (
        day
        + math.ceil(29.5 * (month - 1))
        + (year - 1) * 354
        + math.floor((3 + 11 * year) / 30)
        + 1948439.5
    ) - 1
    jd = jd + 0.5
    z = math.floor(jd)
    if z >= 2299161:
        alpha = math.floor((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - math.floor(alpha / 4)
    else:
        a = z
    b = a + 1524
    c = math.floor((b - 122.1) / 365.25)
    d = math.floor(365.25 * c)
    e = math.floor((b - d) / 30.6001)
    gday = b - d - math.floor(30.6001 * e)
    gmonth = e - 1 if e < 14 else e - 13
    gyear = c - 4716 if gmonth > 2 else c - 4715
    return f"{gyear:04d}-{gmonth:02d}-{gday:02d}"


def parse_hijri_date(text: str) -> Optional[tuple[int, int, int]]:
    """Parse 'Y/M/D' or 'D/M/Y' Hijri fragments; None when ambiguous."""
    import re

    m = re.search(r"(\d{1,4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,4})", text)
    if not m:
        return None
    a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if a > 100:  # Y/M/D (e.g. 1446/8/20)
        y, mo, d = a, b, c
    elif c > 100:  # D/M/Y (e.g. 5/6/1436)
        d, mo, y = a, b, c
    else:
        return None
    if not (1 <= mo <= 12 and 1 <= d <= 30 and 1300 <= y <= 1500):
        return None
    return (y, mo, d)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sort_key(op: dict) -> tuple[str, int]:
    return (op.get("effective_on_iso") or "9999-99-99", int(op.get("effective_order", 0)))


def summarize_operation(op: dict) -> str:
    """One-line Arabic description of a structured operation."""
    scope, action = op.get("scope"), op.get("op")
    target = op.get("target")
    if scope == "article" and action == "replace":
        return "استبدال كامل للمادة"
    if scope == "article" and action == "insert":
        return "إضافة مادة جديدة"
    if scope == "paragraph" and action == "replace":
        return f"تعديل الفقرة {target}" if target else "تعديل فقرة"
    if scope == "paragraph" and action == "insert":
        after = op.get("insert_after")
        label = f"«{target}»" if target else "فقرة"
        return f"إضافة {label}" + (f" بعد {after}" if after else " (الموضع غير مؤكد)")
    if scope == "paragraph" and target == "lexical":
        pairs = op.get("replacements", [])
        if pairs:
            return "استبدال لفظي: " + "؛ ".join(
                f"«{p.get('old')}» ← «{p.get('new')}»" for p in pairs[:3]
            )
        return "استبدال لفظي"
    if scope == "article" and target == "restructure":
        return "إعادة هيكلة عبر مواد (لا تُركّب آليًا)"
    return f"{scope}/{action}"


def compose(article: dict) -> dict:
    """Compose the v1 consolidation outcome for one article row.

    Never assigns `verified`.  Returns the consolidation_* mapping to be
    stored on the article (consolidated_text present only for fully
    validated article-scope chains, still `needs_review`).
    """
    status = article.get("status", "in_force")
    ops = list(article.get("amendments") or [])

    if status in ("in_force",) or not ops:
        return {
            "consolidated_text": None,
            "consolidation_method": None,
            "consolidation_sha256": None,
            "consolidation_status": "not_required",
            "consolidation_note": None,
        }
    if status == "added":
        # Pure addition rows: the pulled text is already the operative
        # text; the op is informational.  Nothing to compose.
        return {
            "consolidated_text": None,
            "consolidation_method": None,
            "consolidation_sha256": None,
            "consolidation_status": "not_required",
            "consolidation_note": "addition row: pulled text is operative; op is informational",
        }

    ordered = sorted(ops, key=sort_key)
    if any(op.get("parse_status") == "failed" for op in ordered):
        return {
            "consolidated_text": None,
            "consolidation_method": None,
            "consolidation_sha256": None,
            "consolidation_status": "failed",
            "consolidation_note": "refused: at least one operation failed to parse — no guessing",
        }

    non_auto = [
        op for op in ordered
        if not (
            op.get("scope") in _V1_AUTO_SCOPES
            and op.get("op") in _V1_AUTO_OPS
            and op.get("parse_status") == "validated"
            and (op.get("quoted_text") or "").strip()
        )
    ]
    if non_auto:
        kinds = sorted({summarize_operation(op) for op in non_auto})
        return {
            "consolidated_text": None,
            "consolidation_method": None,
            "consolidation_sha256": None,
            "consolidation_status": "needs_review",
            "consolidation_note": (
                "v1 composes article-scope validated ops only; "
                "withheld: " + "؛ ".join(kinds)
            ),
        }

    # Fully validated article-scope chain: compose in effective order.
    # Still needs_review — v1 code never marks verified.
    text: Optional[str] = None
    applied: list[str] = []
    for op in ordered:
        quoted = (op.get("quoted_text") or "").strip()
        if not quoted:
            return {
                "consolidated_text": None,
                "consolidation_method": None,
                "consolidation_sha256": None,
                "consolidation_status": "failed",
                "consolidation_note": "refused: validated article op without quoted text",
            }
        text = quoted
        applied.append(op.get("op_id", "?"))
    assert text is not None
    return {
        "consolidated_text": text,
        "consolidation_method": "consolidated_from_instruments",
        "consolidation_sha256": sha256_text(text),
        "consolidation_status": "needs_review",
        "consolidation_note": (
            "candidate composed from validated article-scope ops in effective "
            f"order ({'+'.join(applied)}); NOT an official verbatim quote — "
            "pending licensed review"
        ),
    }
