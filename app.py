import hmac
import os
import time
import pandas as pd
import streamlit as st

from src.agent import guarded_tool_call
from src.audit_security.audit_service import get_audit_events, record_audit_event, verify_audit_chain
from src.audit_security.feedback import get_decision_feedback, record_decision_feedback
from src.audit_security.honeypot import honeypot_trap, read_decoy_record
from src.execution_review.execution_service import execute_tool, get_sandbox_payments
from src.execution_review.review_service import decide_and_execute_review, list_reviews
from src.policy.evaluation_cases import (
    EVALUATION_CASES,
    POLICY_EVALUATION_CASES,
    RETRIEVAL_EVALUATION_CASES,
)
from src.policy.evaluator import (
    evaluate_batch,
    evaluate_policy_batch,
    evaluate_retrieval_batch,
)
from src.policy.moss_validator import runtime_guard
from src.retrieval.moss_client import MossIntegrationError, initialize_moss_index, moss_configuration
from src.retrieval.retrieval_service import retrieve_context

st.set_page_config(page_title="AgentGuard - Runtime Guardrails", layout="wide", page_icon="🛡️")

moss_config = moss_configuration()
if moss_config["configured"]:
    st.sidebar.success(f"Moss configured · index: {moss_config['index_name']}")
else:
    st.sidebar.warning(
        "Moss is not configured; decisions currently use LOCAL_DEMO. "
        "Add project credentials to .streamlit/secrets.toml."
    )

# --- UI Styling ---
st.markdown(
    """
    <style>
    .block-container { max-width: 1200px; padding-top: 2rem; }
    .eyebrow { color: #16a085; font-size: 0.76rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; }
    .hero { border-bottom: 1px solid #d9e2df; padding-bottom: 1.2rem; margin-bottom: 1.5rem; }
    .hero h1 { color: #102a2a; font-size: 2.7rem; letter-spacing: -0.04em; margin: 0.25rem 0 0.5rem; }
    .hero p { color: #526563; font-size: 1.05rem; max-width: 780px; }
    .decision { border-radius: 10px; padding: 1.3rem 1.5rem; margin: 1rem 0; border: 1px solid; }
    .decision h2 { margin: 0 0 0.35rem; }
    .decision p { margin: 0; color: #435653; }
    .allow { background: #eaf8f1; border-color: #78c9a5; }
    .block { background: #fff0ed; border-color: #ee9c8d; }
    .review { background: #fff8e5; border-color: #e7c66b; }
    .result-row { border-radius: 8px; padding: 0.7rem 0.9rem; margin: 0.45rem 0; border: 1px solid; }
    .result-row strong { color: #203331; }
    .result-row p { margin: 0.25rem 0 0; color: #526563; font-size: 0.9rem; }
    .result-allow { background: #f1fbf6; border-color: #a4d9bd; }
    .result-block { background: #fff5f2; border-color: #efb0a5; }
    .result-review { background: #fffaf0; border-color: #ecd58c; }
    .status-badge { display: inline-block; border-radius: 999px; padding: 0.16rem 0.55rem; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em; }
    .badge-allow { background: #d5f2e2; color: #17663d; }
    .badge-block { background: #ffdcd6; color: #9c2f22; }
    .badge-review { background: #ffedb8; color: #795900; }
    .badge-pending { background: #fff3cd; color: #856404; }
    .badge-approved { background: #d4edda; color: #155724; }
    .badge-rejected { background: #f8d7da; color: #721c24; }
    .arena-card { border-radius: 10px; padding: 1.2rem; border: 1px solid #d9e2df; background: #ffffff; height: 100%; }
    .arena-highlight { border-color: #16a085; background: #f0faf7; box-shadow: 0 4px 12px rgba(22, 160, 133, 0.1); }
    </style>
    <div class="hero">
      <div class="eyebrow">YC Fall 2026 x Moss · The Zero Latency Builder Sprint</div>
      <h1>AgentGuard</h1>
      <p>Prototype runtime guard for transaction-oriented agents. Retrieves context through Moss when configured, applies explainable allow/block/review policies, writes allowed payments to a local sandbox, and records an application-level audit trail.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

test_cases = [
    (case["doc_hash"], case["name"], case["action"])
    for case in EVALUATION_CASES
]
test_cases.extend([
    ("safe_invoice_101", "Sample invoice: verified HAL INV101", "payment"),
    ("safe_invoice_202", "Sample invoice: verified SafeCorp INV202", "payment"),
    ("mismatch_amount_301", "Sample invoice: amount conflicts with PO", "payment"),
    ("duplicate_invoice_401", "Sample invoice: already paid", "payment"),
    ("bank_change_501", "Sample invoice: vendor bank details changed", "payment"),
    ("new_vendor_601", "Sample invoice: first-time vendor", "payment"),
])
evaluation = evaluate_batch(EVALUATION_CASES, runtime_guard)
retrieval_evaluation = evaluate_retrieval_batch(RETRIEVAL_EVALUATION_CASES, retrieve_context)
policy_evaluation = evaluate_policy_batch(POLICY_EVALUATION_CASES)
moss_runtime = moss_configuration()
evaluation_modes = sorted({item["result"]["retrieval_mode"] for item in evaluation["results"]})
if moss_runtime.get("error"):
    st.sidebar.error(
        f"Moss could not load index {moss_runtime['index_name']!r}: "
        f"{moss_runtime['error']}"
    )
elif moss_runtime["configured"] and evaluation_modes == ["MOSS"]:
    st.sidebar.success("Moss index loaded and retrieval is active.")

with st.sidebar.expander("Repair Moss index"):
    st.caption(
        "Use only after setting MOSS_INDEX_NAME to a new name, such as "
        "agentguard-context-v2. This creates that new index from the demo corpus; "
        "it never changes or deletes the existing index."
    )
    moss_active = moss_runtime["configured"] and evaluation_modes == ["MOSS"]
    if moss_active:
        st.success("No repair needed: the configured Moss index is already loaded.")
    elif st.button("Create configured Moss index", key="create_moss_index"):
        try:
            created_index = initialize_moss_index()
            st.success(
                f"Created {created_index['index_name']} with "
                f"{created_index['document_count']} documents. Reloading Moss."
            )
            st.rerun()
        except MossIntegrationError as error:
            st.error(f"Could not create Moss index: {error.__cause__ or error}")


def format_latency(latency_ms):
    return "<0.01 ms" if latency_ms < 0.01 else f"{latency_ms:.2f} ms"


def _review_auth_token():
    token = os.getenv("AGENTGUARD_REVIEW_TOKEN")
    if token:
        return token
    try:
        return st.secrets["AGENTGUARD_REVIEW_TOKEN"]
    except (KeyError, FileNotFoundError):
        return None


guard_tab, review_tab, arena_tab, evaluation_tab, audit_tab, sandbox_tab, honeypot_tab, feedback_tab = st.tabs([
    "🛡️ Guardrail",
    "📋 Human Review Queue",
    "⚡ Latency",
    "🧪 Evaluation",
    "⛓️ Audit Trail",
    "🧪 Sandbox Payments",
    "🪤 Honeypot Decoy",
    "📝 Decision Feedback",
])

# ==============================================================================
# TAB 1: GUARDRAIL CONSOLE
# ==============================================================================
with guard_tab:
    left, right = st.columns([0.85, 1.15], gap="large")
    with left:
        st.markdown("#### Test an agent request")
        scenario_names = [name for _, name, _ in test_cases]
        selected_name = st.selectbox("Scenario", scenario_names)
        selected_hash, _, default_action = next(item for item in test_cases if item[1] == selected_name)
        doc_hash_input = st.text_input("Context identifier", value=selected_hash)
        agent_action = st.selectbox(
            "Requested action",
            ["payment", "read_email", "delete_file", "send_contract", "approve_po"],
            index=["payment", "read_email", "delete_file", "send_contract", "approve_po"].index(default_action),
        )
        context_text = st.text_area(
            "Untrusted document or agent context (optional)",
            placeholder="Paste invoice notes or retrieved text. Instruction-override attempts are blocked.",
            max_chars=10_000,
        )
        with st.expander("Transaction verification fields (optional)"):
            invoice_amount = st.text_input("Invoice amount", placeholder="5000.00")
            approved_amount = st.text_input("Approved amount", placeholder="5000.00")
            duplicate_invoice = st.checkbox("Invoice was previously paid / is duplicate")
            expired_approval = st.checkbox("Approval has expired")
        st.caption("Moss is used when configured. The decision always shows the active retrieval mode.")
        run_check = st.button("Run guardrail check", use_container_width=True, type="primary")

    with right:
        st.markdown("#### Decision console")
        if run_check:
            transaction = {
                "invoice_amount": invoice_amount or None,
                "approved_amount": approved_amount or None,
                "is_duplicate": duplicate_invoice,
                "approval_expired": expired_approval,
            }
            agent_request = guarded_tool_call(agent_action, doc_hash_input, context_text, transaction)
            result = agent_request["guard"]
            trap = honeypot_trap(
                doc_hash_input, not result["allow"], result.get("security_findings")
            )
            ledger_block = record_audit_event(
                doc_hash_input,
                result,
                agent_action,
                execution=agent_request["execution"],
                review=agent_request["review_request"],
                security_trace=trap,
            )
            decision_class = result["decision"].lower()
            st.markdown(
                f'<div class="decision {decision_class}"><h2>{result["decision"]}</h2><p>{result["reason"]}</p></div>',
                unsafe_allow_html=True,
            )
            metric_one, metric_two, metric_three = st.columns(3)
            metric_one.metric("Trust", f"{result['trust'] * 100:.0f}%")
            metric_two.metric("Retrieval Latency", format_latency(result["latency"]))
            metric_three.metric("Mode", result["retrieval_mode"])
            st.caption(f"Retrieval source: {result['retrieval_mode']}")
            st.write(f"**Evidence:** {result['doc']} · {result['vendor']}")
            st.caption(
                f"Policy: {result['policy_name']} {result['policy_version']} · "
                f"Reason code: {result['reason_code']}"
            )
            context_evidence = result.get("evidence", {})
            approval_evidence = context_evidence.get("verified_approval") or {}
            with st.expander("Context validation evidence"):
                st.write(
                    f"**Document identity:** {doc_hash_input} · **Retrieved status:** {result['status']} · "
                    f"**Document validity:** {context_evidence.get('valid_until', 'not supplied')}"
                )
                if approval_evidence:
                    st.write(
                        f"**Matched approval:** {approval_evidence.get('purchase_order', 'n/a')} · "
                        f"{approval_evidence.get('vendor', 'Unknown vendor')} · "
                        f"approved {approval_evidence.get('approved_amount', 'n/a')}"
                    )
                    st.write(
                        f"**Verified bank ending:** {approval_evidence.get('bank_account_last4', 'n/a')} · "
                        f"**Paid:** {approval_evidence.get('paid', 'unknown')} · "
                        f"**Approval expires:** {approval_evidence.get('approval_expiry', 'not set')}"
                    )
                else:
                    st.warning("No independent approval record matched this invoice.")
                st.write(f"**Document valid until:** {context_evidence.get('valid_until', 'not supplied')}")
                if result.get("security_findings"):
                    st.write("**Validation findings:** " + " · ".join(
                        finding["code"] for finding in result["security_findings"]
                    ))
            if result.get("security_findings"):
                st.error("Content findings: " + " · ".join(
                    finding["code"] for finding in result["security_findings"]
                ))
            if trap["activated"]:
                st.warning(f"Honeypot trace activated: {trap['trace_id']}")
                st.session_state["latest_honeypot_trace_id"] = trap["trace_id"]
                if not trap.get("telemetry_recorded", False):
                    st.error("The suspicious request was blocked, but the local trace file could not be written.")
            st.write(f"**Tool execution:** {'Executed' if agent_request['executed'] else 'Prevented'}")
            st.caption(
                f"Execution service: {agent_request['execution']['status']} · "
                f"Request: {agent_request['request_id']}"
            )
            st.write(agent_request["execution"]["result"])
            if agent_request["execution"].get("sandbox_record_id"):
                st.success(f"Sandbox payment record: {agent_request['execution']['sandbox_record_id']}")
            with st.expander("Latency trace by stage"):
                st.json(agent_request.get("stage_latency_ms", {}))
            if agent_request["review_request"]:
                st.warning(
                    f"📋 Human review queued: {agent_request['review_request']['review_id']} "
                    "— Open the 'Human Review Queue' tab to inspect and approve."
                )
            with st.expander("View decision payload"):
                st.json(agent_request)
            with st.expander("View audit entry"):
                st.json(ledger_block)
        else:
            st.info("Choose a scenario and run the check to see whether the agent may proceed.")

# ==============================================================================
# TAB 2: HUMAN REVIEW QUEUE (HITL CONSOLE)
# ==============================================================================
with review_tab:
    st.markdown("#### 📋 Human-in-the-Loop Review Console")
    reviewer_id = st.text_input("Reviewer ID", value="demo-operator", max_chars=120)
    expected_review_token = _review_auth_token()
    if expected_review_token:
        supplied_review_token = st.text_input("Reviewer authentication token", type="password")
        reviewer_authenticated = hmac.compare_digest(supplied_review_token, expected_review_token)
        if not reviewer_authenticated:
            st.warning("Enter the configured reviewer token to approve or reject requests.")
    else:
        reviewer_authenticated = True
        st.warning("Demo mode: no reviewer token is configured, so reviewer IDs are labels only. Set AGENTGUARD_REVIEW_TOKEN to require authentication.")
    st.caption(
        "Ambiguous or medium-trust agent actions (70%–85% trust) require explicit human operator review. "
        "Tool execution remains prevented until approved."
    )

    all_reviews = list_reviews()
    pending_count = sum(1 for r in all_reviews if r["status"] == "PENDING")
    approved_count = sum(1 for r in all_reviews if r["status"] == "APPROVED")
    rejected_count = sum(1 for r in all_reviews if r["status"] == "REJECTED")

    col_q1, col_q2, col_q3, col_q4 = st.columns(4)
    col_q1.metric("Total in Queue", len(all_reviews))
    col_q2.metric("Pending Review", pending_count)
    col_q3.metric("Approved Overrides", approved_count)
    col_q4.metric("Rejected Blocks", rejected_count)

    st.divider()

    # Convenience button for hackathon judges to seed a review case instantly
    if not all_reviews:
        st.info("No reviews currently in the queue. Click below to simulate an ambiguous transaction requiring human review.")
        if st.button("📥 Trigger Sample Review Request (New Vendor Invoice INV104)", type="secondary"):
            sample_request = guarded_tool_call("read_email", "d4e5f6g7h8i9j0k1")
            if sample_request["review_request"]:
                st.rerun()
            else:
                st.error(
                    "The sample request did not enter human review: "
                    f"{sample_request['guard']['reason_code']}"
                )
    else:
        top_bar_left, top_bar_right = st.columns([0.8, 0.2])
        with top_bar_right:
            if st.button("📥 Add Sample Review", help="Queue an ambiguous review case for testing"):
                sample_request = guarded_tool_call("read_email", "d4e5f6g7h8i9j0k1")
                if sample_request["review_request"]:
                    st.rerun()
                else:
                    st.error(
                        "The sample request did not enter human review: "
                        f"{sample_request['guard']['reason_code']}"
                    )

        for req in reversed(all_reviews):
            status = req["status"]
            badge_class = f"badge-{status.lower()}"
            with st.container():
                st.markdown(
                    f"""
                    <div class="result-row result-{'allow' if status == 'APPROVED' else 'block' if status == 'REJECTED' else 'review'}">
                      <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong><code>{req['review_id']}</code> · Action: <code>{req['action']}</code></strong>
                        <span class="status-badge {badge_class}">{status}</span>
                      </div>
                      <p><strong>Target Context:</strong> <code>{req['doc_hash']}</code> · <strong>Vendor:</strong> {req.get('vendor', 'UNKNOWN')}</p>
                      <p><strong>Trust:</strong> {req['trust'] * 100:.0f}% · <strong>Reason:</strong> {req['reason']}</p>
                      <p style="font-size: 0.78rem; color: #7f8c8d;">Created: {req.get('created_at', 'Session')}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if status == "PENDING":
                    btn_c1, btn_c2, _ = st.columns([0.3, 0.3, 0.4])
                    with btn_c1:
                        if st.button("✅ Approve with Override", key=f"app_{req['review_id']}", type="primary"):
                            if not reviewer_authenticated:
                                st.error("Reviewer authentication is required before approval.")
                            else:
                                decide_and_execute_review(req["review_id"], "APPROVED", reviewer_id)
                                st.success(f"{req['review_id']} APPROVED! Action executed and logged to audit ledger.")
                                st.rerun()
                    with btn_c2:
                        if st.button("❌ Reject & Block", key=f"rej_{req['review_id']}"):
                            if not reviewer_authenticated:
                                st.error("Reviewer authentication is required before rejection.")
                            else:
                                decide_and_execute_review(req["review_id"], "REJECTED", reviewer_id)
                                st.warning(f"{req['review_id']} REJECTED. Execution permanently prevented.")
                                st.rerun()
                elif status == "APPROVED":
                    st.caption("✅ Approved by Human Operator · Tool Executed · Cryptographic Audit Ledger Block Recorded")
                elif status == "REJECTED":
                    st.caption("❌ Rejected by Human Operator · Autonomous Execution Blocked")

# ==============================================================================
# TAB 3: OBSERVED LATENCY
# ==============================================================================
with arena_tab:
    st.markdown('#### Runtime latency measurements')
    st.caption(
        "Measurements below come from this app's current evaluation run. "
        "They are not comparisons with other providers or production guarantees."
    )
    latency_col1, latency_col2, latency_col3 = st.columns(3)
    latency_col1.metric("Retrieval mode(s)", ", ".join(evaluation_modes) or "UNKNOWN")
    latency_col2.metric("Retrieval p50", format_latency(evaluation["retrieval_median_latency_ms"]))
    latency_col3.metric("Guardrail p95", format_latency(evaluation["p95_latency_ms"]))
    st.dataframe(
        pd.DataFrame([
            {"Stage": stage, "Median latency ms": value}
            for stage, value in evaluation["stage_median_latency_ms"].items()
        ]),
        hide_index=True,
        use_container_width=True,
    )
    if evaluation_modes == ["MOSS"]:
        st.success("Every end-to-end evaluation sample retrieved through Moss.")
    else:
        st.info("This run is not Moss-only. Treat its timings as local/demo or mixed-mode results.")

    st.divider()
    # Live Benchmark Runner
    st.markdown("#### 🚀 Run Live Latency Benchmark")
    st.caption("Execute real-time batch checks to measure latency percentiles on this environment.")

    bench_col1, bench_col2 = st.columns([0.4, 0.6])
    with bench_col1:
        iterations = st.select_slider(
            "Benchmark Iterations",
            options=[20, 50, 100, 200],
            value=50,
        )
        run_bench = st.button("Run Live Benchmark", type="primary", use_container_width=True)

    if run_bench:
        with bench_col2:
            with st.spinner(f"Running {iterations} iterations across evaluation cases..."):
                latencies = []
                stage_samples = {}
                benchmark_modes = set()
                for _ in range(iterations):
                    for case in EVALUATION_CASES:
                        t0 = time.perf_counter_ns()
                        benchmark_result = runtime_guard(
                            case["doc_hash"],
                            case["action"],
                            case.get("context_text"),
                            case.get("transaction"),
                        )
                        latencies.append((time.perf_counter_ns() - t0) / 1_000_000)
                        benchmark_modes.add(benchmark_result["retrieval_mode"])
                        for stage, latency in benchmark_result.get("stage_latency_ms", {}).items():
                            stage_samples.setdefault(stage, []).append(latency)

                sorted_lat = sorted(latencies)
                p50 = sorted_lat[int(len(sorted_lat) * 0.50)]
                p90 = sorted_lat[int(len(sorted_lat) * 0.90)]
                p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
                p99 = sorted_lat[int(len(sorted_lat) * 0.99)]

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Median (p50)", format_latency(p50))
                m2.metric("p90 Latency", format_latency(p90))
                m3.metric("p95 Latency", format_latency(p95))
                m4.metric("Samples", len(latencies))

                st.success(
                    f"**Benchmark complete:** {len(latencies)} measured requests · "
                    f"p50 {format_latency(p50)} · p95 {format_latency(p95)} · "
                    f"retrieval mode(s): {', '.join(sorted(benchmark_modes))}. "
                    "These timings describe this run and environment only."
                )
                st.dataframe(pd.DataFrame([
                    {
                        "Stage": stage,
                        "p50 ms": sorted(values)[int((len(values) - 1) * 0.50)],
                        "p95 ms": sorted(values)[int((len(values) - 1) * 0.95)],
                    }
                    for stage, values in sorted(stage_samples.items())
                ]), hide_index=True, use_container_width=True)

                # Small line chart of sample latency distribution
                sample_slice = latencies[:100]
                df_samples = pd.DataFrame({"Latency (ms)": sample_slice})
                st.line_chart(df_samples)

# ==============================================================================
# TAB 4: REPRODUCIBLE EVALUATION
# ==============================================================================
with evaluation_tab:
    st.markdown("#### Reproducible safety evaluation")
    metric_one, metric_two, metric_three, metric_four, metric_five = st.columns(5)
    metric_one.metric("Accuracy", f"{evaluation['accuracy'] * 100:.0f}%")
    metric_two.metric("False allows", str(evaluation["false_allows"]))
    metric_three.metric("Cases", str(evaluation["total_cases"]))
    metric_four.metric("Median latency", format_latency(evaluation["median_latency_ms"]))
    metric_five.metric("p95 latency", format_latency(evaluation["p95_latency_ms"]))
    st.caption(f"Retrieval mode(s) used: {', '.join(evaluation_modes)}")
    if moss_runtime.get("error"):
        st.error(f"Moss diagnostic: {moss_runtime['error']}")
    st.caption(
        f"{evaluation['blocked']} blocked · {evaluation['false_blocks']} false blocks · "
        f"{evaluation['false_allows']} false allows · {evaluation['unexpected_reviews']} unexpected reviews. "
        "A false allow is an unsafe case that was incorrectly allowed."
    )
    st.markdown("#### Median latency by stage (ms)")
    st.dataframe(
        pd.DataFrame([{"Stage": stage, "Median ms": value} for stage, value in evaluation["stage_median_latency_ms"].items()]),
        hide_index=True,
        use_container_width=True,
    )
    for item in evaluation["results"]:
        result = item["result"]
        decision = item["actual"].lower()
        status = "PASS" if item["passed"] else "FAIL"
        st.markdown(
            f'<div class="result-row result-{decision}">'
            f'<strong><span class="status-badge badge-{decision}">{decision.upper()}</span> '
            f'{status} · {item["category"]} · {item["name"]}</strong>'
            f'<p><code>{item["expected"]}</code> expected · '
            f'<code>{item["actual"]}</code> returned · '
            f'guard {format_latency(item["latency_ms"])} · '
            f'retrieval {format_latency(item["retrieval_latency_ms"])}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown("#### Results by category")
    for category, values in evaluation["category_results"].items():
        st.write(
            f"**{category}**: {values['passed']}/{values['total']} passed "
            f"({values['accuracy'] * 100:.0f}%) · {values['false_allows']} false allows · "
            f"{values['false_blocks']} false blocks · {values['unexpected_reviews']} unexpected reviews"
        )
    st.markdown("#### Expected vs returned decisions")
    st.dataframe(pd.DataFrame(evaluation["confusion_matrix"]).T, use_container_width=True)

    st.divider()
    st.markdown("#### Stage 1: retrieval evidence checks")
    ret1, ret2, ret3, ret4 = st.columns(4)
    ret1.metric("Retrieval cases", retrieval_evaluation["total_cases"])
    ret2.metric("Evidence matches", f"{retrieval_evaluation['passed']}/{retrieval_evaluation['total_cases']}")
    ret3.metric("Retrieval p50", format_latency(retrieval_evaluation["median_latency_ms"]))
    ret4.metric("Retrieval p95", format_latency(retrieval_evaluation["p95_latency_ms"]))
    st.caption(f"Provider(s): {', '.join(retrieval_evaluation['retrieval_modes'])}")
    st.dataframe(pd.DataFrame([
        {
            "Result": "PASS" if item["passed"] else "FAIL",
            "Document": item["doc_hash"],
            "Case": item["name"],
            "Checks": ", ".join(f"{key}={'ok' if value else 'mismatch'}" for key, value in item["checks"].items()),
            "Mode": item["retrieval_mode"],
            "Cache hit": item["cache_hit"],
            "Latency ms": item["latency_ms"],
        }
        for item in retrieval_evaluation["results"]
    ]), hide_index=True, use_container_width=True)

    st.markdown("#### Stage 2: policy-only checks")
    pol1, pol2, pol3 = st.columns(3)
    pol1.metric("Policy cases", policy_evaluation["total_cases"])
    pol2.metric("Expected decisions", f"{policy_evaluation['passed']}/{policy_evaluation['total_cases']}")
    pol3.metric("Policy mismatches", policy_evaluation["failed"])
    st.dataframe(pd.DataFrame(policy_evaluation["results"]), hide_index=True, use_container_width=True)

# ==============================================================================
# TAB 5: AUDIT TRAIL
# ==============================================================================
with audit_tab:
    st.markdown("#### Application audit chain")
    st.caption(
        "Each decision is cryptographically linked to the previous entry via SHA-256 for traceability. "
        "This is an application-level hash chain."
    )

    col_v1, col_v2 = st.columns([0.7, 0.3])
    with col_v2:
        if st.button("🔍 Verify Hash-Chain Integrity", use_container_width=True):
            is_valid = verify_audit_chain()
            if is_valid:
                st.success("✅ Audit Chain Valid: All blocks linked and untampered.")
            else:
                st.error("❌ Chain Tampering Detected!")

with sandbox_tab:
    st.markdown("#### Fabricated sandbox payment ledger")
    st.caption("These are local demo records only. No bank, payment processor, or external tool is contacted.")
    sandbox_payments = get_sandbox_payments()
    st.metric("Recorded sandbox payments", len(sandbox_payments))
    if sandbox_payments:
        st.dataframe(pd.DataFrame(sandbox_payments), hide_index=True, use_container_width=True)
    else:
        st.info("No sandbox payment records yet. Run an allowed payment scenario in the Guardrail tab.")

with honeypot_tab:
    st.markdown("#### Read-only decoy record")
    st.caption("This fake record is available only after a suspicious request creates a trace. Opening it records a decoy-access event; it cannot trigger a payment or tool action.")
    decoy_trace = st.text_input(
        "Suspicious request trace ID",
        value=st.session_state.get("latest_honeypot_trace_id", ""),
        key="honeypot_trace_input",
    )
    if st.button("Open fabricated decoy", key="open_honeypot_decoy"):
        try:
            st.session_state["opened_honeypot_decoy"] = read_decoy_record(decoy_trace, "streamlit_read")
            except (ValueError, RuntimeError) as error:
                st.error(str(error))
    if st.session_state.get("opened_honeypot_decoy"):
        st.json(st.session_state["opened_honeypot_decoy"])

with feedback_tab:
    st.markdown("#### Reviewer feedback for policy evaluation")
    st.caption("Labels are saved for later dataset review. Feedback does not automatically alter policy or evaluation outcomes.")
    feedback_audit = get_audit_events()
    if feedback_audit:
        audit_options = {
            f"Block #{item['block_no']} · {item['decision']} · {item['action']} · {item['reason_code']}": item
            for item in reversed(feedback_audit)
        }
        with st.form("decision_feedback_form"):
            selected_audit_label = st.selectbox("Decision to review", list(audit_options))
            feedback_reviewer = st.text_input("Reviewer ID", value="demo-operator", max_chars=120)
            feedback_label = st.selectbox("Was the decision correct?", ["CORRECT", "INCORRECT"])
            feedback_reason = st.text_area("Reason or correction", max_chars=1000)
            submit_feedback = st.form_submit_button("Save feedback")
        if submit_feedback:
            selected_block = audit_options[selected_audit_label]
            saved_feedback = record_decision_feedback(
                selected_block["block_no"], feedback_label, feedback_reviewer, feedback_reason
            )
            st.success(f"Saved {saved_feedback['feedback_id']} for audit block #{saved_feedback['block_no']}.")
            st.rerun()
    else:
        st.info("Run a guardrail request before labeling a decision.")
    saved_feedback_rows = get_decision_feedback()
    if saved_feedback_rows:
        st.dataframe(pd.DataFrame(saved_feedback_rows), hide_index=True, use_container_width=True)

with audit_tab:
    ledger = get_audit_events()
    if ledger:
        for block in reversed(ledger[-8:]):
            decision = block["decision"].lower()
            badge_class = f"badge-{decision if decision in ['allow', 'block', 'review'] else 'allow'}"
            st.markdown(
                f'<div class="result-row result-{decision if decision in ["allow", "block", "review"] else "allow"}">'
                f'<strong><span class="status-badge {badge_class}">{block["decision"]}</span> '
                f'Block #{block["block_no"]}</strong>'
                f'<p><code>{block["timestamp"]}</code> · Hash: <code>{block.get("block_hash", "N/A")}</code> · '
                f'Prev: <code>{block.get("prev_hash", "0000000000000000")}</code> · '
                f'Doc: <code>{block["doc_hash"]}</code> · Action: <code>{block["action"]}</code> · '
                f'Security trace: <code>{block.get("security_trace_id") or "none"}</code> · '
                f'Sandbox record: <code>{block.get("sandbox_record_id") or "none"}</code> · '
                f'Request: <code>{block.get("request_id") or "n/a"}</code></p>'
                f'<p style="font-size: 0.8rem; color: #7f8c8d;">Reason: {block.get("reason_code", "N/A")}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("No decisions have been recorded in this session yet.")

st.divider()
st.caption("AgentGuard · YC Fall 2026 x Moss Builder Sprint · Runtime Guardrails, HITL Review, and application hash-chain audit")
