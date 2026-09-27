import unittest

from src.gateway import GuardResponse, HealthResponse, ToolRequest
from src.retrieval import (
    MossIntegrationError,
    MossNotConfigured,
    RetrievalResult,
    local_demo_search,
    moss_error_result,
    retrieve_context,
)
from src.policy import (
    EVALUATION_CASES,
    PolicyDecision,
    evaluate_batch,
    evaluate_policy,
    normalize_context,
    runtime_guard,
)
from src.execution_review import (
    ExecutionResult,
    create_pending_review,
    decide_review,
    execute_tool,
    get_review,
    list_reviews,
)
from src.audit_security import (
    LEDGER,
    add_to_ledger,
    analyze_request,
    get_audit_events,
    honeypot_trap,
    record_audit_event,
    security_trace,
    verify_audit_chain,
    verify_ledger,
)
import src


class ArchitectureLayersTests(unittest.TestCase):
    """Test that all 5 architectural layers and top-level facade export properly."""

    def test_layer_1_gateway_exports(self):
        self.assertTrue(issubclass(ToolRequest, object))
        self.assertTrue(issubclass(GuardResponse, object))
        self.assertTrue(issubclass(HealthResponse, object))

    def test_layer_2_retrieval_exports(self):
        res = local_demo_search("a1b2c3d4e5f6g7h8")
        self.assertTrue(res["found"])
        self.assertEqual(res["retrieval_mode"], "LOCAL_DEMO")
        self.assertEqual(res["vendor"], "HAL")

    def test_layer_3_policy_exports(self):
        context = RetrievalResult(
            found=True,
            trust=0.95,
            latency=0.5,
            doc="Invoice INV100",
            status="VERIFIED",
            vendor="HAL",
            retrieval_mode="LOCAL_DEMO",
        )
        decision = evaluate_policy("payment", context)
        self.assertEqual(decision.decision, "ALLOW")
        self.assertTrue(decision.allow)

    def test_layer_4_execution_review_exports(self):
        res = execute_tool("read_email", "REQ-001", {"decision": "ALLOW"})
        self.assertTrue(res.executed)
        self.assertEqual(res.status, "EXECUTED")

    def test_layer_5_audit_security_exports(self):
        trace = security_trace("hacker_inject_999", is_blocked=True)
        self.assertTrue(trace["activated"])
        self.assertIn("TRACE-", trace["trace_id"])

    def test_top_level_facade_exports(self):
        self.assertTrue(callable(src.guarded_tool_call))
        self.assertTrue(callable(src.runtime_guard))
        self.assertTrue(callable(src.evaluate_policy))
        self.assertTrue(callable(src.retrieve_context))
        self.assertTrue(callable(src.record_audit_event))
        self.assertTrue(hasattr(src, "gateway"))
        self.assertTrue(hasattr(src, "retrieval"))
        self.assertTrue(hasattr(src, "policy"))
        self.assertTrue(hasattr(src, "execution_review"))
        self.assertTrue(hasattr(src, "audit_security"))


if __name__ == "__main__":
    unittest.main()
