"""
M6: Contracts and Data Structures
=================================
Typed dataclasses, constants, and validation schemas for the Bounded LLM
and Communication Layer.

M6 sits strictly downstream of M4. It does not select or mutate decisions.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Authoritative Constants
# ---------------------------------------------------------------------------

VALID_CUSTOMER_SEGMENTS: Set[str] = {
    "b2c_new",
    "b2c_returning",
    "b2b",
}

VALID_CHANNELS: Set[str] = {
    "email",
    "sms",
    "whatsapp",
    "none",
}

ACTIVE_RECOVERY_ACTIONS: Set[str] = {
    "retry",
    "payment_link",
    "reminder",
    "discount",
}

INACTIVE_ACTIONS: Set[str] = {
    "wait",
    "close",
    "escalate",
    "no_action_required",
}

ALL_RECOGNIZED_ACTIONS: Set[str] = ACTIVE_RECOVERY_ACTIONS | INACTIVE_ACTIONS

GENERATION_MODES: Set[str] = {
    "deterministic_template",
    "generator_verified",
    "fallback_due_to_guardrail",
    "non_sendable_fallback",
}


# ---------------------------------------------------------------------------
# Approved Customer Context Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApprovedCustomerContext:
    """
    Explicitly approved context supplied from external customer/transaction stores.
    M4 does not provide customer context; M6 must validate this context strictly.
    """
    transaction_id: str
    amount: Optional[float] = None
    currency: str = "INR"
    customer_segment: Optional[str] = None
    channel: Optional[str] = None
    failure_type: Optional[str] = None
    urgency: Optional[str] = None
    recovery_window_hours_remaining: Optional[float] = None
    approved_discount_percent: Optional[float] = None
    approved_payment_link: Optional[str] = None
    customer_display_name: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ApprovedCustomerContext":
        if not data or not isinstance(data, dict):
            return cls(transaction_id="unknown")
        
        # Safe float conversions
        amount = data.get("amount")
        if amount is not None:
            try:
                amount = float(amount)
            except (ValueError, TypeError):
                amount = None

        disc = data.get("approved_discount_percent")
        if disc is not None:
            try:
                disc = float(disc)
            except (ValueError, TypeError):
                disc = None

        hours = data.get("recovery_window_hours_remaining")
        if hours is not None:
            try:
                hours = float(hours)
            except (ValueError, TypeError):
                hours = None

        return cls(
            transaction_id=str(data.get("transaction_id", "unknown")),
            amount=amount,
            currency=str(data.get("currency", "INR")),
            customer_segment=data.get("customer_segment"),
            channel=data.get("channel"),
            failure_type=data.get("failure_type"),
            urgency=data.get("urgency"),
            recovery_window_hours_remaining=hours,
            approved_discount_percent=disc,
            approved_payment_link=data.get("approved_payment_link"),
            customer_display_name=data.get("customer_display_name"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Guardrail Results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GuardrailCheckResult:
    """Individual rule verification outcome."""
    check_name: str
    passed: bool
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GuardrailStatus:
    """Overall status of guardrail execution."""
    passed: bool
    checks: List[GuardrailCheckResult] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "violations": list(self.violations),
        }


# ---------------------------------------------------------------------------
# Customer Communication Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CustomerCommunication:
    """
    Structured customer-facing communication output.
    Contains customer-safe text only (zero internal metadata/probabilities/EV).
    """
    transaction_id: str
    decision: str
    sendable: bool
    channel: str
    subject: Optional[str]
    body: str
    customer_display_name: Optional[str]
    generation_mode: str
    guardrail_status: Dict[str, Any]
    fallback_used: bool
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Decision Explanation Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DecisionExplanation:
    """
    Internal-facing explanation for merchants, operators, and compliance auditors.
    Transparently details M4 decision, M3 policy restrictions, and EV rationale.
    """
    transaction_id: str
    decision: str
    decision_type: str
    decision_reason: str
    escalation_required: bool
    terminal: bool
    selected_probability: Optional[float]
    selected_ev: Optional[float]
    summary_explanation: str
    policy_rationale: str
    economic_rationale: str
    allowed_actions: List[str]
    blocked_actions: Dict[str, Any]
    model_version: str
    policy_version: str
    decision_engine_version: str
    disclaimer: str = (
        "Internal audit explanation generated by M6 based on authoritative M4 "
        "decision output. M6 did not select or alter this action."
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
