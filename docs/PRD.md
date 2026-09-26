# AgentGuard Product Requirements

## Problem

AI agents can act on stale, tampered, injected, or unauthorized context. A payment or file operation performed without a fast safety check can create financial and operational damage.

## Target user

Teams deploying transaction-oriented AI agents, initially accounts-payable workflows that review invoices and initiate payments.

## Product promise

Before an agent performs a sensitive action, AgentGuard retrieves relevant context, evaluates the action against policy, returns an explainable decision, and records evidence.

## Primary workflow

1. An agent submits a tool request with an action and document or transaction identifier.
2. AgentGuard retrieves relevant context through the configured retrieval adapter.
3. The policy evaluator calculates trust and checks the requested action.
4. AgentGuard returns `ALLOW`, `BLOCK`, or `REVIEW` with a reason and evidence.
5. The payment sandbox writes a fabricated local record only for `ALLOW`; other allowed actions are simulated, while `BLOCK` and `REVIEW` prevent autonomous execution.
6. The application audit chain records the decision, latency, and previous block reference.
7. Selected suspicious blocked inputs create a security trace; investigators may read a fabricated decoy record that cannot invoke tools.

## Security requirements

- Unknown or low-trust context must be blocked for sensitive actions.
- Payment actions require a higher trust threshold than low-risk reads.
- Decisions must include an explanation and evidence fields.
- Sensitive invoice facts must be checked against a separate approval/vendor source; request-supplied approval values are not authoritative.
- Every sensitive request must validate retrieved document identity and freshness; missing or conflicting approval evidence must fail closed.
- Reviewer decisions are stored durably; API write routes can require a configured bearer token.
- Reviewer feedback is linked to an audit decision and does not automatically change policy.
- Audit entries must preserve ordering through a previous-hash reference.
- Secrets must be supplied through environment configuration and never committed.

## Evaluation requirements

The demo must evaluate retrieval correctness, policy decisions against controlled context fixtures, and end-to-end requests separately. It must cover trusted input, varied prompt injection, benign lookalikes, tampered amount, stale or duplicate reuse, unauthorized action, and ambiguous context. Reports include false allows, false blocks, unexpected reviews, and per-stage latency.

## Latency requirement

When configured, Moss downloads the selected index and performs steady-state semantic retrieval locally. Initial index loading is reported separately from query timing. `LOCAL_DEMO` is used only when Moss is not configured, and a configured Moss load/query failure returns `MOSS_ERROR` and fails closed. Moss benchmark claims require every measured request to report retrieval mode `MOSS`.

## Moss retrieval requirements

- The configured index name, such as `agentguard-context-v2`, must be explicit in deployment secrets.
- Retrieval for a document identifier must filter Moss metadata on the exact `doc_hash`; semantic similarity alone must not authorize another document.
- If a cloud index cannot be decoded by the SDK, the operator creates a newly named index from the committed corpus. Existing cloud indexes are not overwritten or deleted by the app.
- A `REVIEW` context creates a human-review request for non-payment actions and blocks payment actions.

## Evaluation and trace requirements

- Retrieval correctness is evaluated separately from policy decisions; end-to-end cases exercise both with request text and transaction fields.
- Retrieval query, Moss index loading, policy evaluation, security validation, tool boundary, and total guard latency are reported separately.
- The application hash chain links suspicious-request trace IDs, sandbox records, and human review outcomes to their decision records.

## Non-goals for the sprint

- Building a real cryptocurrency or external blockchain network
- Supporting every agent framework
- Replacing a complete identity and access management system
- Claiming production reliability from a small demo corpus

## Success criteria

- A judge can run the demo from the README.
- A judge can see an allow and block decision in under two minutes.
- The Moss retrieval role is visible and technically honest.
- Evaluation results and latency are reproducible.
- The repository includes architecture, PRD, tests, and deployment instructions.
