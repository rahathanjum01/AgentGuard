# 🛡️ AgentGuard

AgentGuard is a runtime safety gateway for transaction-oriented AI agents. It validates context before an agent can act, returns an explainable allow or block decision, and records audit evidence.

## What this project does

- Validates document trust through a retrieval adapter with an explicit local demo mode
- Provides a server-side Moss adapter boundary with fail-closed error handling
- Blocks risky actions like payment or file deletion when trust is too low
- Detects known attack patterns such as injection, tampered amounts, and stale reuse
- Inspects untrusted document text and transaction fields before execution (prompt injection, amount mismatch, duplicate invoice, expired approval)
- Triggers a honeypot trap to mislead bad actors
- Stores an application-level hash-chain audit ledger for evidence and traceability
- Shows everything in a Streamlit dashboard

## Key demo features

- Runtime guardrail decisions before agent execution
- Trust scoring and latency tracking
- Honeypot-style attacker baiting
- Explainable audit chain with linked evidence
- Interactive UI for testing attack patterns

## Requirements

- Python 3.12 recommended
- pip
- A virtual environment is recommended

## Run locally

From the project root:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\.venv\Scripts\streamlit.exe run app.py
```

Then open the local URL shown in the terminal, typically:

```text
http://localhost:8501
```

## Example test inputs

The app includes a few sample hashes and attack values:

- Trusted document: `a1b2c3d4e5f6g7h8`
- Medium-trust review case: `d4e5f6g7h8i9j0k1`
- Risky injection case: `hacker_inject_999`
- Reuse or stale case: `stale_reuse_001`
- Tampered amount example: `tampered_amt_1`

## Project structure (5 Architectural Layers)

AgentGuard is structured into 5 architectural layers matching `architecture.pdf`:

- **Layer 1: Gateway Layer (`src/gateway/`)**: API Gateway (`api.py`), Pydantic models (`api_models.py`)
- **Layer 2: Context Retrieval Layer (`src/retrieval/`)**: Moss client (`moss_client.py`), retrieval orchestrator (`retrieval_service.py`), local demo provider (`local_retrieval.py`), schemas (`retrieval_models.py`)
- **Layer 3: Policy Evaluation Layer (`src/policy/`)**: Deterministic policy engine (`policy_engine.py`), normalizer (`context_normalizer.py`), validator (`moss_validator.py`), policy models (`policy_models.py`), evaluation suite (`evaluator.py`, `evaluation_cases.py`)
- **Layer 4: Execution & Review Layer (`src/execution_review/`)**: Tool execution boundary (`execution_service.py`), models (`execution_models.py`), human review service (`review_service.py`, `review.py`)
- **Layer 5: Audit & Security Layer (`src/audit_security/`)**: Hash-chain ledger (`blockchain.py`), audit coordinator (`audit_service.py`), content security analyzer (`security_analysis.py`), honeypot tracer (`security_service.py`, `honeypot.py`)
- `app.py` — Streamlit interactive UI dashboard
- `docs/architecture.md` & `docs/architecture.pdf` — system architecture specifications
- `docs/PRD.md` — product requirements and evaluation criteria
- `tests/` — comprehensive unit and behavioral test suite
- `requirements.txt` — Python dependencies

## Moss integration

Moss integration is implemented in `src/retrieval/moss_client.py` using the official Python SDK.

The adapter:

- Loads the configured index (the deployed demo uses `agentguard-context-v2`)
- Queries Moss with `MossClient` and `QueryOptions(top_k=1)` plus an exact `doc_hash` metadata filter, so a semantically similar record cannot authorize a different document
- Maps Moss score and metadata into AgentGuard trust evidence
- Reports successful retrieval as `MOSS`
- Uses `LOCAL_DEMO` only when Moss is not configured
- Returns `MOSS_ERROR` with zero trust when Moss fails

Configure these values only through Streamlit Cloud Secrets or local `.streamlit/secrets.toml`:

```toml
MOSS_PROJECT_ID = "your-project-id"
MOSS_PROJECT_KEY = "your-project-key"
MOSS_INDEX_NAME = "agentguard-context-v2"
# Optional. Moss is enabled automatically when both credentials are present.
# Set to "false" only to deliberately use LOCAL_DEMO.
MOSS_ENABLED = "true"
```

Seed the committed, non-secret demo corpus into a new Moss project index:

```bash
$env:MOSS_PROJECT_ID = "your-project-id"
$env:MOSS_PROJECT_KEY = "your-project-key"
python scripts/seed_moss.py
```

This is an explicit one-time cloud mutation. If `agentguard-context` already exists, the script leaves it unchanged and does not download it again. To test a newly-created index explicitly, append `--verify`; do not use this option repeatedly. To create a fresh index without deleting data, set the same custom name for both seeding and the application:

```powershell
$env:MOSS_INDEX_NAME = "agentguard-context-v2"
python scripts/seed_moss.py
```

Set `MOSS_INDEX_NAME = "agentguard-context-v2"` in Streamlit secrets (or the API environment) when running the app. Never delete or overwrite an existing cloud index merely to rerun this demo setup.

If Moss reports that it cannot decode an existing index download, do not delete the index. Set `MOSS_INDEX_NAME` to a new value such as `agentguard-context-v2`, reboot the Streamlit app, and use the sidebar **Repair Moss index** control to explicitly create the new corpus index. It creates only the newly named index and leaves existing cloud data untouched.

Moss activates automatically when credentials are present (unless `MOSS_ENABLED=false`). The process downloads and loads the selected index locally before querying it and caches up to 256 document-hash lookups. Initial index loading is not a query-latency claim; steady-state queries run against the local Moss runtime. An index-load failure is reported as `MOSS_ERROR` and blocks sensitive actions rather than being presented as a successful Moss result. Restart the app after changing credentials or index settings.

Before opening the app, verify the exact project and index without modifying cloud data:

```powershell
.venv\Scripts\python.exe scripts/check_moss.py
```

The application reads these settings only at runtime. Credentials are never returned in decision payloads or audit entries.

The `REVIEW` path creates a pending in-memory human-review request and prevents tool execution. The review queue is intentionally a prototype service boundary; production use requires durable storage and authenticated reviewer actions.

The audit ledger is an application-level hash chain, not an external blockchain. This is a prototype for product evaluation and hackathon demonstration, not a production security system.

The demo models an agent tool call: a request is evaluated before the tool is marked as executed. `ALLOW` executes the request; `BLOCK` and `REVIEW` prevent autonomous execution.

The Evaluation tab runs 12 deterministic cases across trusted actions, ambiguous context, prompt injection, tampering, stale context, unknown vendors, and unauthorized actions. It reports per-case results, category accuracy, median latency, and p95 latency.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Run the gateway API

Install the dependencies, then start FastAPI with Uvicorn:

```bash
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

OpenAPI documentation:

```text
http://127.0.0.1:8000/docs
```

Example request:

```bash
curl -X POST http://127.0.0.1:8000/v1/guard/tool-request \
	-H "Content-Type: application/json" \
	-d '{"action":"payment","doc_hash":"a1b2c3d4e5f6g7h8"}'
```

The API returns `ALLOW`, `BLOCK`, or `REVIEW` in the response body. Only `ALLOW` can execute a tool. Invalid requests return `422`. The Streamlit app and FastAPI gateway are separate runtime surfaces; deploying the Streamlit demo does not automatically deploy the API.

### Content-security request example

The guard accepts optional untrusted context and transaction verification fields. These are inspected independently of the document identifier; matching amounts are required when both are supplied.

```json
{
  "action": "payment",
  "doc_hash": "a1b2c3d4e5f6g7h8",
  "context_text": "Invoice review notes",
  "transaction": {
    "invoice_amount": "6000.00",
    "approved_amount": "5000.00"
  }
}
```

This request is blocked with `AMOUNT_MISMATCH`. Context containing instruction-override language is blocked with `PROMPT_INJECTION`. The response includes sanitized finding codes and the audit entry records those codes, not the source text.

## Benchmark latency honestly

Run the reproducible benchmark from the project root:

```bash
python scripts/benchmark.py --iterations 100
```

It reports retrieval and end-to-end p50/p95 separately and prints active retrieval modes. A run is a Moss benchmark only when every sample reports `MOSS`; otherwise the output explicitly says that it is not a Moss benchmark. Configure the Moss credentials above and populate the configured index (for the deployed demo, `agentguard-context-v2`) before recording Moss results.

When `MOSS_ENABLED=true`, the benchmark first performs one Moss preflight request. If it cannot retrieve through Moss, it stops before the full run to conserve cloud usage.

The gateway connects to retrieval through `src/retrieval_service.py`. That service selects the Moss adapter when configured, uses the `LOCAL_DEMO` provider only when Moss is not configured, normalizes the result, and fails closed with `MOSS_ERROR` when a configured provider fails. Retrieval evidence is returned separately from the policy decision; retrieval alone never authorizes a tool.

## Policy evaluation

The deterministic Python policy engine evaluates normalized retrieval evidence using policy version `agentguard-default-v1`:

- trust below `0.70` blocks the request with `LOW_TRUST`
- payment trust below `0.90` blocks the request with `HIGH_RISK_THRESHOLD`
- trust from `0.70` up to but not including `0.85` requires review with `REVIEW_REQUIRED`
- trusted evidence at or above `0.85` allows non-payment actions with `CONTEXT_ACCEPTED`
- missing, failed, unknown-status, or unknown-source retrieval blocks the request

The API returns the policy name, version, reason code, human-readable reason, and retrieval evidence together. OPA and LangGraph are future adapter options, not current runtime dependencies.

## Execution, review, and security flow

The end-to-end path is shared by the API and Streamlit UI:

- `ALLOW` enters the Python execution service and returns a simulated execution result. No external payment, email, file, or contract tool is called by this prototype.
- `REVIEW` creates one pending in-memory review request and remains non-executable.
- `BLOCK` prevents execution. Suspicious identifiers such as injection, tampering, stale, or fake markers can create a sanitized demo security trace.
- Every request is recorded by the application hash-chain audit service, including policy provenance, execution status, review id, and security trace id when present.
- `GET /v1/reviews`, `GET /v1/audit`, and `GET /v1/audit/verify` expose read-only inspection for the demo.

The reference architecture supplied for the hackathon is documented as a production target. PostgreSQL, OPA, LangGraph, OpenTelemetry, React/Node.js, and Rust are not claimed as current runtime dependencies.
