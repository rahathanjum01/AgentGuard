"""Content-level security checks performed before a tool can execute.

These checks deliberately inspect the untrusted request payload, rather than
relying on demo document identifiers. They are deterministic and explainable
so a reviewer can see exactly why an action was stopped.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation


INJECTION_PATTERNS = (
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"(?:follow|reveal|print|show|ignore|override|replace|repeat)\s+(?:the\s+)?system\s+prompt",
    r"disregard\s+(the\s+)?(policy|rules|guardrail)",
    r"override\s+(the\s+)?(approval|safety|policy)",
    r"do\s+not\s+tell\s+(the\s+)?user",
)


def _amount(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def analyze_request(
    context_text: str | None = None,
    transaction: dict | None = None,
    trusted_evidence: dict | None = None,
) -> list[dict[str, str]]:
    """Return sanitized, explainable findings from untrusted request content."""
    findings: list[dict[str, str]] = []
    text = (context_text or "").lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            findings.append({
                "code": "PROMPT_INJECTION",
                "message": "Untrusted context contains an instruction-override pattern.",
            })
            break

    transaction = transaction or {}
    evidence_available = trusted_evidence is not None
    trusted_evidence = trusted_evidence or {}
    verified_approval = trusted_evidence.get("verified_approval") or {}
    invoice_amount = _amount(
        transaction.get("invoice_amount") or trusted_evidence.get("invoice_amount")
    )
    # When runtime retrieval supplied evidence, its approved amount is
    # authoritative. A request's own `approved_amount` must not verify itself.
    approved_amount = _amount(
        verified_approval.get("approved_amount")
        if evidence_available
        else transaction.get("approved_amount")
    )
    if invoice_amount is not None and approved_amount is not None and invoice_amount != approved_amount:
        findings.append({
            "code": "AMOUNT_MISMATCH",
            "message": "Invoice amount does not match the approved amount.",
        })
    evidence_says_paid = str(verified_approval.get("paid", "")).lower() == "true"
    if transaction.get("is_duplicate") or evidence_says_paid:
        findings.append({
            "code": "DUPLICATE_INVOICE",
            "message": "Transaction is marked as a duplicate or previously paid invoice.",
        })
    evidence_says_expired = str(verified_approval.get("approval_expired", "")).lower() == "true"
    expiry = verified_approval.get("approval_expiry")
    if expiry:
        try:
            evidence_says_expired = evidence_says_expired or date.fromisoformat(str(expiry)) < date.today()
        except ValueError:
            evidence_says_expired = True
    if transaction.get("approval_expired") or evidence_says_expired:
        findings.append({
            "code": "EXPIRED_APPROVAL",
            "message": "The approval attached to this transaction has expired.",
        })

    submitted_bank = transaction.get("bank_account_last4") or trusted_evidence.get("bank_account_last4")
    verified_bank = verified_approval.get("bank_account_last4")
    if submitted_bank and verified_bank and str(submitted_bank) != str(verified_bank):
        findings.append({
            "code": "BANK_ACCOUNT_MISMATCH",
            "message": "Payment bank details do not match the verified vendor record.",
        })

    submitted_vendor = transaction.get("vendor") or trusted_evidence.get("vendor")
    verified_vendor = verified_approval.get("vendor")
    if submitted_vendor and verified_vendor and str(submitted_vendor).casefold() != str(verified_vendor).casefold():
        findings.append({
            "code": "VENDOR_MISMATCH",
            "message": "Invoice vendor does not match the verified approval record.",
        })
    return findings


def validate_retrieved_context(action: str, doc_hash: str, evidence: dict) -> list[dict[str, str]]:
    """Validate identity, freshness, and linked approval evidence on each request."""
    findings: list[dict[str, str]] = []
    evidence = evidence or {}
    retrieved_hash = str(evidence.get("doc_hash", "")).strip()
    if retrieved_hash and retrieved_hash != doc_hash:
        findings.append({
            "code": "DOCUMENT_ID_MISMATCH",
            "message": "Retrieved document identity does not match the requested document.",
        })

    allowed_action = str(evidence.get("allowed_action", "")).strip().lower()
    if action != "read_email" and allowed_action != action.lower():
        findings.append({
            "code": "UNAUTHORIZED_ACTION",
            "message": "Retrieved context does not authorize the requested tool action.",
        })

    valid_until = evidence.get("valid_until")
    if valid_until:
        try:
            if date.fromisoformat(str(valid_until)) < date.today():
                findings.append({
                    "code": "STALE_CONTEXT",
                    "message": "Retrieved document is past its validity date.",
                })
        except ValueError:
            findings.append({
                "code": "INVALID_FRESHNESS_METADATA",
                "message": "Retrieved document has an invalid validity date.",
            })

    if action == "payment":
        invoice_id = str(evidence.get("invoice_id", "")).strip()
        approval = evidence.get("verified_approval")
        if not invoice_id or not approval:
            findings.append({
                "code": "APPROVAL_RECORD_NOT_FOUND",
                "message": "Payment requires a matching independently retrieved approval record.",
            })
    return findings


def security_block_result(result: dict, findings: list[dict[str, str]]) -> dict:
    """Convert a normal policy result into a fail-closed content-security block."""
    if not findings:
        return result
    primary = findings[0]
    return {
        **result,
        "allow": False,
        "decision": "BLOCK",
        "action": "BLOCKED",
        "alert": "CONTENT SECURITY CHECK FAILED",
        "reason": primary["message"],
        "reason_code": primary["code"],
        "color": "red",
        "security_findings": findings,
    }
