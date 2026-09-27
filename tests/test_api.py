import unittest

from fastapi.testclient import TestClient

from api import app
from src.blockchain import LEDGER
from src.review import REVIEW_QUEUE


class ApiGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        LEDGER.clear()
        REVIEW_QUEUE.clear()

    def test_health_check(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_allowed_request_executes(self):
        response = self.client.post(
            "/v1/guard/tool-request",
            json={
                "action": "payment",
                "doc_hash": "a1b2c3d4e5f6g7h8",
            },
        )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["decision"], "ALLOW")
        self.assertTrue(body["executed"])
        self.assertEqual(body["execution"]["status"], "EXECUTED")
        self.assertEqual(body["policy_name"], "agentguard-default")
        self.assertEqual(body["policy_version"], "agentguard-default-v1")
        self.assertEqual(body["reason_code"], "CONTEXT_ACCEPTED")
        self.assertEqual(body["retrieval"]["retrieval_mode"], "LOCAL_DEMO")
        self.assertEqual(body["retrieval"]["trust"], 0.95)
        self.assertEqual(body["audit"]["decision"], "ALLOW")

    def test_blocked_request_does_not_execute(self):
        response = self.client.post(
            "/v1/guard/tool-request",
            json={
                "action": "payment",
                "doc_hash": "hacker_inject_999",
            },
        )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["decision"], "BLOCK")
        self.assertFalse(body["executed"])
        self.assertEqual(body["execution"]["status"], "PREVENTED")
        self.assertTrue(body["honeypot"]["activated"])
        self.assertEqual(body["reason_code"], "INVALID_CONTEXT_STATUS")
        self.assertEqual(body["audit"]["decision"], "BLOCK")

    def test_review_request_does_not_execute(self):
        response = self.client.post(
            "/v1/guard/tool-request",
            json={
                "action": "read_email",
                "doc_hash": "d4e5f6g7h8i9j0k1",
            },
        )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["decision"], "REVIEW")
        self.assertFalse(body["executed"])
        self.assertEqual(body["execution"]["status"], "PREVENTED")
        self.assertEqual(body["reason_code"], "REVIEW_REQUIRED")
        self.assertFalse(body["honeypot"]["activated"])
        self.assertEqual(body["review_request"]["status"], "PENDING")

    def test_audit_and_review_read_models(self):
        self.client.post(
            "/v1/guard/tool-request",
            json={"action": "read_email", "doc_hash": "d4e5f6g7h8i9j0k1"},
        )

        reviews = self.client.get("/v1/reviews")
        audit = self.client.get("/v1/audit")
        verification = self.client.get("/v1/audit/verify")

        self.assertEqual(reviews.status_code, 200)
        self.assertEqual(len(reviews.json()["reviews"]), 1)
        self.assertEqual(len(audit.json()["events"]), 1)
        self.assertTrue(verification.json()["valid"])

    def test_review_decision_does_not_execute_tool(self):
        response = self.client.post(
            "/v1/guard/tool-request",
            json={"action": "read_email", "doc_hash": "d4e5f6g7h8i9j0k1"},
        )
        review_id = response.json()["review_request"]["review_id"]

        decision = self.client.post(
            f"/v1/reviews/{review_id}/decision",
            json={"decision": "APPROVED"},
        )

        self.assertTrue(decision.json()["updated"])
        self.assertEqual(decision.json()["review"]["status"], "APPROVED")
        self.assertFalse(decision.json()["execution_started"])

    def test_invalid_request_returns_422(self):
        response = self.client.post(
            "/v1/guard/tool-request",
            json={"action": "unknown", "doc_hash": "x"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(LEDGER), 0)


if __name__ == "__main__":
    unittest.main()
