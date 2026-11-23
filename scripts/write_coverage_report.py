"""
write_coverage_report.py — B5: corpus coverage + fingerprints + gates.

Regenerates releases/phase-b-coverage.json from the current corpus files
(counts, status/text_status/consolidation splits, per-file sha256
fingerprints, instruments, fetch stamps) plus eval metrics, retrieval
perf (median/P95 vs the 50 ms budget), and the standing policy gates.

Also refreshes the `corpus` linkage block of evals/source-registry.json
entries that have a verbatim corpus (files/count/fetched_at/sha256).
ZATCA stays summary-only by documented decision (regulator PDF, not a
BOE/UQN law page — the ingest pipeline has no PDF parser, and a partial
scrape would be less honest than the labeled summary).

No network.  Run: python scripts/write_coverage_report.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import os

os.environ.setdefault("REPO_PATH", str(REPO_ROOT / "saudi_legal_mcp" / "data"))

from evals.metrics.eval_runner import run_eval  # noqa: E402
from scripts.measure_retrieval_perf import run_perf  # noqa: E402
from saudi_legal_mcp.tools.corpus import CORPUS_FILES, load_corpus_file  # noqa: E402
from saudi_legal_mcp.tools.reasoning import _MAX_SECTIONS_RETURNED  # noqa: E402
from saudi_legal_mcp.tools.search import MATCH_CONFIDENCE_THRESHOLD  # noqa: E402

def _corpus_block(source_id: str) -> str | None:
    """Render the registry `corpus` block for one source (or None)."""
    stems = CORPUS_FILES.get(source_id, ())
    files, fetched, counts = [], [], 0
    shas: dict[str, str | None] = {}
    for stem in stems:
        corpus = load_corpus_file(stem)
        if not corpus:
            return None
        files.append(stem + ".json")
        counts += len(corpus.get("articles", []))
        fetched.append(corpus.get("fetched_at") or "")
        shas[stem] = corpus.get("source_sha256")
    block = {
        "files": files,
        "article_count": counts,
        "fetched_at": max((f for f in fetched if f), default=None),
        "source_sha256": shas,
    }
    return '"corpus": ' + json.dumps(block, ensure_ascii=False, indent=2).replace("\n", "\n    ")


def _refresh_registry_block(text: str, key: str, block: str) -> str:
    """Surgically insert-or-replace one entry's corpus block (additive only
    for the rest of the file: no reformatting, no deletions)."""
    import re as _re

    anchor = f'"{key}": ' + "{"
    idx = text.find(anchor)
    if idx < 0:
        return text
    pattern = _re.compile(r'\n    "corpus": \{(?:[^{}]|\{[^{}]*\})*\},')
    head, tail = text[:idx], text[idx:]
    tail_new, n = pattern.subn("\n    " + block + ",", tail, count=1)
    if n == 0:
        # No existing block: insert right after the entry opening line.
        eol = tail.find("\n")
        tail_new = tail[: eol + 1] + "    " + block + ",\n" + tail[eol + 1 :]
    return head + tail_new


REGISTRY_PATH = REPO_ROOT / "evals" / "source-registry.json"
REGISTRY_KEY_BY_SOURCE = {
    "labor-law": "labor_law",
    "civil-transactions-law": "civil_transactions_law",
    "pdpl": "pdpl_law",
    "commercial-courts": "commercial_courts_law",
    "companies-law": "companies_law",
    "arbitration-law": "arbitration_law",
    "e-commerce-law": "e_commerce_law",
}
EXEC_REGS_KEY = "pdpl_exec_regs"


def _git_head() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=15,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> int:
    corpora: dict[str, dict] = {}
    for source_id, stems in CORPUS_FILES.items():
        files = []
        total = 0
        fetched: list[str] = []
        instruments: list[str] = []
        for stem in stems:
            corpus = load_corpus_file(stem)
            if not corpus:
                continue
            articles = corpus.get("articles", [])
            total += len(articles)
            fetched.append(corpus.get("fetched_at") or "")
            instruments.append(corpus.get("instrument") or "")
            files.append({
                "stem": stem,
                "articles": len(articles),
                "status": dict(Counter(a.get("status", "?") for a in articles)),
                "text_status": dict(Counter(a.get("text_status", "?") for a in articles)),
                "consolidation": dict(Counter(
                    a.get("consolidation_status", "?") for a in articles
                )),
                "parse": dict(Counter(
                    (o.get("parse_status") or "?")
                    for a in articles for o in (a.get("amendments") or [])
                )),
                "source_sha256": corpus.get("source_sha256"),
                "fetched_at": corpus.get("fetched_at"),
                "instrument": corpus.get("instrument"),
                "document_url": corpus.get("document_url"),
                "amendments_schema": corpus.get("amendments_schema_version"),
            })
        if files:
            corpora[source_id] = {
                "files": files,
                "article_count": total,
                "fetched_at": max((f for f in fetched if f), default=None),
                "instruments": sorted(set(instruments)),
            }

    # Refresh registry corpus linkage (surgical: insert-or-replace only
    # the per-entry corpus block; the rest of the file is untouched).
    if REGISTRY_PATH.exists():
        text = REGISTRY_PATH.read_text(encoding="utf-8")
        for source_id, key in REGISTRY_KEY_BY_SOURCE.items():
            if source_id not in corpora:
                continue
            block = _corpus_block(source_id)
            if block is None:
                continue
            text = _refresh_registry_block(text, key, block)
        REGISTRY_PATH.write_text(text, encoding="utf-8")

    print("[coverage] running eval ...", file=sys.stderr)
    evaluation = run_eval()
    print("[coverage] running perf ...", file=sys.stderr)
    _, perf_overall = run_perf(reps=15, warmup=3)
    perf_overall = {**perf_overall, "budget_ms": 50.0}
    perf_overall["within_budget"] = perf_overall["p95_ms"] < 50.0

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_head": _git_head(),
        "phase": "B (v1 composition; no verified rows without licensed review)",
        "golden_values": "TEMPORARY until licensed review — negative tests only",
        "corpora": corpora,
        "totals": {
            "sources_with_corpus": len(corpora),
            "articles": sum(c["article_count"] for c in corpora.values()),
        },
        "evaluation": {
            "total_questions": evaluation.get("total_questions"),
            "citation_precision_avg": evaluation.get("citation_precision_avg"),
            "source_recall_avg": evaluation.get("source_recall_avg"),
            "abstention_accuracy": evaluation.get("abstention_accuracy"),
        },
        "retrieval_perf": perf_overall,
        "policy_gates": {
            "match_confidence_threshold": MATCH_CONFIDENCE_THRESHOLD,
            "corpus_limit": _MAX_SECTIONS_RETURNED,
            "verified_requires": "licensed review or official resync (never v1 code)",
        },
        "deliberately_summary_only": {
            "zatca-e-invoicing": (
                "Official source is a regulator PDF on zatca.gov.sa, not a "
                "BOE/UQN law page; the ingest pipeline parses BOE/UQN HTML "
                "only and has no PDF parser. Kept as labeled hand-written "
                "summary rather than a partial scrape."
            )
        },
    }
    out_path = REPO_ROOT / "releases" / "phase-b-coverage.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[coverage] wrote {out_path} [OK]")
    if not perf_overall["within_budget"]:
        print(
            f"[coverage] PERF BUDGET EXCEEDED: P95 {perf_overall['p95_ms']}ms",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
