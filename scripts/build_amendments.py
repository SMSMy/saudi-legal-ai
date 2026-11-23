"""
build_amendments.py — B1: build structured amendments[] + v1 consolidation.

Reads the free-text amendment_history of every amended article in
labor-law.json / pdpl.json and parses each operation into the plan §2.2
shape (scope/target/op/quoted_text/instrument/dates/parse_status), then
runs the v1 composer (saudi_legal_mcp.tools.amendments) and stores the
consolidation_* outcome on the article.

Conservative by design: anything the strict patterns cannot pin down is
parse_status needs_review/failed, and v1 composition applies ONLY to
validated article/replace|insert chains.  Nothing here quotes anything
as operative and nothing is marked verified — that needs a licensed
review (Phase B gate).

Idempotent: rebuilds amendments/consolidation keys from text+history.
No network.  Run: python scripts/build_amendments.py [--check]
  --check: parse + compose in memory, report, write nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from saudi_legal_mcp.tools.amendments import (  # noqa: E402
    compose,
    hijri_to_iso,
    parse_hijri_date,
    summarize_operation,
)

DATA_DIR = REPO_ROOT / "saudi_legal_mcp" / "data"
CORPUS_DIR = DATA_DIR / "corpus"
STEMS = ("labor-law", "civil-transactions-law", "pdpl", "pdpl-exec-regulations",
          "commercial-courts", "companies-law", "arbitration-law", "e-commerce-law")

# Display-only typo corrections: (old, new).  Never touches text/sha256.
TYPO_FIXES: dict[str, dict[str, tuple[str, str]]] = {
    "labor-law": {"234": ("شهاً", "شهرًا")},
}

_QUOTE_RE = re.compile(r"[\"“”«»](.+?)[\"“”«»]", re.S)

_SEG_SPLIT_RE = re.compile(
    r"(?=المادة\s+(?![^.:\n]{0,60}?(?:على النحو|النص الآتي|بهذه|بهذا))[^:]{1,60}?\s*:\s*(?:-|تم|صدر|عُ|عد|أض|أع|إض|إح|جر|كما|ألغ|حُ))"
)

_ART_REF_RE = re.compile(r"المادة\s+(?:الثانية عشرة|الثالثة عشرة|الرابعة عشرة)")


def _norm_instrument(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("م/"):
        return raw
    return raw


def _extract_instrument(segment: str, fallback: list[dict]) -> tuple[str, str]:
    # The operative decree for the quoted text is the LAST one mentioned:
    # histories often recap an earlier decree before stating the latest
    # amendment ("as amended by X, further amended by Y to read: ...").
    # All instruments found are recorded in the op note when >1.
    pairs: list[tuple[str, str]] = []
    for m in re.finditer(
        r"(?:المرسوم الملكي\s+(?:رقم\s*)?\(?\s*م\s*/\s*(\d+)\s*\)?|قرار مجلس الوزراء رقم\s*\(?\s*(\d+))",
        segment,
    ):
        num = m.group(1) or m.group(2)
        prefix = "م/" if m.group(1) else "ق/"
        tail = segment[m.end():]
        dm = re.search(r"تاريخ\s+(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{3,4})\s*ه?", tail)
        date = ""
        if dm:
            a, b, c = dm.group(1), dm.group(2), dm.group(3)
            date = f"{c}/{b}/{a}" if len(c) == 4 else ""
        pairs.append((f"{prefix}{num}", date))
    if pairs:
        inst, date = pairs[-1]
    else:
        inst, date = "", ""
    if not date and fallback:
        date = (fallback[0].get("date") or "").rstrip("ه")
    extra = "; ".join(f"{i} {d}" for i, d in pairs[:-1]) if len(pairs) > 1 else ""
    note_instruments = f" [earlier mentioned: {extra}]" if extra else ""
    return _norm_instrument(inst), date, note_instruments


def _hijri_iso(hijri_ymd: str) -> "str | None":
    parsed = parse_hijri_date(hijri_ymd or "")
    if not parsed:
        return None
    try:
        return hijri_to_iso(*parsed)
    except (ValueError, OverflowError):
        return None


def _effective_of(segment: str, issued_hijri: str) -> str:
    m = re.search(r"يعم(?:ل|ل بها) من تاريخ\s+([^\s،؛.\"\"«»]+)", segment)
    # Robust form: capture the Y/M/D or D/M/Y fragment after the phrase.
    m2 = re.search(r"يعمل بها من تاريخ\s+(\d[\d/\s]*\d)\s*ه?", segment)
    if m2:
        frag = m2.group(1)
        pm = re.search(r"(\d{1,4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,4})", frag)
        if pm:
            a, b, c = pm.group(1), pm.group(2), pm.group(3)
            if len(a) >= 4:
                return f"{a}/{b}/{c}"
            if len(c) >= 4:
                return f"{c}/{b}/{a}"
    _ = m
    return issued_hijri


def _lexical_pairs(segment: str) -> list[dict]:
    pairs = []
    for m in re.finditer(
        r"بإحلال\s+(?:كلمة|عبارة)\s+[\"«]([^\"»]+)[\"»]\s+محل\s+(?:كلمتي?|عبار[ةة])\s+[\"«]([^\"»]+)[\"»]",
        segment,
    ):
        old = m.group(2).strip()
        # Sibling olds: محل كلمتي "وحدة" و "وحدات" → old = both, joined.
        rest = segment[m.end():]
        for sm in re.finditer(r"\s*و\s+[\"«]([^\"»]+)[\"»]", rest):
            gap = rest[: sm.start()]
            if re.search(r"[.!؛:]", gap):
                break
            old = old + " / " + sm.group(1).strip()
            rest = rest[sm.end():]
            if old.count("/") >= 3:
                break
        pairs.append({"old": old, "new": m.group(1).strip()})
    # Unquoted fallback: إحلال كلمة X محل كلمة Y (pdpl 5/24 style).
    if not pairs:
        for m in re.finditer(
            r"إحلال\s+(?:كلمة|عبارة)\s+\"?([^\"،؛.]+?)\"?\s+محل\s+(?:كلمة|كلمتي?|عبارة)\s+\"?([^\"،؛.]+?)\"?\s+الواردة",
            segment,
        ):
            pairs.append({"old": m.group(2).strip(), "new": m.group(1).strip()})
    return pairs


def _bare(text):
    """Strip tashkeel + normalize أ→ا for pattern matching.

    Quotes/instruments/dates always use the original text; only
    directive classification uses the normalized copy.
    """
    text = re.sub(r"[\u064B-\u0652\u0670]", "", text)
    return text.replace("أ", "ا")


def _directive_kind(pre):
    """Classify the directive text preceding a quote (diacritic-free).

    Returns (kind, target); kind in: whole, paragraph, preamble,
    lexical, insert, definitions, cancel, delete, unknown.
    Only the PRE-QUOTE directive counts — in-quote cross-references
    must never veto a whole-article replacement.
    """
    pre = _bare(pre)
    if re.search(r"حذفت هذه المادة", pre):
        return ("delete", None)
    if re.search(r"الغيت هذه المادة", pre):
        return ("cancel", None)
    if re.search(r"إلغاء (الباب|الفصل)", pre):
        return ("cancel", "chapter")
    hm = re.search(
        r"\u062d\u0630\u0641[\u062a\u0629]?\s+(?:\u0627\u0644\u0641\u0642\u0631\u0629|\u0627\u0644\u0641\u0642\u0631\u062a\u0627\u0646|\u0627\u0644\u0641\u0642\u0631\u0627\u062a)\s*(?:\(([^)]+)\)|([\u0600-\u06FF0-9/]+))", pre
    )
    if hm:
        return ("para_cancel", (hm.group(1) or hm.group(2) or "").strip() or None)
    if "تعريف" in pre:
        return ("definitions", None)
    if re.search(r"(?:بإضافة|إضافة)\s+", pre):
        return ("insert", None)
    if re.search(r"بإحلال|إحلال\s+(?:كلمة|عبارة)", pre):
        return ("lexical", None)
    pm = re.search(
        r"(?:الفقرة|الفقرتان|الفقرات)\s*(?:\(([^)]+)\)|([\u0600-\u06FF0-9/]+))", pre
    )
    if pm and re.search(r"(?:عدل|تعديل)", pre):
        return ("paragraph", (pm.group(1) or pm.group(2) or "").strip() or None)
    if re.search(r"(?:ديباجة|صدر)\s+(?:هذه\s+)?المادة", pre) and re.search(
        r"(?:عدل|تعديل)", pre
    ):
        dm = re.search(r"(ديباجة|صدر)", pre)
        return ("preamble", dm.group(1) if dm else None)
    rm = re.search(r"ونقلها لتكون\s*\(([^)]+)\)", pre)
    if rm:
        return ("renumber", rm.group(1).strip())
    if re.search(
        r"(?:هذه المادة|نص هذه المادة).{0,120}?(?:لتكون بالنص الآتي|لتصبح بالنص|"
        r"إحلال النص الآتي محله|ليكون النص كالآتي|لتكون على النحو الآتي|"
        r"لتصبح فقرة واحدة بالنص الآتي|لتكون فقرة واحدة بالنص الآتي)",
        pre,
    ):
        return ("whole", None)
    return ("unknown", None)


def _lexical_target(segment):
    seg = _bare(segment)
    lm = re.search(r"الواردة في (?:الفقرة\s*\(([^)]+)\)|هذه المادة)", seg)
    if lm:
        return lm.group(1).strip() if lm.group(1) else "article"
    if "أينما وردت" in seg:
        return "article"
    return None


def _lexical_pairs(segment):
    seg = _bare(segment)
    pairs = []
    for m in re.finditer(
        r"بإحلال\s+(?:كلمة|عبارة)\s+[\"«]([^\"»]+)[\"»]\s+محل\s+(?:كلمتي?|عبار[ةة])\s+[\"«]([^\"»]+)[\"»]",
        seg,
    ):
        pairs.append({"old": m.group(2).strip(), "new": m.group(1).strip()})
    if not pairs:
        for m in re.finditer(
            r"إحلال\s+(?:كلمة|عبارة)\s+\"?([^\"،؛.]+?)\"?\s+محل\s+(?:كلمة|كلمتي?|عبارة)\s+\"?([^\"،؛.]+?)\"?\s+الواردة",
            seg,
        ):
            pairs.append({"old": m.group(2).strip(), "new": m.group(1).strip()})
    return pairs


def _parse_segment(article_no, seg_idx, segment, fallback_instruments):
    """Parse one history segment into 0+ structured ops (conservative)."""

    def base_op(suffix=0):
        inst, issued, extra_note = _extract_instrument(segment, fallback_instruments)
        eff = _effective_of(segment, issued)
        op = {
            "op_id": f"{article_no}.{seg_idx}" + (f".{suffix}" if suffix else ""),
            "instrument": inst,
            "issued_on_hijri": issued,
            "issued_on_iso": _hijri_iso(issued),
            "effective_on_hijri": eff,
            "effective_on_iso": _hijri_iso(eff),
            "effective_order": seg_idx * 10 + suffix,
            "official_url": None,
            "fetched_at": None,
            "source_sha256": None,
            "_extra_instruments": extra_note,
        }
        return op

    def _note(op, text):
        extra = op.pop("_extra_instruments", "")
        if text and extra:
            return text + extra
        return text or extra or None

    def _final(op, text):
        op["parse_note"] = _note(op, text)
        return op

    def spans_of(text):
        return [(m.start(), m.end(), m.group(1).strip()) for m in _QUOTE_RE.finditer(text)]

    spans = spans_of(segment)
    quotes = [q for _, _, q in spans if q]
    bare = _bare(segment)
    spans_bare = spans_of(bare)
    if len(spans_bare) != len(spans):
        spans_bare = spans  # fall back; gaps still usable for keywords
    if (
        len(re.findall(r"المادة\s+(?:الثانية عشرة|الثالثة عشرة|الرابعة عشرة)", segment)) >= 2
        or ("لتصبح في مادتين" in bare or "لتصبحا في مادتين" in bare)
        or "إعادة صياغ" in bare
        or (re.search(r"تعديل احكام الماد", bare) and "لتكون في ماد" in bare)
    ):
        op = base_op()
        op.update({
            "scope": "article", "target": "restructure", "op": "replace",
            "insert_after": None, "quoted_text": None, "replacements": [],
            "parse_status": "needs_review",
            "parse_note": "cross-article restructure: not auto-composable",
        })
        return [op]

    pre0 = re.split(r"[\"“”«»]", segment, maxsplit=1)[0]
    kind0, t0 = _directive_kind(pre0)
    if kind0 in ("cancel", "delete"):
        op = base_op()
        op.update({
            "scope": "article", "target": t0, "op": "cancel",
            "insert_after": None, "quoted_text": None, "replacements": [],
            "parse_status": "validated",
            "parse_note": (
                f"article {kind0}d by instrument"
                + (f" ({t0} repeal)" if t0 else "")
                + "; kept as amended row per BOE"
            ),
        })
        return [op]

    # Multi-quote segment: single-op shortcuts first (lexical batches,
    # definition batches, ambiguous whole-article quotes).
    if len(spans) > 1:
        pre_first = segment[: spans[0][0]] if spans else segment
        seg_kind, _seg_t = _directive_kind(pre_first)
        if seg_kind == "lexical":
            pairs = _lexical_pairs(segment)
            if pairs:
                op = base_op()
                op.update({
                    "scope": "paragraph", "target": _lexical_target(segment),
                    "op": "replace", "insert_after": None, "quoted_text": None,
                    "replacements": pairs,
                    "parse_status": "validated" if _lexical_target(segment) else "needs_review",
                    "parse_note": "lexical batch; v1 never auto-applies (article-scope only)",
                })
                return [op]
        if seg_kind == "definitions":
            op = base_op()
            op.update({
                "scope": "paragraph", "target": "\u062a\u0639\u0631\u064a\u0641\u0627\u062a",
                "op": "insert" if "\u0625\u0636\u0627\u0641\u0629" in _bare(pre_first) else "replace",
                "insert_after": None, "quoted_text": None, "replacements": [],
                "parse_status": "needs_review",
                "parse_note": "multi-definition batch; per-item positions vary, withheld in v1",
            })
            return [op]
        if seg_kind == "whole":
            op = base_op()
            op.update({
                "scope": "article", "target": None, "op": "replace",
                "insert_after": None, "quoted_text": None, "replacements": [],
                "parse_status": "needs_review",
                "parse_note": "whole-article directive with multiple quotes: ambiguous, withheld",
            })
            return [op]
    # Multi-quote segment: bind each quote to its own directive gap.
    if len(spans) > 1:
        bound_ops = []
        for i, (s, e, q) in enumerate(spans):
            gs = spans_bare[i - 1][1] if i > 0 else 0
            gap = bare[gs:spans_bare[i][0]]
            kind, target = _directive_kind(gap)
            if kind == "unknown":
                kind, target = _directive_kind(bare[: spans_bare[i][0]])
            op = base_op(i + 1)
            if kind == "whole":
                scope, action = "article", "replace"
            elif kind in ("paragraph", "preamble"):
                scope, action = "paragraph", "replace"
            elif kind == "para_cancel":
                scope, action = "paragraph", "cancel"
            elif kind == "insert":
                scope, action = "paragraph", "insert"
            elif kind == "lexical":
                scope, action = "paragraph", "replace"
            elif kind == "definitions":
                scope, action = "paragraph", (
                    "insert" if "إضافة" in gap or "اضافة" in gap else "replace"
                )
                target = "تعريفات"
            else:
                op.update({
                    "scope": None, "target": None, "op": None,
                    "insert_after": None, "quoted_text": None, "replacements": [],
                    "parse_status": "failed",
                    "parse_note": f"unrecognized directive before quote {i + 1}: {gap[-120:]}…",
                })
                bound_ops.append(op)
                continue
            after = None
            if action == "insert":
                mkr = re.search(r"(\d+)\s*\(\s*مكرر\s*\)", q)
                after = mkr.group(1) if mkr else "append"
                if after != "append" and not target:
                    target = after + " مكرر"
            op.update({
                "scope": scope,
                "target": "lexical" if kind == "lexical" else target,
                "op": action,
                "insert_after": after,
                "quoted_text": q,
                "replacements": _lexical_pairs(gap) if kind == "lexical" else [],
                "parse_status": "validated" if (target or kind in ("whole", "lexical")) else "needs_review",
                "parse_note": None,
            })
            if kind == "lexical" and not op["replacements"]:
                op["replacements"] = _lexical_pairs(segment)
            bound_ops.append(op)
        if any(o["parse_status"] != "failed" for o in bound_ops):
            return bound_ops
        pairs = _lexical_pairs(segment)
        if pairs and ("بإحلال" in bare or "إحلال" in bare):
            op = base_op()
            op.update({
                "scope": "paragraph", "target": _lexical_target(segment),
                "op": "replace", "insert_after": None, "quoted_text": None,
                "replacements": pairs,
                "parse_status": "validated" if _lexical_target(segment) else "needs_review",
                "parse_note": "lexical substitution; v1 never auto-applies (article-scope only)",
            })
            return [op]
        op = base_op()
        op.update({
            "scope": None, "target": None, "op": None,
            "insert_after": None, "quoted_text": None, "replacements": [],
            "parse_status": "failed",
            "parse_note": f"multi-quote segment without bindable directives: {segment[:160]}…",
        })
        return [op]

    # Single-quote (or quoteless) segment from here on.
    pre = segment[: spans[0][0]] if spans else segment
    q0 = quotes[0] if len(quotes) == 1 else None
    kind, target = _directive_kind(pre)

    if kind == "whole":
        op = base_op()
        op.update({
            "scope": "article", "target": None, "op": "replace",
            "insert_after": None, "quoted_text": q0, "replacements": [],
            "parse_status": "validated" if q0 else "needs_review",
            "parse_note": None if q0 else "whole-article directive without exactly one quote",
        })
        return [op]

    if kind == "renumber":
        op = base_op()
        op.update({
            "scope": "article", "target": f"renumber→{target}", "op": "move",
            "insert_after": None, "quoted_text": q0, "replacements": [],
            "parse_status": "needs_review",
            "parse_note": "article moved/renumbered; identity change withheld in v1",
        })
        return [op]

    if kind == "para_cancel":
        op = base_op()
        op.update({
            "scope": "paragraph", "target": target, "op": "cancel",
            "insert_after": None, "quoted_text": None, "replacements": [],
            "parse_status": "validated" if target else "needs_review",
            "parse_note": "paragraph deleted by instrument; v1 withholds all non-article ops",
        })
        return [op]

    if kind in ("paragraph", "preamble"):
        op = base_op()
        op.update({
            "scope": "paragraph", "target": target, "op": "replace",
            "insert_after": None, "quoted_text": q0, "replacements": [],
            "parse_status": "validated" if (target and q0) else "needs_review",
            "parse_note": None if (target and q0) else "target or quote uncertain",
        })
        return [op]

    if kind == "definitions":
        if q0 and len(quotes) == 1:
            tm = re.search(r"تعريف\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+){0,2})", _bare(pre))
            op = base_op()
            op.update({
                "scope": "paragraph", "target": (tm.group(1).strip() if tm else "تعريف"),
                "op": "replace", "insert_after": None, "quoted_text": q0,
                "replacements": [],
                "parse_status": "validated",
                "parse_note": "single-definition replace; v1 withholds paragraph ops",
            })
            return [op]
        op = base_op()
        op.update({
            "scope": "paragraph", "target": "تعريفات", "op": "replace",
            "insert_after": None, "quoted_text": None, "replacements": [],
            "parse_status": "needs_review",
            "parse_note": "multi-definition update; per-item positions vary",
        })
        return [op]

    if kind == "insert":
        mkr = re.findall(r"(\d+)\s*\(\s*مكرر\s*\)", segment)
        if mkr:
            out = []
            for i, num in enumerate(mkr):
                op = base_op(i + 1 if len(mkr) > 1 else 0)
                bound = quotes[i] if len(quotes) == len(mkr) and i < len(quotes) else None
                op.update({
                    "scope": "paragraph", "target": f"{num} مكرر", "op": "insert",
                    "insert_after": num, "quoted_text": bound, "replacements": [],
                    "parse_status": "validated" if bound else "needs_review",
                    "parse_note": "مكرر paragraph: inserted after N by numbering convention",
                })
                out.append(op)
            return out
        fm = re.search(r"إضافة فقرة\s*\(([^)]+)\)", _bare(pre))
        if fm:
            op = base_op()
            op.update({
                "scope": "paragraph", "target": fm.group(1).strip(), "op": "insert",
                "insert_after": "append", "quoted_text": q0, "replacements": [],
                "parse_status": "needs_review",
                "parse_note": "appended paragraph: position inferred, withheld in v1",
            })
            return [op]
        op = base_op()
        op.update({
            "scope": "paragraph", "target": target, "op": "insert",
            "insert_after": "append", "quoted_text": q0, "replacements": [],
            "parse_status": "needs_review",
            "parse_note": "added paragraph(s)/definitions; position inferred, withheld in v1",
        })
        return [op]

    pairs = _lexical_pairs(segment)
    if pairs and ("بإحلال" in bare or "إحلال" in bare):
        op = base_op()
        op.update({
            "scope": "paragraph", "target": _lexical_target(segment),
            "op": "replace", "insert_after": None, "quoted_text": None,
            "replacements": pairs,
            "parse_status": "validated" if _lexical_target(segment) else "needs_review",
            "parse_note": "lexical substitution; v1 never auto-applies (article-scope only)",
        })
        return [op]

    ins = re.search(r"بإضافة عبارة\s+[\"«]([^\"»]+)[\"»]\s+بعد\s+([^.؛\"\"«»]{1,60})", segment)
    if ins:
        op = base_op()
        op.update({
            "scope": "paragraph", "target": ins.group(1).strip(), "op": "insert",
            "insert_after": ins.group(2).strip(), "quoted_text": None, "replacements": [],
            "parse_status": "validated",
            "parse_note": "phrase insert at explicit location; v1 withholds paragraph/insert",
        })
        return [op]

    op = base_op()
    op.update({
        "scope": None, "target": None, "op": None,
        "insert_after": None, "quoted_text": None, "replacements": [],
        "parse_status": "failed",
        "parse_note": f"unrecognized directive pattern: {pre[-160:]}…",
    })
    return [op]


def split_segments(history: str) -> list[str]:
    parts = [p for p in _SEG_SPLIT_RE.split(history or "") if p.strip()]
    # re.split with lookahead keeps delimiters glued; drop empties.
    if len(parts) <= 1 and history:
        return [history]
    return parts


def build_article_ops(article: dict) -> list[dict]:
    status = article.get("status")
    instruments = article.get("amendment_instruments", []) or []
    if status == "added":
        inst = instruments[0] if instruments else {}
        op = {
            "op_id": f"{article.get('article')}.0",
            "scope": "article", "target": None, "op": "insert",
            "insert_after": None, "quoted_text": None, "replacements": [],
            "instrument": inst.get("instrument", ""),
            "issued_on_hijri": inst.get("date", ""),
            "issued_on_iso": _hijri_iso(inst.get("date", "")),
            "effective_on_hijri": inst.get("date", ""),
            "effective_on_iso": _hijri_iso(inst.get("date", "")),
            "effective_order": 0,
            "official_url": None, "fetched_at": None, "source_sha256": None,
            "parse_status": "validated",
            "parse_note": "addition row: pulled text is the operative text; op is informational",
        }
        return [op]
    if status != "amended":
        return []
    segments = split_segments(article.get("amendment_history") or "")
    ops: list[dict] = []
    for i, seg in enumerate(segments):
        ops.extend(_parse_segment(str(article.get("article")), i, seg, instruments))
    return ops


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="parse only; write nothing")
    ap.add_argument("--stem", action="append", default=list(STEMS))
    args = ap.parse_args()

    total = {"ops": 0, "validated": 0, "needs_review": 0, "failed": 0,
             "consolidated": 0, "c_withheld": 0, "c_failed": 0, "c_na": 0}
    failures: list[str] = []

    for stem in args.stem:
        path = CORPUS_DIR / f"{stem}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for article in data.get("articles", []):
            ops = build_article_ops(article)
            # Fold the instrument-recap note and drop the scratch key.
            for op in ops:
                extra = op.pop("_extra_instruments", "")
                if extra:
                    op["parse_note"] = ((op.get("parse_note") or "") + extra) or None
            article["amendments"] = ops
            for op in ops:
                total["ops"] += 1
                total[op["parse_status"]] = total.get(op["parse_status"], 0) + 1
            result = compose({**article, "amendments": ops})
            article["consolidated_text"] = result["consolidated_text"]
            article["consolidation_method"] = result["consolidation_method"]
            article["consolidation_sha256"] = result["consolidation_sha256"]
            article["consolidation_status"] = result["consolidation_status"]
            article["consolidation_note"] = result["consolidation_note"]
            st = result["consolidation_status"]
            if st == "needs_review" and result["consolidated_text"]:
                total["consolidated"] += 1
            elif st == "needs_review":
                total["c_withheld"] += 1
            elif st == "failed":
                total["c_failed"] += 1
                failures.append(f"{stem} art-{article.get('article')}")
            else:
                total["c_na"] += 1
            # Display-only typo corrections (plan §2.5): never touch text/sha.
            fixes = TYPO_FIXES.get(stem, {})
            if str(article.get("article")) in fixes:
                old, new = fixes[str(article.get("article"))]
                if article.get("text", "").count(old) == 1:
                    article["display_text"] = article["text"].replace(old, new, 1)
                    article["display_note"] = (
                        "تصحيح إملائي للعرض فقط، وليس تعديلًا للنص النظامي؛ "
                        "النص المسحوب وبصمته دون تغيير، ولا يُقتبس المصحح حرفيًا."
                    )
        data["amendments_schema_version"] = "1.0"
        data["amendments_built_at"] = datetime.now(timezone.utc).isoformat()
        if not args.check:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{stem}] amended/added rows processed")

    print(json.dumps({"totals": total, "failed_articles": failures}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
