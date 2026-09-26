# 🛡️ AgentGuard

AgentGuard is a runtime safety gateway for transaction-oriented AI agents. It validates context before an agent can act, returns an explainable allow or block decision, and records audit evidence.

## What this project does

- Validates document trust through a retrieval adapter with an explicit local demo mode
- Provides a server-side Moss adapter boundary with fail-closed error handling
- Blocks risky actions like payment or file deletion when trust is too low
- Detects known attack patterns such as injection, tampered amounts, and stale reuse
- Inspects untrusted document text and transaction fields before execution (prompt injection, amount mismatch, duplicate invoice, expired approval)
- Offers a read-only fabricated decoy record after selected suspicious requests and logs decoy access
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

The `REVIEW` path creates a pending SQLite-backed review request and prevents tool execution. API review decisions can require a bearer token through `AGENTGUARD_REVIEW_TOKEN`; without that setting, reviewer IDs are demo labels rather than authenticated identities. The Streamlit review console is a local demo surface.

The audit ledger is an application-level hash chain, not an external blockchain. This is a prototype for product evaluation and hackathon demonstration, not a production security system.

The demo checks a request before the tool boundary. An allowed payment writes one idempotent, fabricated payment record to `sandbox_payments.db`, using the independent approval fixture. Other allowed tool actions return simulated results. No bank, processor, email, file, or contract service is called; `BLOCK` and `REVIEW` prevent execution.

The Evaluation tab separates retrieval evidence checks, policy-only checks, and end-to-end trusted, adversarial, and benign-lookalike cases. It reports per-case outcomes, category accuracy, false allows, false blocks, unexpected reviews, and latency by stage. Cases that miss their expected decision remain visible as failures.

The audit ledger stores a full SHA-256 application hash chain. It links request IDs, sandbox records, review outcomes, security trace IDs, and stage timings. This is tamper-evident local application storage, not an external blockchain or protection against an operator who can rewrite the entire database.

Selected blocked suspicious requests create a trace and expose a read-only fabricated decoy through the **Honeypot Decoy** tab or `GET /v1/honeypot/decoys/{trace_id}`. Viewing the decoy appends an OpenTelemetry-shaped event to the ignored local `honeypot_events.jsonl`; it cannot execute tools. The **Decision Feedback** tab records reviewer labels for audit blocks; labels do not automatically change policy.

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

Configure reviewer authentication for API review decisions and feedback by setting `AGENTGUARD_REVIEW_TOKEN` in the API environment. Send it as `Authorization: Bearer <token>`. If unset, those prototype endpoints accept the supplied reviewer ID as an unauthenticated demo label.

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

It reports Moss index-load and query time, guardrail stages, end-to-end p50/p95, and active retrieval modes. A run is a Moss benchmark only when every sample reports `MOSS`; otherwise the output explicitly says that it is not a Moss benchmark. Configure the Moss credentials above and populate the configured index (for the deployed demo, `agentguard-context-v2`) before recording Moss results.

When Moss credentials are configured (and `MOSS_ENABLED` is not explicitly `false`), the benchmark first performs one Moss preflight request. If it cannot retrieve through Moss, it stops before the full run to conserve cloud usage.

The gateway connects to retrieval through `src/retrieval/retrieval_service.py`. That service selects Moss when configured, uses `LOCAL_DEMO` only when Moss is not configured, joins retrieved invoice IDs to the separate approval fixture, and fails closed with `MOSS_ERROR` when a configured provider fails. Retrieval and policy quality have separate evaluation suites; retrieval alone never authorizes a tool.

For the fabricated AP demo, invoice documents live in `agentguard-context.json` and independent purchase-order/vendor approval facts live in `approval_records.json`. Every retrieved payment context is checked for matching document identity, validity date, and a matching approval record; invoice amount, vendor, bank details, paid state, and approval expiry are compared with that separate fixture. A caller-provided `approved_amount` is not treated as the trusted approval value. These files are demonstration fixtures, not a connection to a real finance system.

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

- `ALLOW` reaches the Python execution service. Payments create a local, idempotent sandbox ledger record; other actions are simulated.
- `REVIEW` creates a durable pending SQLite review request and remains non-executable until resolved.
- `BLOCK` prevents execution. Selected suspicious requests create a trace; reading the associated fabricated decoy logs an access event.
- Every request is recorded by the application hash-chain audit service, including policy provenance, execution status, review ID, sandbox payment ID, stage latency, and security trace ID when present.
- `GET /v1/reviews`, `GET /v1/audit`, and `GET /v1/audit/verify` expose read-only inspection for the demo.
- `GET /v1/feedback` and `POST /v1/feedback` expose the reviewer feedback loop; `GET /v1/honeypot/decoys/{trace_id}` returns only fabricated read-only data.

The reference architecture supplied for the hackathon is documented as a production target. PostgreSQL, OPA, LangGraph, OpenTelemetry, React/Node.js, and Rust are not claimed as current runtime dependencies.

## Final-round walkthrough

1. In Guardrail, select **Sample invoice: verified HAL INV101** and run a payment. Show the independent approval, `ALLOW`, and sandbox payment record ID.
2. Select **Sample invoice: amount conflicts with PO**. Show the block and the invoice/approval amount difference.
3. Select **Sample invoice: first-time vendor**. Show payment blocked because there is no matched approval.
4. Open Evaluation and explain the retrieval, policy-only, and end-to-end results, including any remaining failures.
5. If a suspicious case creates a trace, open Honeypot Decoy, read the fabricated record, then show its trace ID in the audit entry. No real payment was attempted.
6. Open Decision Feedback to label an audit outcome. Feedback is saved for later evaluation review and does not silently change policy.
