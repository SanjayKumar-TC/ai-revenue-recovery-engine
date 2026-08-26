"""
M6: Test Suite for Bounded Communication & Explanation Engine
=============================================================
Comprehensive standalone test suite verifying:
  - M4 decision validation and immutability
  - Active vs inactive recovery action rules
  - Hard programmatic guardrails against financial, URL, identity, and data leakage
  - Deterministic parameterized fallback templates
  - Optional generator integration with fail-closed guardrail protection
  - Internal transparent decision explanations
  - Real M4 make_decision() integration

Runnable standalone:
    python -m ml.llm.test_communication
"""

import copy
import sys
from typing import Any, Dict

from ml.llm.contracts import (
    ApprovedCustomerContext,
    CustomerCommunication,
    DecisionExplanation,
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

# ---------------------------------------------------------------------------
# Test Reporting Infrastructure
# ---------------------------------------------------------------------------

PASS_COUNT = 0
FAIL_COUNT = 0


def _report(test_num: int, name: str, passed: bool, details: str = "") -> bool:
    global PASS_COUNT, FAIL_COUNT
    status = "PASS" if passed else "FAIL"
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1

    print(f"\n[Test {test_num:02d}] {name}: {status}")
    if details:
        for line in details.strip().split("\n"):
            print(f"  {line}")
    return passed


# ---------------------------------------------------------------------------
# Standard Mock Fixtures
# ---------------------------------------------------------------------------

def _mock_m4_decision(
    action: str = "retry",
    decision_type: str = "ev_optimization",
    decision_reason: str = "highest_expected_net_value",
    escalation_required: bool = False,
    terminal: bool = False,
    prob: Any = 0.45,
    ev: Any = 450.0,
    blocked: Any = None,
) -> Dict[str, Any]:
    """Generate a valid synthetic M4 make_decision() output dictionary."""
    if blocked is not None:
        blocked_actions = blocked
    else:
        # Default blocked actions should not conflict with the chosen action
        if action == "discount":
            blocked_actions = {"payment_link": ["customer_opted_out"]}
        elif action == "retry":
            blocked_actions = {"discount": ["max_discount_cap_exceeded"]}
        elif action == "payment_link":
            blocked_actions = {"retry": ["max_retries_exceeded"]}
        elif action == "reminder":
            blocked_actions = {"discount": ["max_discount_cap_exceeded"]}
        else:
            blocked_actions = {"retry": ["max_retries_exceeded"], "discount": ["max_discount_cap_exceeded"]}

    # Real M4 contract: when prob/ev are None or decision is escalation/terminal/fallback, action_analysis is empty
    if prob is not None and ev is not None:
        action_analysis = {
            action: {
                "action": action,
                "predicted_probability": float(prob),
                "recoverable_amount": 1000.0,
                "gross_expected_recovery": float(prob) * 1000.0,
                "intervention_cost": 2.0 if action == "retry" else (5.0 if action == "payment_link" else 0.0),
                "discount_amount": 0.0,
                "expected_net_value": float(ev),
            },
            "wait": {
                "action": "wait",
                "predicted_probability": 0.10,
                "recoverable_amount": 1000.0,
                "gross_expected_recovery": 100.0,
                "intervention_cost": 0.0,
                "discount_amount": 0.0,
                "expected_net_value": 100.0,
            } if action != "wait" else {
                "action": "wait",
                "predicted_probability": float(prob),
                "recoverable_amount": 1000.0,
                "gross_expected_recovery": float(prob) * 1000.0,
                "intervention_cost": 0.0,
                "discount_amount": 0.0,
                "expected_net_value": float(ev),
            }
        }
    else:
        action_analysis = {}

    return {
        "transaction_id": "TXN_M6_001",
        "policy_version": "1.0.0",
        "decision": action,
        "decision_type": decision_type,
        "decision_reason": decision_reason,
        "escalation_required": escalation_required,
        "terminal": terminal,
        "selected_probability": prob,
        "selected_ev": ev,
        "action_analysis": action_analysis,
        "allowed_actions": [action] if prob is None else [action, "wait"],
        "blocked_actions": blocked_actions,
        "model_version": "M2_logistic_regression" if prob is not None else "N/A",
        "decision_engine_version": "1.0.0",
        "evaluated_at": "2026-08-26T12:00:00Z",
    }


def _mock_approved_context(
    action: str = "retry",
    amount: float = 1000.0,
    discount_pct: float = 10.0,
    payment_link: str = "https://checkout.example.com/pay/TXN_M6_001",
    channel: str = "email",
    segment: str = "b2c_returning",
    name: str = "Ananya Sharma",
) -> Dict[str, Any]:
    """Generate valid approved customer context dictionary."""
    return {
        "transaction_id": "TXN_M6_001",
        "amount": amount,
        "currency": "INR",
        "customer_segment": segment,
        "channel": channel,
        "failure_type": "temporary_bank_decline",
        "urgency": "medium",
        "recovery_window_hours_remaining": 24.0,
        "approved_discount_percent": discount_pct if action == "discount" else None,
        "approved_payment_link": payment_link if action == "payment_link" else None,
        "customer_display_name": name,
    }


# ===========================================================================
# 1. M4 Decision Validation & Immutability Tests (Tests 1 - 3)
# ===========================================================================

def test_1_valid_m4_decision_validation():
    """Verify valid M4 decision dictionary is recognized and validated."""
    dec = _mock_m4_decision()
    val = validate_decision_output(dec)
    passed = val["is_valid"] and len(val["errors"]) == 0 and val["sanitized_decision"] is not None
    return _report(1, "VALID M4 DECISION VALIDATION", passed, f"is_valid={val['is_valid']}")


def test_2_malformed_m4_decision_rejection():
    """Verify missing required keys or invalid actions are rejected."""
    # Missing required 'decision' key
    dec_bad = {"transaction_id": "TXN_BAD"}
    val = validate_decision_output(dec_bad)
    passed1 = not val["is_valid"] and len(val["errors"]) > 0

    # Invalid action
    dec_invalid_act = _mock_m4_decision(action="unauthorized_action")
    val2 = validate_decision_output(dec_invalid_act)
    passed2 = not val2["is_valid"]

    passed = passed1 and passed2
    return _report(2, "MALFORMED M4 DECISION REJECTION", passed, f"errors={val['errors']}")


def test_3_m4_decision_immutability():
    """Verify compose_customer_communication and explain_decision never mutate input dict."""
    dec = _mock_m4_decision()
    dec_original = copy.deepcopy(dec)
    ctx = _mock_approved_context()
    ctx_original = copy.deepcopy(ctx)

    _ = compose_customer_communication(dec, ctx)
    _ = explain_decision(dec)

    dec_unmodified = (dec == dec_original)
    ctx_unmodified = (ctx == ctx_original)
    passed = dec_unmodified and ctx_unmodified
    return _report(3, "M4 DECISION IMMUTABILITY", passed, f"dec_unmodified={dec_unmodified}, ctx_unmodified={ctx_unmodified}")


# ===========================================================================
# 2. Customer Communication per Action (Tests 4 - 11)
# ===========================================================================

def test_4_retry_communication():
    """Verify retry action generates sendable communication without payment links or discounts."""
    dec = _mock_m4_decision(action="retry")
    ctx = _mock_approved_context(action="retry", amount=2500.0)
    comm = compose_customer_communication(dec, ctx)

    passed = (
        comm["sendable"] is True
        and comm["decision"] == "retry"
        and "2,500.00" in comm["body"]
        and "http" not in comm["body"]
        and "discount" not in comm["body"].lower()
        and comm["generation_mode"] == "deterministic_template"
    )
    return _report(4, "RETRY COMMUNICATION", passed, f"sendable={comm['sendable']}, mode={comm['generation_mode']}")


def test_5_payment_link_communication():
    """Verify payment_link communication includes approved URL and is sendable."""
    dec = _mock_m4_decision(action="payment_link")
    ctx = _mock_approved_context(action="payment_link", amount=1500.0, payment_link="https://checkout.example.com/pay/123")
    comm = compose_customer_communication(dec, ctx)

    passed = (
        comm["sendable"] is True
        and comm["decision"] == "payment_link"
        and "https://checkout.example.com/pay/123" in comm["body"]
        and "1,500.00" in comm["body"]
        and comm["generation_mode"] == "deterministic_template"
    )
    return _report(5, "PAYMENT_LINK COMMUNICATION", passed, f"sendable={comm['sendable']}, has_link={'checkout.example.com' in comm['body']}")


def test_6_reminder_communication():
    """Verify reminder communication is gentle and does not claim auto-retry or discount."""
    dec = _mock_m4_decision(action="reminder")
    ctx = _mock_approved_context(action="reminder", amount=3000.0)
    comm = compose_customer_communication(dec, ctx)

    passed = (
        comm["sendable"] is True
        and comm["decision"] == "reminder"
        and "3,000.00" in comm["body"]
        and "discount" not in comm["body"].lower()
        and "automatically retrying" not in comm["body"].lower()
    )
    return _report(6, "REMINDER COMMUNICATION", passed, f"sendable={comm['sendable']}, body_snippet={comm['body'][:60]}...")


def test_7_discount_communication():
    """Verify discount communication preserves exact approved percentage and discounted amount."""
    dec = _mock_m4_decision(action="discount")
    ctx = _mock_approved_context(action="discount", amount=1000.0, discount_pct=15.0)
    comm = compose_customer_communication(dec, ctx)

    passed = (
        comm["sendable"] is True
        and comm["decision"] == "discount"
        and "15%" in comm["body"]
        and "850.00" in comm["body"] # 1000 - 15% = 850
        and comm["generation_mode"] == "deterministic_template"
    )
    return _report(7, "DISCOUNT COMMUNICATION", passed, f"sendable={comm['sendable']}, has_15pct={'15%' in comm['body']}")


def test_8_wait_non_sendable():
    """Verify wait action produces sendable=False non-recovery notice."""
    dec = _mock_m4_decision(action="wait")
    ctx = _mock_approved_context(action="wait")
    comm = compose_customer_communication(dec, ctx)

    passed = (
        comm["sendable"] is False
        and comm["decision"] == "wait"
        and comm["generation_mode"] == "non_sendable_fallback"
        and "pay now" not in comm["body"].lower()
    )
    return _report(8, "WAIT NON-SENDABLE", passed, f"sendable={comm['sendable']}, mode={comm['generation_mode']}")


def test_9_close_non_sendable():
    """Verify close action produces sendable=False terminal notice."""
    dec = _mock_m4_decision(action="close", terminal=True)
    ctx = _mock_approved_context(action="close")
    comm = compose_customer_communication(dec, ctx)

    passed = (
        comm["sendable"] is False
        and comm["decision"] == "close"
        and comm["generation_mode"] == "non_sendable_fallback"
    )
    return _report(9, "CLOSE NON-SENDABLE", passed, f"sendable={comm['sendable']}")


def test_10_escalate_non_sendable():
    """Verify escalate action produces sendable=False human-routing notice."""
    dec = _mock_m4_decision(action="escalate", escalation_required=True)
    ctx = _mock_approved_context(action="escalate")
    comm = compose_customer_communication(dec, ctx)

    passed = (
        comm["sendable"] is False
        and comm["decision"] == "escalate"
        and comm["generation_mode"] == "non_sendable_fallback"
    )
    return _report(10, "ESCALATE NON-SENDABLE", passed, f"sendable={comm['sendable']}")


def test_11_no_action_required_non_sendable():
    """Verify no_action_required produces sendable=False notice."""
    dec = _mock_m4_decision(action="no_action_required", terminal=True)
    ctx = _mock_approved_context(action="no_action_required")
    comm = compose_customer_communication(dec, ctx)

    passed = (
        comm["sendable"] is False
        and comm["decision"] == "no_action_required"
        and comm["generation_mode"] == "non_sendable_fallback"
    )
    return _report(11, "NO_ACTION_REQUIRED NON-SENDABLE", passed, f"sendable={comm['sendable']}")


# ===========================================================================
# 3. Guardrails & Rejection Tests (Tests 12 - 21)
# ===========================================================================

def test_12_unauthorized_amount_rejection():
    """Verify generator attempting an unauthorized amount triggers fallback."""
    dec = _mock_m4_decision(action="retry")
    ctx = _mock_approved_context(action="retry", amount=1000.0)

    # Malicious/hallucinating generator tries to state ₹9999
    bad_generator = lambda d, c: f"Hello, we will retry your payment of ₹9,999.00 shortly."
    comm = compose_customer_communication(dec, ctx, generator=bad_generator)

    passed = (
        comm["fallback_used"] is True
        and comm["generation_mode"] == "fallback_due_to_guardrail"
        and "9,999" not in comm["body"]
        and "1,000.00" in comm["body"]
    )
    return _report(12, "UNAUTHORIZED AMOUNT REJECTION", passed, f"fallback_used={comm['fallback_used']}, mode={comm['generation_mode']}")


def test_13_unauthorized_discount_rejection():
    """Verify generator mentioning discount on a retry action triggers fallback."""
    dec = _mock_m4_decision(action="retry")
    ctx = _mock_approved_context(action="retry", amount=1000.0)

    bad_generator = lambda d, c: f"We applied a 10% discount to your payment of ₹1,000.00."
    comm = compose_customer_communication(dec, ctx, generator=bad_generator)

    passed = (
        comm["fallback_used"] is True
        and comm["generation_mode"] == "fallback_due_to_guardrail"
        and "discount" not in comm["body"].lower()
    )
    return _report(13, "UNAUTHORIZED DISCOUNT REJECTION", passed, f"fallback_used={comm['fallback_used']}")


def test_14_excessive_invalid_discount_rejection():
    """Verify generator offering 50% when 10% was approved triggers fallback."""
    dec = _mock_m4_decision(action="discount")
    ctx = _mock_approved_context(action="discount", amount=1000.0, discount_pct=10.0)

    # Hallucinating generator claims 50% discount
    bad_generator = lambda d, c: f"Dear Customer, you got a massive 50% discount! Pay ₹500."
    comm = compose_customer_communication(dec, ctx, generator=bad_generator)

    passed = (
        comm["fallback_used"] is True
        and comm["generation_mode"] == "fallback_due_to_guardrail"
        and "50%" not in comm["body"]
        and "10%" in comm["body"]
    )
    return _report(14, "EXCESSIVE/INVALID DISCOUNT REJECTION", passed, f"fallback_used={comm['fallback_used']}")


def test_15_blocked_action_rejection():
    """Verify generator proposing an action in blocked_actions triggers fallback."""
    dec = _mock_m4_decision(action="reminder", blocked={"retry": ["max_retries_exceeded"]})
    ctx = _mock_approved_context(action="reminder", amount=1000.0)

    # Generator proposes blocked retry
    bad_generator = lambda d, c: f"Dear Customer, we will automatically retry your payment of ₹1,000.00."
    comm = compose_customer_communication(dec, ctx, generator=bad_generator)

    passed = (
        comm["fallback_used"] is True
        and comm["generation_mode"] == "fallback_due_to_guardrail"
    )
    return _report(15, "BLOCKED-ACTION REJECTION", passed, f"fallback_used={comm['fallback_used']}")


def test_16_alternate_action_recommendation_rejection():
    """Verify generator recommending payment link when decision is retry triggers fallback."""
    dec = _mock_m4_decision(action="retry")
    ctx = _mock_approved_context(action="retry", amount=1000.0)

    bad_generator = lambda d, c: f"Dear Customer, please pay using the link below: https://example.com"
    comm = compose_customer_communication(dec, ctx, generator=bad_generator)

    passed = (
        comm["fallback_used"] is True
        and comm["generation_mode"] == "fallback_due_to_guardrail"
        and "link" not in comm["body"].lower()
    )
    return _report(16, "ALTERNATE-ACTION RECOMMENDATION REJECTION", passed, f"fallback_used={comm['fallback_used']}")


def test_17_invented_url_rejection():
    """Verify generator introducing unapproved URLs is rejected."""
    dec = _mock_m4_decision(action="payment_link")
    ctx = _mock_approved_context(action="payment_link", amount=1000.0, payment_link="https://approved.pay.com/123")

    # Generator puts a phishing/hallucinated URL
    bad_generator = lambda d, c: f"Pay ₹1,000.00 at https://fake-scam-url.com/pay"
    comm = compose_customer_communication(dec, ctx, generator=bad_generator)

    passed = (
        comm["fallback_used"] is True
        and comm["generation_mode"] == "fallback_due_to_guardrail"
        and "https://fake-scam-url.com/pay" not in comm["body"]
        and "https://approved.pay.com/123" in comm["body"]
    )
    return _report(17, "INVENTED URL REJECTION", passed, f"fallback_used={comm['fallback_used']}")


def test_18_invented_identity_rejection():
    """Verify generator hallucinating a customer name when none was provided triggers fallback."""
    dec = _mock_m4_decision(action="retry")
    ctx = _mock_approved_context(action="retry", amount=1000.0, name=None) # No name provided

    # Generator invents "Dear Rajesh Kumar,"
    bad_generator = lambda d, c: f"Dear Rajesh Kumar,\nWe are retrying your payment of ₹1,000.00."
    comm = compose_customer_communication(dec, ctx, generator=bad_generator)

    passed = (
        comm["fallback_used"] is True
        and comm["generation_mode"] == "fallback_due_to_guardrail"
        and "Rajesh Kumar" not in comm["body"]
    )
    return _report(18, "INVENTED IDENTITY REJECTION", passed, f"fallback_used={comm['fallback_used']}")


def test_19_internal_metadata_leakage_rejection():
    """Verify generator containing internal engine metadata tokens is rejected."""
    dec = _mock_m4_decision(action="retry")
    ctx = _mock_approved_context(action="retry", amount=1000.0)

    bad_generator = lambda d, c: f"M2_logistic_regression and ev_optimization selected retry for ₹1,000.00."
    comm = compose_customer_communication(dec, ctx, generator=bad_generator)

    passed = (
        comm["fallback_used"] is True
        and "M2_logistic_regression" not in comm["body"]
    )
    return _report(19, "INTERNAL METADATA LEAKAGE REJECTION", passed, f"fallback_used={comm['fallback_used']}")


def test_20_probability_leakage_rejection():
    """Verify generator quoting recovery probability is rejected."""
    dec = _mock_m4_decision(action="retry")
    ctx = _mock_approved_context(action="retry", amount=1000.0)

    bad_generator = lambda d, c: f"Your transaction of ₹1,000.00 has a recovery probability of 45%."
    comm = compose_customer_communication(dec, ctx, generator=bad_generator)

    passed = (
        comm["fallback_used"] is True
        and "recovery probability" not in comm["body"].lower()
    )
    return _report(20, "PROBABILITY LEAKAGE REJECTION", passed, f"fallback_used={comm['fallback_used']}")


def test_21_ev_leakage_rejection():
    """Verify generator quoting EV numbers or terms is rejected."""
    dec = _mock_m4_decision(action="retry")
    ctx = _mock_approved_context(action="retry", amount=1000.0)

    bad_generator = lambda d, c: f"We selected retry for ₹1,000.00 with expected net value = ₹450."
    comm = compose_customer_communication(dec, ctx, generator=bad_generator)

    passed = (
        comm["fallback_used"] is True
        and "expected net value" not in comm["body"].lower()
    )
    return _report(21, "EV LEAKAGE REJECTION", passed, f"fallback_used={comm['fallback_used']}")


# ===========================================================================
# 4. Context Validation & Edge Cases (Tests 22 - 27)
# ===========================================================================

def test_22_missing_approved_context():
    """Verify missing required context fields causes fail-closed non-sendable output."""
    dec = _mock_m4_decision(action="payment_link")
    ctx_no_link = _mock_approved_context(action="payment_link", payment_link=None)
    comm = compose_customer_communication(dec, ctx_no_link)

    passed = (
        comm["sendable"] is False
        and comm["generation_mode"] == "non_sendable_fallback"
    )
    return _report(22, "MISSING APPROVED CONTEXT (PAYMENT_LINK WITHOUT URL)", passed, f"sendable={comm['sendable']}")


def test_23_invalid_channel():
    """Verify invalid channel is rejected by approved context validator."""
    dec = _mock_m4_decision(action="retry")
    ctx_bad_channel = _mock_approved_context(channel="unsupported_telegram_channel")
    comm = compose_customer_communication(dec, ctx_bad_channel)

    passed = (
        comm["sendable"] is False
        and comm["generation_mode"] == "non_sendable_fallback"
    )
    return _report(23, "INVALID CHANNEL REJECTION", passed, f"sendable={comm['sendable']}")


def test_24_invalid_segment():
    """Verify invalid customer segment is rejected by context validator."""
    dec = _mock_m4_decision(action="retry")
    ctx_bad_seg = _mock_approved_context(segment="vip_platinum_custom_tier")
    comm = compose_customer_communication(dec, ctx_bad_seg)

    passed = (
        comm["sendable"] is False
        and comm["generation_mode"] == "non_sendable_fallback"
    )
    return _report(24, "INVALID CUSTOMER SEGMENT REJECTION", passed, f"sendable={comm['sendable']}")


def test_25_optional_generator_success():
    """Verify valid safe custom generator passes guardrails and marks generator_verified."""
    dec = _mock_m4_decision(action="retry")
    ctx = _mock_approved_context(action="retry", amount=1000.0, name="Ananya")

    good_generator = lambda d, c: {
        "subject": "Payment Status Notice",
        "body": "Dear Ananya,\nWe are automatically re-attempting your payment of ₹1,000.00. No action required.",
    }
    comm = compose_customer_communication(dec, ctx, generator=good_generator)

    passed = (
        comm["sendable"] is True
        and comm["fallback_used"] is False
        and comm["generation_mode"] == "generator_verified"
        and "Ananya" in comm["body"]
        and "1,000.00" in comm["body"]
    )
    return _report(25, "OPTIONAL GENERATOR SUCCESS", passed, f"mode={comm['generation_mode']}, fallback_used={comm['fallback_used']}")


def test_26_generator_guardrail_failure_fallback():
    """Verify generator failing guardrails falls back safely to deterministic template."""
    dec = _mock_m4_decision(action="payment_link")
    ctx = _mock_approved_context(action="payment_link", amount=1000.0, payment_link="https://pay.example.com/123")

    # Generator throws unapproved amount
    bad_generator = lambda d, c: "Click to pay ₹500 at https://pay.example.com/123"
    comm = compose_customer_communication(dec, ctx, generator=bad_generator)

    passed = (
        comm["sendable"] is True
        and comm["fallback_used"] is True
        and comm["generation_mode"] == "fallback_due_to_guardrail"
        and "1,000.00" in comm["body"]
        and "https://pay.example.com/123" in comm["body"]
    )
    return _report(26, "GENERATOR GUARDRAIL FAILURE -> DETERMINISTIC FALLBACK", passed, f"mode={comm['generation_mode']}")


def test_27_deterministic_fallback_reproducibility():
    """Verify repeated calls with identical context produce 100% byte-identical output."""
    dec = _mock_m4_decision(action="discount")
    ctx = _mock_approved_context(action="discount", amount=5000.0, discount_pct=20.0)

    comm1 = compose_customer_communication(dec, ctx)
    comm2 = compose_customer_communication(dec, ctx)

    passed = (comm1["body"] == comm2["body"] and comm1["subject"] == comm2["subject"] and comm1["sendable"] == comm2["sendable"])
    return _report(27, "DETERMINISTIC FALLBACK REPRODUCIBILITY", passed, f"identical={passed}")


# ===========================================================================
# 5. Internal Explanation Tests (Tests 28 - 31)
# ===========================================================================

def test_28_internal_decision_explanation():
    """Verify internal decision explanation transparently details M3 policy and M4 EV."""
    dec = _mock_m4_decision(action="retry", prob=0.65, ev=648.0)
    exp = explain_decision(dec)

    passed = (
        exp["decision"] == "retry"
        and exp["decision_type"] == "ev_optimization"
        and "648.00" in exp["economic_rationale"]
        and "max_discount_cap_exceeded" in exp["policy_rationale"]
        and "M6 did not select or alter this action" in exp["disclaimer"]
    )
    return _report(28, "INTERNAL DECISION EXPLANATION", passed, f"summary={exp['summary_explanation']}")


def test_29_escalation_explanation():
    """Verify internal explanation for policy-enforced human escalation."""
    dec = _mock_m4_decision(
        action="escalate",
        decision_type="escalation_only",
        decision_reason="high_risk_score_escalation",
        escalation_required=True,
        prob=None,
        ev=None,
    )
    exp = explain_decision(dec)

    passed = (
        exp["decision"] == "escalate"
        and exp["escalation_required"] is True
        and "escalation" in exp["summary_explanation"].lower()
    )
    return _report(29, "ESCALATION EXPLANATION", passed, f"summary={exp['summary_explanation']}")


def test_30_terminal_explanation():
    """Verify internal explanation for terminal forced close upon window expiry."""
    dec = _mock_m4_decision(
        action="close",
        decision_type="terminal_forced_action",
        decision_reason="terminal_recovery_window_expired",
        terminal=True,
        prob=None,
        ev=0.0,
    )
    exp = explain_decision(dec)

    passed = (
        exp["decision"] == "close"
        and exp["terminal"] is True
        and "terminal" in exp["summary_explanation"].lower()
    )
    return _report(30, "TERMINAL EXPLANATION", passed, f"summary={exp['summary_explanation']}")


def test_31_hidden_truth_leakage_prevention():
    """Verify generator with simulator hidden truth tokens (e.g. latent_score) is rejected."""
    dec = _mock_m4_decision(action="retry")
    ctx = _mock_approved_context(action="retry", amount=1000.0)

    bad_generator = lambda d, c: "Your latent_score is high, so we retried ₹1,000.00."
    comm = compose_customer_communication(dec, ctx, generator=bad_generator)

    passed = (
        comm["fallback_used"] is True
        and "latent_score" not in comm["body"]
    )
    return _report(31, "HIDDEN-TRUTH LEAKAGE PREVENTION", passed, f"fallback_used={comm['fallback_used']}")


# ===========================================================================
# 6. Real M4 Integration Fixture (Test 32)
# ===========================================================================

def test_32_real_m4_make_decision_integration():
    """
    Verify real M4 make_decision() output is directly consumable by M6
    without mutating M4 output or altering the selected decision.
    """
    try:
        from ml.decision.decision_engine import make_decision
        from ml.policy.policy_engine import evaluate_policy

        txn_fixture = {
            "transaction_id": "TXN_INTEG_001",
            "amount": 2500.0,
            "failure_type": "temporary_bank_decline",
            "attempt_number": 1,
            "hours_since_failure": 2.0,
            "risk_score": 0.15,
            "contact_fatigue_score": 0.10,
            "segment": "b2c_returning",
            "payment_method": "card",
            "discount_percent": 10.0,
            "lifetime_successful_txns": 5,
            "lifetime_failed_txns": 1,
        }

        # Step 1: Run real M4 make_decision
        m4_result = make_decision(txn_fixture)
        m4_copy = copy.deepcopy(m4_result)

        # Step 2: Pass real M4 result to M6 explanation
        explanation = explain_decision(m4_result)

        # Step 3: Pass real M4 result to M6 communication
        approved_ctx = {
            "transaction_id": txn_fixture["transaction_id"],
            "amount": txn_fixture["amount"],
            "currency": "INR",
            "customer_segment": txn_fixture["segment"],
            "channel": "email",
            "approved_payment_link": "https://pay.example.com/checkout/TXN_INTEG_001",
            "approved_discount_percent": 10.0,
            "customer_display_name": "Rohan Mehra",
        }
        comm = compose_customer_communication(m4_result, approved_ctx)

        # Verify M4 result remained 100% immutable
        m4_unmodified = (m4_result == m4_copy)

        # Verify M6 aligned with M4 decision
        action_aligned = (
            comm["decision"] == m4_result["decision"]
            and explanation["decision"] == m4_result["decision"]
        )

        passed = (
            m4_unmodified
            and action_aligned
            and comm["sendable"] in [True, False]
            and len(explanation["summary_explanation"]) > 0
        )

        return _report(
            32,
            "REAL M4 MAKE_DECISION() INTEGRATION",
            passed,
            f"m4_decision={m4_result['decision']}, sendable={comm['sendable']}, m4_unmodified={m4_unmodified}",
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return _report(32, "REAL M4 MAKE_DECISION() INTEGRATION", False, f"Exception: {e}")


# ===========================================================================
# Main Test Runner
# ===========================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("M6 BOUNDED LLM / COMMUNICATION LAYER — TEST SUITE")
    print("=" * 70)

    # 1. Validation & Immutability
    test_1_valid_m4_decision_validation()
    test_2_malformed_m4_decision_rejection()
    test_3_m4_decision_immutability()

    # 2. Action Communications
    test_4_retry_communication()
    test_5_payment_link_communication()
    test_6_reminder_communication()
    test_7_discount_communication()
    test_8_wait_non_sendable()
    test_9_close_non_sendable()
    test_10_escalate_non_sendable()
    test_11_no_action_required_non_sendable()

    # 3. Guardrails & Rejections
    test_12_unauthorized_amount_rejection()
    test_13_unauthorized_discount_rejection()
    test_14_excessive_invalid_discount_rejection()
    test_15_blocked_action_rejection()
    test_16_alternate_action_recommendation_rejection()
    test_17_invented_url_rejection()
    test_18_invented_identity_rejection()
    test_19_internal_metadata_leakage_rejection()
    test_20_probability_leakage_rejection()
    test_21_ev_leakage_rejection()

    # 4. Context & Edge Cases
    test_22_missing_approved_context()
    test_23_invalid_channel()
    test_24_invalid_segment()
    test_25_optional_generator_success()
    test_26_generator_guardrail_failure_fallback()
    test_27_deterministic_fallback_reproducibility()

    # 5. Internal Explanations
    test_28_internal_decision_explanation()
    test_29_escalation_explanation()
    test_30_terminal_explanation()
    test_31_hidden_truth_leakage_prevention()

    # 6. Real M4 Integration
    test_32_real_m4_make_decision_integration()

    # Summary
    print("\n" + "=" * 70)
    print("M6 TEST SUMMARY")
    print("=" * 70)
    print(f"Total Tests: {PASS_COUNT + FAIL_COUNT}")
    print(f"Passed:      {PASS_COUNT}")
    print(f"Failed:      {FAIL_COUNT}")
    all_pass = (FAIL_COUNT == 0)
    print(f"Overall:     {'PASS' if all_pass else 'FAIL'}")
    print("=" * 70)

    if not all_pass:
        sys.exit(1)
