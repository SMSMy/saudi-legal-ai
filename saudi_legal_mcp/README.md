# saudi-legal-ai — MCP Server

سيرفر استرجاع قانوني سعودي محلي. لا يحتاج أي مفتاح API، ولا يستورد عميل HTTP
داخل حزمة الاسترجاع.

## Setup

```bash
git clone https://github.com/SMSMy/saudi-legal-ai.git
cd saudi-legal-ai
python3 -m venv .venv
.venv/bin/pip install -e .
```

## MCP client registration (OpenClaw example)

```bash
openclaw mcp set saudi-legal \
  '{"command":"'$(pwd)'/.venv/bin/saudi-legal-mcp","args":[]}'

openclaw mcp reload
```

OpenClaw is one MCP client; the same stdio command works in any MCP-capable
client.

## Tools

| Tool | Description |
|------|-------------|
| `get_legal_skill` | Reasoning guide for a legal domain (not statute text) |
| `get_regulation_source` | Hand-written summary; explicitly `hand_written_summary` |
| `get_legal_context` | Skill + source + risks for a contract type |
| `search_contract_risks` | Contract risk dataset with evidence policy |
| `list_legal_domains` | Domains and provenance distribution |
| `get_source_status` | Manifest status and freshness warnings |
| `report_source_issue` | Local issue report (opt-in) |
| `search_legal_provision` | Corpus-first search; returns `quotes` with `official_verbatim` |
| `get_legal_brief` | Brief assembled from skill + provisions + risks |

## Data layout

- `data/sources/` — 20 hand-written summaries, each section linked to its document.
- `data/corpus/` — verbatim articles (Labor 245, Civil Transactions 721, PDPL 43,
  PDPL Implementing Regulation 38), with `fetched_at`, `sha256`, and provenance.
- `data/skills/` — reasoning guides; each starts with a "not statute text" banner.

See `../docs/corpus.md` and `../docs/source-coverage-2026-11.md`.
