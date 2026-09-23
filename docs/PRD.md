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
5. The guarded tool executes only for `ALLOW`; `BLOCK` and `REVIEW` prevent autonomous execution.
6. The application audit chain records the decision, latency, and previous block reference.
7. Suspicious blocked inputs may activate a honeypot trace for investigation.

## Security requirements

- Unknown or low-trust context must be blocked for sensitive actions.
- Payment actions require a higher trust threshold than low-risk reads.
- Decisions must include an explanation and evidence fields.
- Audit entries must preserve ordering through a previous-hash reference.
- Secrets must be supplied through environment configuration and never committed.

## Evaluation requirements

The demo must cover trusted input, prompt injection, tampered amount, stale or duplicate reuse, unauthorized action, and an ambiguous case. Each case must report expected decision, actual decision, pass/fail status, and measured latency.

## Latency requirement

When configured, Moss downloads the selected index and performs steady-state semantic retrieval locally. Initial index loading is reported separately from query timing. `LOCAL_DEMO` is used only when Moss is not configured, and a configured Moss load/query failure returns `MOSS_ERROR` and fails closed. Moss benchmark claims require every measured request to report retrieval mode `MOSS`.

## Moss retrieval requirements

- The configured index name, such as `agentguard-context-v2`, must be explicit in deployment secrets.
- Retrieval for a document identifier must filter Moss metadata on the exact `doc_hash`; semantic similarity alone must not authorize another document.
- If a cloud index cannot be decoded by the SDK, the operator creates a newly named index from the committed corpus. Existing cloud indexes are not overwritten or deleted by the app.
- A `REVIEW` context creates a human-review request for non-payment actions and blocks payment actions.

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
