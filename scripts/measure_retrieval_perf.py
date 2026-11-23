"""
measure_retrieval_perf.py — B5: local retrieval latency (median/P95).

Warms up each query, then times N repetitions of the real tool path
(search_legal_provision corpus-first + find_legal_provision summary).
No network.  Exits 1 when overall P95 >= 50 ms (plan §8 budget).

Usage:
    python scripts/measure_retrieval_perf.py [--reps 40] [--warmup 5]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import os

os.environ.setdefault("REPO_PATH", str(REPO_ROOT / "saudi_legal_mcp" / "data"))

from saudi_legal_mcp.tools.reasoning import (  # noqa: E402
    find_legal_provision,
    search_legal_provision,
)

QUERIES: list[tuple[str, str, str, bool]] = [
    # (label, source_id, query, prefer_corpus)
    ("civil-template", "civil-transactions-law", "لا تسمع الدعوى على المنكر بانقضاء", True),
    ("civil-10yr", "civil-transactions-law", "متى لا تسمع الدعوى على المنكر بعد عشر سنوات", True),
    ("labor-eosb", "labor-law", "كيف تحسب مكافأة نهاية الخدمة؟", True),
    ("labor-probation", "labor-law", "ما الحد الأقصى لفترة التجربة؟", True),
    ("labor-notice", "labor-law", "كم مدة إشعار إنهاء العقد غير محدد المدة؟", True),
    ("labor-leave-summary", "labor-law", "كم يوماً الإجازة السنوية الدنيا للموظف؟", False),
    ("commercial-m24", "commercial-courts", "ما مدة عدم سماع الدعوى التجارية؟", True),
    ("companies-llc", "companies-law", "ما الحد الأدنى لرأس مال الشركة ذات المسؤولية المحدودة؟", True),
    ("arbitration-writing", "arbitration-law", "هل يصح اتفاق التحكيم الشفهي؟", True),
    ("ecom-7d", "e-commerce-law", "ما مهلة فسخ عقد التجارة الإلكترونية؟", True),
    ("pdpl-breach72", "pdpl", "متى يجب إبلاغ جهة الاختصاص عن تسرب البيانات؟", True),
    ("zatca-phases", "zatca-e-invoicing", "ما مرحلتا الفوترة الإلكترونية؟", False),
    ("bankruptcy-summary", "bankruptcy-law", "ما الإجراءات الرئيسية لنظام الإفلاس؟", False),
    ("evidence-summary", "evidence-law", "ما حجية المحرر الإلكتروني؟", False),
]


def _p95(samples: list[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    k = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95)))
    # Nearest-rank on 1-based index for small n.
    rank = max(1, int(-(-len(ordered) * 95 // 100)))
    return ordered[rank - 1]


def run_perf(*, reps: int = 40, warmup: int = 5) -> tuple[list[dict], dict]:
    per_query: list[dict] = []
    all_samples: list[float] = []
    for label, source_id, query, prefer_corpus in QUERIES:
        fn = search_legal_provision if prefer_corpus else find_legal_provision
        for _ in range(warmup):
            if prefer_corpus:
                fn(query, source_id)
            else:
                fn(query, source_id)
        samples: list[float] = []
        for _ in range(reps):
            t0 = time.perf_counter()
            if prefer_corpus:
                fn(query, source_id)
            else:
                fn(query, source_id)
            samples.append((time.perf_counter() - t0) * 1000.0)
        all_samples.extend(samples)
        per_query.append({
            "label": label,
            "source_id": source_id,
            "corpus_first": prefer_corpus,
            "reps": len(samples),
            "median_ms": round(statistics.median(samples), 2),
            "p95_ms": round(_p95(samples), 2),
            "max_ms": round(max(samples), 2),
        })
    overall = {
        "queries": len(QUERIES),
        "samples": len(all_samples),
        "median_ms": round(statistics.median(all_samples), 2),
        "p95_ms": round(_p95(all_samples), 2),
        "max_ms": round(max(all_samples), 2),
    }
    return per_query, overall


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=40)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--budget-ms", type=float, default=50.0)
    args = ap.parse_args()

    per_query, overall = run_perf(reps=args.reps, warmup=args.warmup)
    overall = {**overall, "budget_ms": args.budget_ms}
    overall["within_budget"] = overall["p95_ms"] < args.budget_ms
    print(json.dumps({"per_query": per_query, "overall": overall}, ensure_ascii=False, indent=2))
    if not overall["within_budget"]:
        print(
            f"[perf] BUDGET EXCEEDED: P95 {overall['p95_ms']}ms >= {args.budget_ms}ms",
            file=sys.stderr,
        )
        return 1
    print(f"[perf] within budget: P95 {overall['p95_ms']}ms < {args.budget_ms}ms [OK]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
