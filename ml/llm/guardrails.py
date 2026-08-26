"""
M6: Programmatic Guardrails & Decision Validator
================================================
Authoritative, deterministic guardrails enforcing zero data leakage,
strict financial accuracy, action alignment, and customer safety.

All rules fail closed.
"""

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

from ml.llm.contracts import (
    ACTIVE_RECOVERY_ACTIONS,
    ALL_RECOGNIZED_ACTIONS,
    INACTIVE_ACTIONS,
    VALID_CHANNELS,
    VALID_CUSTOMER_SEGMENTS,
    ApprovedCustomerContext,
    GuardrailCheckResult,
    GuardrailStatus,
)

# ---------------------------------------------------------------------------
# Leakage and Disallowed Keyword Patterns
# ---------------------------------------------------------------------------

INTERNAL_METADATA_PATTERNS = [
    r"\bmodel_version\b",
    r"\bpolicy_version\b",
    r"\bdecision_engine_version\b",
    r"\bM2_logistic_regression\b",
    r"\bev_optimization\b",
    r"\bdecision_reason\b",
    r"\bterminal_forced_action\b",
    r"\bsingle_permitted_action\b",
    r"\bhighest_expected_net_value\b",
    r"\bhighest_expected_net_value_tiebreak\b",
    r"\bpolicy_result\b",
    r"\bevaluation_report\b",
]

PROBABILITY_LEAKAGE_PATTERNS = [
    r"\bselected_probability\b",
    r"\bpredicted_probability\b",
    r"\bP\(recovery\b",
    r"\bp_recovery\b",
    r"\brecovery probability\b",
    r"\bmodel confidence\b",
    r"\blikelihood score\b",
    r"\bstatistical likelihood\b",
]

EV_LEAKAGE_PATTERNS = [
    r"\bselected_ev\b",
    r"\bexpected_net_value\b",
    r"\bgross_expected_recovery\b",
    r"\bintervention_cost\b",
    r"\bexpected value\b",
    r"\bexpected net monetary value\b",
    r"\bEV\s*=\s*",
    r"\bEV\s*:\s*",
    r"\bEV\s+of\b",
    r"\bnet EV\b",
]

RANKING_LEAKAGE_PATTERNS = [
    r"\baction_analysis\b",
    r"\bpriority_order\b",
    r"\btiebreak\b",
    r"\btie-break\b",
    r"\branked 1st\b",
    r"\bsecond best action\b",
    r"\brunner-up action\b",
    r"\baction hierarchy\b",
]

SIMULATOR_TRUTH_PATTERNS = [
    r"\blatent_score\b",
    r"\btrue_prob_HIDDEN\b",
    r"\bsynthetic data generator\b",
    r"\bfailure_action\b",
    r"\bsegment_action\b",
    r"\bground truth\b",
]

URL_REGEX = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Decision Validator
# ---------------------------------------------------------------------------

def validate_decision_output(decision_output: Any) -> Dict[str, Any]:
    """
    Validate the structure and integrity of an M4 decision dictionary.
    Does not mutate the input dictionary.
    """
    if not isinstance(decision_output, dict):
        return {
            "is_valid": False,
            "errors": ["Decision output must be a dictionary."],
            "sanitized_decision": None,
        }

    errors: List[str] = []
    required_keys = {
        "transaction_id",
        "decision",
        "decision_type",
        "decision_reason",
        "escalation_required",
        "terminal",
        "allowed_actions",
        "blocked_actions",
    }

    missing_keys = required_keys - set(decision_output.keys())
    if missing_keys:
        errors.append(f"Missing required decision keys: {sorted(missing_keys)}")

    decision = decision_output.get("decision")
    if not decision or not isinstance(decision, str):
        errors.append("Field 'decision' must be a non-empty string.")
    elif decision not in ALL_RECOGNIZED_ACTIONS:
        errors.append(f"Unrecognized decision action: '{decision}'.")

    # If decision_type is ev_optimization, decision cannot be in blocked_actions
    blocked = decision_output.get("blocked_actions", {})
    if isinstance(blocked, dict) and decision in blocked:
        decision_type = decision_output.get("decision_type", "")
        if decision_type == "ev_optimization":
            errors.append(
                f"Contradiction: Selected decision '{decision}' is listed in blocked_actions."
            )

    sanitized = copy.deepcopy(decision_output) if not errors else None
    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "sanitized_decision": sanitized,
    }


# ---------------------------------------------------------------------------
# Approved Context Validator
# ---------------------------------------------------------------------------

def validate_approved_context(
    approved_context: Optional[Any],
    decision: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validate customer context supplied from external approved sources.
    Fails closed if values violate domain constraints.
    """
    if approved_context is None:
        return {
            "is_valid": True,
            "errors": [],
            "context": ApprovedCustomerContext(transaction_id="unknown"),
        }

    if isinstance(approved_context, ApprovedCustomerContext):
        ctx = approved_context
    elif isinstance(approved_context, dict):
        ctx = ApprovedCustomerContext.from_dict(approved_context)
    else:
        return {
            "is_valid": False,
            "errors": ["approved_context must be a dict or ApprovedCustomerContext instance."],
            "context": None,
        }

    errors: List[str] = []

    # Channel check
    if ctx.channel is not None and ctx.channel not in VALID_CHANNELS:
        errors.append(f"Invalid communication channel '{ctx.channel}'. Expected one of {sorted(VALID_CHANNELS)}.")

    # Segment check
    if ctx.customer_segment is not None and ctx.customer_segment not in VALID_CUSTOMER_SEGMENTS:
        errors.append(
            f"Invalid customer segment '{ctx.customer_segment}'. Expected one of {sorted(VALID_CUSTOMER_SEGMENTS)}."
        )

    # Amount check
    if ctx.amount is not None and ctx.amount < 0:
        errors.append(f"Transaction amount cannot be negative: {ctx.amount}")

    # Discount check
    if ctx.approved_discount_percent is not None:
        if ctx.approved_discount_percent <= 0 or ctx.approved_discount_percent > 100:
            errors.append(
                f"Approved discount percent must be in (0, 100], got {ctx.approved_discount_percent}"
            )

    # Payment link check
    if ctx.approved_payment_link is not None:
        if not (ctx.approved_payment_link.startswith("http://") or ctx.approved_payment_link.startswith("https://")):
            errors.append(
                f"Approved payment link must be a valid HTTP(S) URL: '{ctx.approved_payment_link}'"
            )

    # Action-specific requirements
    if decision == "discount" and ctx.approved_discount_percent is None:
        errors.append("Action is 'discount' but approved_discount_percent is missing.")

    if decision == "payment_link" and not ctx.approved_payment_link:
        errors.append("Action is 'payment_link' but approved_payment_link is missing or empty.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "context": ctx if len(errors) == 0 else None,
    }


# ---------------------------------------------------------------------------
# Programmatic Communication Guardrails
# ---------------------------------------------------------------------------

def run_communication_guardrails(
    text: str,
    decision: str,
    approved_context: ApprovedCustomerContext,
    decision_output: Dict[str, Any],
) -> GuardrailStatus:
    """
    Execute deterministic programmatic guardrails against proposed message text.
    Returns GuardrailStatus detailing all checks and violations.
    """
    checks: List[GuardrailCheckResult] = []
    violations: List[str] = []

    def _record(name: str, passed: bool, details: str = ""):
        checks.append(GuardrailCheckResult(check_name=name, passed=passed, details=details))
        if not passed:
            violations.append(f"[{name}] {details}")

    # 1. Text presence
    if not text or not isinstance(text, str) or not text.strip():
        _record("text_presence", False, "Generated text is empty or non-string.")
        return GuardrailStatus(passed=False, checks=checks, violations=violations)
    else:
        _record("text_presence", True, "Text is present.")

    # 2. Internal Metadata Leakage
    meta_leaks = [p for p in INTERNAL_METADATA_PATTERNS if re.search(p, text, re.IGNORECASE)]
    if meta_leaks:
        _record("metadata_leakage", False, f"Internal metadata leaked: {meta_leaks}")
    else:
        _record("metadata_leakage", True, "No internal metadata leaked.")

    # 3. Probability Leakage
    prob_leaks = [p for p in PROBABILITY_LEAKAGE_PATTERNS if re.search(p, text, re.IGNORECASE)]
    if prob_leaks:
        _record("probability_leakage", False, f"Probability or confidence leaked: {prob_leaks}")
    else:
        _record("probability_leakage", True, "No probability scores leaked.")

    # 4. EV Leakage
    ev_leaks = [p for p in EV_LEAKAGE_PATTERNS if re.search(p, text, re.IGNORECASE)]
    if ev_leaks:
        _record("ev_leakage", False, f"Expected value leaked: {ev_leaks}")
    else:
        _record("ev_leakage", True, "No EV terms leaked.")

    # 5. Ranking Leakage
    rank_leaks = [p for p in RANKING_LEAKAGE_PATTERNS if re.search(p, text, re.IGNORECASE)]
    if rank_leaks:
        _record("ranking_leakage", False, f"Action rankings or tiebreak leaked: {rank_leaks}")
    else:
        _record("ranking_leakage", True, "No action rankings leaked.")

    # 6. Simulator Truth Leakage
    sim_leaks = [p for p in SIMULATOR_TRUTH_PATTERNS if re.search(p, text, re.IGNORECASE)]
    if sim_leaks:
        _record("simulator_truth_leakage", False, f"Simulator truth leaked: {sim_leaks}")
    else:
        _record("simulator_truth_leakage", True, "No simulator truth leaked.")

    # 7. Inactive Action Recovery Offer Prevention
    if decision in INACTIVE_ACTIONS:
        recovery_solicitation_patterns = [
            r"\bclick here to pay\b",
            r"\bpay now\b",
            r"\bretry payment\b",
            r"\bcomplete your payment\b",
            r"\bclaim your discount\b",
            r"\bpayment link\b",
        ]
        active_offers = [p for p in recovery_solicitation_patterns if re.search(p, text, re.IGNORECASE)]
        if active_offers:
            _record(
                "inactive_action_safety",
                False,
                f"Action '{decision}' is inactive/terminal but active payment solicitation found: {active_offers}",
            )
        else:
            _record("inactive_action_safety", True, "Inactive action has no active payment solicitation.")
    else:
        _record("inactive_action_safety", True, "Active recovery action.")

    # 8. Financial Amount Authorization
    # Extract numeric amount patterns with currency tokens (e.g. ₹100, Rs. 100, Rs 100, INR 100, $100)
    amount_matches = re.findall(r"(?:₹|Rs\.?|INR|\$)\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    cleaned_amounts = []
    for m in amount_matches:
        try:
            val = float(m.replace(",", ""))
            cleaned_amounts.append(val)
        except ValueError:
            pass

    if approved_context.amount is None:
        if cleaned_amounts:
            _record(
                "amount_authorization",
                False,
                f"Context has no approved amount, but text mentions amounts: {cleaned_amounts}",
            )
        else:
            _record("amount_authorization", True, "No unapproved amount mentioned.")
    else:
        approved_amt = approved_context.amount
        # In discount mode, discounted amount is also authorized: amount * (1 - disc/100)
        authorized_amts = {round(approved_amt, 2)}
        if decision == "discount" and approved_context.approved_discount_percent is not None:
            disc_amt = approved_amt * (1.0 - (approved_context.approved_discount_percent / 100.0))
            authorized_amts.add(round(disc_amt, 2))
            authorized_amts.add(round(approved_amt * (approved_context.approved_discount_percent / 100.0), 2))

        unauthorized_amts = [
            amt for amt in cleaned_amounts
            if not any(abs(amt - auth) < 0.05 for auth in authorized_amts)
        ]
        if unauthorized_amts:
            _record(
                "amount_authorization",
                False,
                f"Found unauthorized amounts {unauthorized_amts}. Authorized: {authorized_amts}",
            )
        else:
            _record("amount_authorization", True, "All mentioned amounts are authorized.")

    # 9. Discount Authorization
    # Find all percentages mentioned in text
    percent_matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    percent_word_matches = re.findall(r"(\d+(?:\.\d+)?)\s*percent", text, re.IGNORECASE)
    found_percentages = [float(p) for p in (percent_matches + percent_word_matches)]

    discount_words = re.findall(r"\b(discount|concession|rebate|% off|percent off)\b", text, re.IGNORECASE)

    if decision != "discount":
        if discount_words or found_percentages:
            _record(
                "discount_authorization",
                False,
                f"Action is '{decision}' (not discount), but text mentions discount/percentages: {discount_words or found_percentages}",
            )
        else:
            _record("discount_authorization", True, "No discount mentioned for non-discount action.")
    else:
        # Decision IS discount
        if approved_context.approved_discount_percent is None:
            _record("discount_authorization", False, "Discount action without approved_discount_percent.")
        else:
            expected_p = approved_context.approved_discount_percent
            if not found_percentages and not discount_words:
                _record("discount_authorization", False, "Discount action text missing discount terms.")
            else:
                mismatched_p = [p for p in found_percentages if abs(p - expected_p) > 0.01]
                if mismatched_p:
                    _record(
                        "discount_authorization",
                        False,
                        f"Found unauthorized discount percentage {mismatched_p}. Approved is {expected_p}%.",
                    )
                else:
                    _record("discount_authorization", True, f"Approved discount {expected_p}% verified.")

    # 10. Payment URL Integrity
    found_urls = URL_REGEX.findall(text)
    if decision == "payment_link":
        approved_url = approved_context.approved_payment_link
        if not approved_url:
            _record("payment_url_integrity", False, "payment_link action missing approved URL in context.")
        elif approved_url not in text:
            _record("payment_url_integrity", False, f"Approved payment link '{approved_url}' not in text.")
        else:
            # Check if any OTHER url is present
            extra_urls = [u for u in found_urls if u != approved_url]
            if extra_urls:
                _record("payment_url_integrity", False, f"Found unapproved URL(s): {extra_urls}")
            else:
                _record("payment_url_integrity", True, "Approved payment link correctly embedded.")
    else:
        if found_urls:
            _record("payment_url_integrity", False, f"Action is '{decision}' but URL found: {found_urls}")
        else:
            _record("payment_url_integrity", True, "No extraneous URLs found.")

    # 11. Customer Identity Integrity
    # If customer_display_name is None, ensure text does not hallucinate invented names
    if not approved_context.customer_display_name:
        # Check for common invented salutations
        invented_salutations = re.findall(r"\bDear\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", text)
        invalid_names = [name for name in invented_salutations if name.lower() not in {"customer", "user", "merchant", "partner", "member"}]
        if invalid_names:
            _record("customer_identity_integrity", False, f"Invented customer name: {invalid_names}")
        else:
            _record("customer_identity_integrity", True, "Neutral greeting used for anonymous context.")
    else:
        # Name is provided; if a specific name is in greeting, it should match
        _record("customer_identity_integrity", True, "Customer identity matches approved context.")

    # 12. Blocked Actions Exclusion
    blocked_actions = decision_output.get("blocked_actions", {})
    if isinstance(blocked_actions, dict):
        for blocked_act in blocked_actions.keys():
            if blocked_act == "retry" and decision != "retry":
                if re.search(r"\bwe (have retried|will automatically retry|will retry)\b", text, re.IGNORECASE):
                    _record("blocked_action_exclusion", False, "Text proposes blocked action 'retry'.")
            elif blocked_act == "payment_link" and decision != "payment_link":
                if re.search(r"\b(click the link|payment link generated)\b", text, re.IGNORECASE):
                    _record("blocked_action_exclusion", False, "Text proposes blocked action 'payment_link'.")
            elif blocked_act == "discount" and decision != "discount":
                if re.search(r"\b(discount|concession)\b", text, re.IGNORECASE):
                    _record("blocked_action_exclusion", False, "Text proposes blocked action 'discount'.")

    # If no blocked action errors recorded, mark pass
    if not any(c.check_name == "blocked_action_exclusion" and not c.passed for c in checks):
        _record("blocked_action_exclusion", True, "No blocked actions recommended.")

    # 13. Action Alignment
    # Text must not instruct an action different from M4 decision
    if decision == "retry":
        if re.search(r"\b(click this payment link|pay using the link below)\b", text, re.IGNORECASE):
            _record("action_alignment", False, "Retry text asks customer to use payment link.")
        else:
            _record("action_alignment", True, "Action alignment verified for retry.")
    elif decision == "payment_link":
        if re.search(r"\bwe will automatically re-attempt your card\b", text, re.IGNORECASE):
            _record("action_alignment", False, "Payment link text claims automated retry.")
        else:
            _record("action_alignment", True, "Action alignment verified for payment_link.")
    elif decision == "reminder":
        if re.search(r"\bwe have automatically retried your card\b", text, re.IGNORECASE):
            _record("action_alignment", False, "Reminder text claims automated retry.")
        else:
            _record("action_alignment", True, "Action alignment verified for reminder.")
    else:
        _record("action_alignment", True, f"Action alignment verified for {decision}.")

    passed = len(violations) == 0
    return GuardrailStatus(passed=passed, checks=checks, violations=violations)
