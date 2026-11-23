"""
article_numbers.py — parse Arabic article-number words used by Saudi law pages.

Examples:
    المادة الرابعة والثمانون            → 84
    المادة الحادية عشرة                 → 11
    المادة الأولى بعد المائة            → 101
    المادة الخامسة والثلاثون بعد المائتين → 235
    المادة المائة                       → 100

The parser is intentionally narrow: it accepts the ordinal vocabulary used by
BOE/Umm Al-Qura article headings and returns None for anything else.  It is not
a general Arabic-number library.
"""
from __future__ import annotations

import re
import unicodedata

_UNITS = {
    "الاول": 1, "الاولي": 1,
    "الثاني": 2, "الثانيه": 2,
    "الثالث": 3, "الثالثه": 3,
    "الرابع": 4, "الرابعه": 4,
    "الخامس": 5, "الخامسه": 5,
    "السادس": 6, "السادسه": 6,
    "السابع": 7, "السابعه": 7,
    "الثامن": 8, "الثامنه": 8,
    "التاسع": 9, "التاسعه": 9,
    "العاشر": 10, "العاشره": 10,
    "الحادي": 1, "الحاديه": 1,
}

_TENS = {
    "العشرون": 20, "العشرين": 20,
    "الثلاثون": 30, "الثلاثين": 30,
    "الاربعون": 40, "الاربعين": 40,
    "الخمسون": 50, "الخمسين": 50,
    "الستون": 60, "الستين": 60,
    "السبعون": 70, "السبعين": 70,
    "الثمانون": 80, "الثمانين": 80,
    "التسعون": 90, "التسعين": 90,
}

_HUNDREDS = {
    "المائه": 100, "المئه": 100,
    "المائتان": 200, "المائتين": 200,
    "المئتان": 200, "المئتين": 200,
    "الثلاثمائه": 300, "الثلاثمئه": 300,
    "الاربعمائه": 400, "الاربعمئه": 400,
    "الخمسمائه": 500, "الخمسمئه": 500,
    "الستمائه": 600, "الستمئه": 600,
    "السبعمائه": 700, "السبعمئه": 700,
    "الثمانمائه": 800, "الثمانمئه": 800,
}

_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_arabic_number_text(s: str) -> str:
    """Fold Arabic orthography for number-word parsing."""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u00ad", "").replace("\u0640", "")
    s = re.sub(r"[\u064B-\u0652\u0670]", "", s)
    return (
        s.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )


def parse_arabic_article_number(title: str) -> int | None:
    """Parse an Arabic article heading into an integer, or return None."""
    if not title:
        return None

    text = normalize_arabic_number_text(title)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("الماده", " ").strip(" :،-.")

    hundreds = 0
    for phrase, value in (
        ("بعد الثمانمائه", 800),
        ("بعد الثمانمئه", 800),
        ("بعد السبعمائه", 700),
        ("بعد السبعمئه", 700),
        ("بعد الستمائه", 600),
        ("بعد الستمئه", 600),
        ("بعد الخمسمائه", 500),
        ("بعد الخمسمئه", 500),
        ("بعد الاربعمائه", 400),
        ("بعد الاربعمئه", 400),
        ("بعد الثلاثمائه", 300),
        ("بعد الثلاثمئه", 300),
        ("بعد المائتين", 200),
        ("بعد المئتين", 200),
        ("بعد المائه", 100),
        ("بعد المئه", 100),
        ("المائتان", 200),
        ("المائتين", 200),
        ("المئتان", 200),
        ("المئتين", 200),
        ("الثلاثمائه", 300),
        ("الثلاثمئه", 300),
        ("الاربعمائه", 400),
        ("الاربعمئه", 400),
        ("الخمسمائه", 500),
        ("الخمسمئه", 500),
        ("الستمائه", 600),
        ("الستمئه", 600),
        ("السبعمائه", 700),
        ("السبعمئه", 700),
        ("الثمانمائه", 800),
        ("الثمانمئه", 800),
        ("المائه", 100),
        ("المئه", 100),
    ):
        if phrase in text:
            hundreds = value
            text = text.replace(phrase, " ")
            break

    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return hundreds or None

    tokens = text.split()
    total = hundreds
    for token in tokens:
        token = token.strip(" :،-.")
        if not token:
            continue
        if token.startswith("و") and len(token) > 1:
            token = token[1:]
        if token in ("عشره", "عشر"):
            total += 10
        elif token in _UNITS:
            total += _UNITS[token]
        elif token in _TENS:
            total += _TENS[token]
        elif token in _HUNDREDS:
            total += _HUNDREDS[token]
        else:
            return None
    return total or None


def parse_digits_article_number(value: str | int | None) -> int | None:
    """Parse a plain or Arabic-Indic digit article number."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).translate(_ARABIC_INDIC).strip()
    if text.isdigit():
        return int(text)
    return parse_arabic_article_number(text)
