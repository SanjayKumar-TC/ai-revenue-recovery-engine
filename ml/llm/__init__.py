"""
M6: Bounded LLM & Communication Layer
======================================
Downstream communication generation and internal decision explanation subsystem.
"""

from ml.llm.contracts import (
    ACTIVE_RECOVERY_ACTIONS,
    ALL_RECOGNIZED_ACTIONS,
    INACTIVE_ACTIONS,
    VALID_CHANNELS,
    VALID_CUSTOMER_SEGMENTS,
    ApprovedCustomerContext,
    CustomerCommunication,
    DecisionExplanation,
    GuardrailCheckResult,
    GuardrailStatus,
)
from ml.llm.guardrails import (
    run_communication_guardrails,
    validate_approved_context,
    validate_decision_output,
)
from ml.llm.communication import (
    compose_customer_communication,
    explain_decision,
)

__all__ = [
    "ACTIVE_RECOVERY_ACTIONS",
    "ALL_RECOGNIZED_ACTIONS",
    "INACTIVE_ACTIONS",
    "VALID_CHANNELS",
    "VALID_CUSTOMER_SEGMENTS",
    "ApprovedCustomerContext",
    "CustomerCommunication",
    "DecisionExplanation",
    "GuardrailCheckResult",
    "GuardrailStatus",
    "validate_decision_output",
    "validate_approved_context",
    "run_communication_guardrails",
    "compose_customer_communication",
    "explain_decision",
]
