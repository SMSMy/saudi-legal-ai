"""
arabic.py — shared Arabic text normalization for retrieval and comparison.

This module is deliberately dependency-free.  The normalization rules are the
ones already used by the v0.4 retrieval engine:

  - diacritics / tanween / shadda are removed;
  - orthographic variants are folded (أ/إ/آ → ا, ى → ي, ة → ه);
  - Arabic function words are excluded from query tokenization;
  - a SMALL, documented synonym list is used at scoring time only.

Nothing here is a stemmer.  A real stemmer/BM25 belongs to a later wave and
must be evaluated before replacing this behavior.
"""
from __future__ import annotations

import re

# v0.4.9 — diacritics are not semantic for retrieval.
_DIACRITICS_RE = re.compile(r"[\u064B-\u0652\u0670]")

# v0.4.10 — orthographic normalization (safe, no true stemming).
_HAMZA_TABLE = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})

# v0.4.12 — minimal synonym groups for scoring-side expansion.
# Built ONLY from documented failure cases.  Groups are in NORMALIZED form.
SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"الموظف", "العامل"}),
    frozenset({"السنه", "سنه", "سنويا", "سنويه", "سنوي", "السنوي"}),
    frozenset({"يستحق", "تستحق"}),
    frozenset({"يجدد", "تجديد"}),
    frozenset({"افصل", "فصل", "انهاء"}),
)

# v0.4.9 — Arabic function words excluded from scoring.
ARABIC_STOPWORDS = frozenset({
    "كم", "في", "من", "إلى", "على", "عن", "هل", "ما", "هذا", "هذه",
    "ذلك", "تلك", "الذي", "التي", "الذين", "أن", "إن", "هو", "هي",
    "هم", "لم", "لن", "لا", "قد", "كان", "كانت", "كل", "بعض", "أي",
    "غير", "حيث", "إذا", "ثم", "أو", "حتى", "مع", "بين", "بعد", "قبل",
    "عند", "لدى", "نحو", "حول", "مثل", "دون", "كيف", "متى", "أين",
    "لماذا", "ماذا",
    "يبي", "تبي", "لي", "له", "وبعد", "لأن",
})

_ARABIC_PREFIXES = ("لل", "وال", "بال", "كال", "فال", "ال")


def strip_diacritics(s: str) -> str:
    """Remove Arabic diacritics only."""
    return _DIACRITICS_RE.sub("", s)


def normalize_arabic(s: str) -> str:
    """Diacritics removal + orthographic normalization for matching."""
    return strip_diacritics(s).translate(_HAMZA_TABLE)


def synonym_variants(term_normalized: str) -> frozenset[str]:
    """Return the synonym group containing the normalized term, or the term."""
    for group in SYNONYM_GROUPS:
        if term_normalized in group:
            return group
    return frozenset({term_normalized})


def tokenize_query(query: str) -> list[str]:
    """Extract meaningful tokens from a query.

    Arabic letters only (punctuation/diacritics are not glued to tokens),
    function words excluded.  Latin tokens remain >= 3 characters.
    """
    tokens = re.findall(r"[\u0621-\u064A]{2,}|[a-zA-Z]{3,}", query)
    seen: set[str] = set()
    unique: list[str] = []
    for t in tokens:
        t_lower = t.lower()
        if t_lower in ARABIC_STOPWORDS:
            continue
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def normalize_phrase(s: str) -> str:
    """Normalize Arabic text for equivalence comparison.

    Diacritics + orthographic normalization, then per-word stripping of
    leading prefixes (لل/وال/بال/كال/فال/ال).  Symmetric on both sides.
    """
    normalized = normalize_arabic(s)
    out_words = []
    for w in normalized.split():
        for pref in _ARABIC_PREFIXES:
            if w.startswith(pref) and len(w) > len(pref) + 1:
                w = w[len(pref):]
                break
        out_words.append(w)
    return " ".join(out_words)


def strip_placeholders(text: str) -> str:
    """Remove [يحتاج تحقق ...] placeholder markers from text."""
    return re.sub(r"\[يحتاج تحقق[^\]]*\]", "", text)
