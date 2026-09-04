# Saudi Legal AI Eval Harness

A dedicated evaluation harness for measuring the accuracy and legal reliability of the Saudi Legal AI Framework's tools and prompts.

## Purpose
This evaluation benchmark ensures that AI models return accurate, legally sound responses based on official Saudi Arabian laws and regulations. It is not intended to validate LLMs for providing direct legal advice, but rather to benchmark their retrieval and reasoning within the bounded context of the provided legal sources.

## Structure
- `schema.json`: The JSON schema defining an evaluation case.
- `source-registry.json`: Official mapping of all sources referenced in the cases.
  Since schema v2.0 it also carries machine-readable watch metadata
  (`citation`, `source_file`, `monitor.signals`) for the weekly
  regulation-watch — see [docs/regulation-watch.md](../docs/regulation-watch.md).
  The original five entries' `name/decree/date/url` values are frozen for validator compatibility.
- `cases/`: Contains the test cases split by legal domains (e.g., Labor Law, PDPL).
- `validate_cases.py`: Script to validate that all JSON cases adhere strictly to `schema.json`.
- `results/`: Directory (git-ignored) for storing evaluation outputs locally.

## Guidelines for Adding Cases
1. **Never rely on memory:** All cases must be strictly backed by an official source (e.g., BOE laws).
2. **Be specific:** Provide the exact Article or Paragraph in `source_locator`.
3. **Draft Status:** All new cases should start with `status: draft` until verified by a domain expert.

## Running Validations
```bash
pip install -r requirements-dev.txt
python3 evals/validate_cases.py
python3 -m pytest tests/test_eval_validator.py -q
```
