"""
M3: Deterministic Policy Engine
================================
Sits between the ML probability model (M2) and the future EV/Decision
Engine (M4):

    Transaction Context -> M3 Policy Engine -> Allowed/Blocked actions

M3 determines ACTION ELIGIBILITY and SAFETY only.
M3 does NOT calculate expected monetary value.
M3 does NOT choose the economically optimal action.
M3 does NOT use an LLM.
M3 does NOT let probability override a safety rule.

Same input always produces the same policy result (deterministic).
"""

from datetime import datetime

from ml.policy.eligibility import (
    ALL_ACTIONS,
    AUTOMATED_RECOVERY_ACTIONS,
    CONTACT_ACTIONS,
    get_eligible_actions,
)
from ml.policy.policy_config import (
    HIGH_RISK_BLOCK_THRESHOLD,
    HIGH_RISK_ESCALATION_THRESHOLD,
    MAX_AUTO_RECOVERY_AMOUNT,
    MAX_AUTO_RETRIES,
    MAX_CONTACT_FATIGUE,
    MAX_DISCOUNT_PERCENT,
    POLICY_VERSION,
    RECOVERY_WINDOW_HOURS,
)


def _block_action(blocked_actions, action, reason):
    """Add a block reason to an action. Multiple rules can each record their
    own reason on the same action — all reasons are preserved as a list."""
    if action not in blocked_actions:
        blocked_actions[action] = []
    blocked_actions[action].append(reason)


def evaluate_policy(transaction):
    """
    Evaluate all policy rules for a transaction and return the policy result.

    Parameters
    ----------
    transaction : dict
        Must contain at minimum:
            - transaction_id
            - failure_type : str
            - amount : float
            - risk_score : float (0-1, higher = riskier)
            - attempt_number : int
            - contact_fatigue_score : float (0-1)
            - hours_since_failure : float (hours elapsed since the failure event)
            - already_recovered : bool
        Optional:
            - discount_percent : float (if a discount is being considered)

    Returns
    -------
    dict : Policy result with allowed_actions, blocked_actions, blocked_reasons, etc.
          blocked_actions maps action -> [list of all reasons that block it].
    """

    blocked_actions = {}  # action -> [reason1, reason2, ...]
    escalation_required = False
    terminal = False

    # ================================================================
    # STEP 0: INPUT VALIDATION — fail safe on missing/invalid input
    # ================================================================
    validation_error = _validate_input(transaction)
    if validation_error is not None:
        return _safe_failure_result(transaction, validation_error)

    transaction_id = transaction.get("transaction_id", "unknown")
    failure_type = transaction["failure_type"]
    amount = transaction["amount"]
    risk_score = transaction["risk_score"]
    attempt_number = transaction["attempt_number"]
    contact_fatigue = transaction["contact_fatigue_score"]
    hours_since_failure = transaction["hours_since_failure"]
    already_recovered = transaction.get("already_recovered", False)
    discount_percent = transaction.get("discount_percent", 0.0)

    # ================================================================
    # STEP 1: CHECK ALREADY RECOVERED (Rule 1)
    # ================================================================
    if already_recovered:
        return {
            "transaction_id": transaction_id,
            "policy_status": "terminal",
            "allowed_actions": [],
            "blocked_actions": {a: ["already_recovered"] for a in sorted(ALL_ACTIONS)},
            "blocked_reasons": {a: ["already_recovered"] for a in sorted(ALL_ACTIONS)},
            "escalation_required": False,
            "terminal": True,
            "policy_version": POLICY_VERSION,
            "evaluated_at": datetime.utcnow().isoformat(),
        }

    # ================================================================
    # STEP 2: CHECK RECOVERY WINDOW (Rule 6)
    # Deterministic: if expired -> force close, terminal=true
    # ================================================================
    if hours_since_failure > RECOVERY_WINDOW_HOURS:
        all_except_close = sorted(ALL_ACTIONS - {"close"})
        return {
            "transaction_id": transaction_id,
            "policy_status": "terminal",
            "allowed_actions": ["close"],
            "blocked_actions": {a: ["recovery_window_expired"] for a in all_except_close},
            "blocked_reasons": {a: ["recovery_window_expired"] for a in all_except_close},
            "escalation_required": False,
            "terminal": True,
            "policy_version": POLICY_VERSION,
            "evaluated_at": datetime.utcnow().isoformat(),
        }

    # ================================================================
    # STEP 3: GET FAILURE-TYPE ELIGIBILITY (Rule 8)
    # Start with M1 eligible actions, then remove via safety rules
    # ================================================================
    eligible = get_eligible_actions(failure_type)

    # Block any action not eligible for this failure_type
    for action in ALL_ACTIONS:
        if action not in eligible:
            _block_action(blocked_actions, action, "ineligible_for_failure_type")

    # ================================================================
    # STEP 4: CHECK AMOUNT CEILING (Rule 2)
    # ================================================================
    if amount > MAX_AUTO_RECOVERY_AMOUNT:
        for action in AUTOMATED_RECOVERY_ACTIONS:
            if action in eligible:
                _block_action(blocked_actions, action, "amount_above_auto_limit")
        escalation_required = True

    # ================================================================
    # STEP 5: CHECK RISK GATE (Rule 3)
    # Two non-overlapping bands:
    #   risk_score < 0.75              -> normal
    #   0.75 <= risk_score < 0.85      -> mandatory escalation
    #   risk_score >= 0.85             -> block automated recovery
    # ================================================================
    if risk_score >= HIGH_RISK_BLOCK_THRESHOLD:
        # Block all automated recovery actions
        for action in AUTOMATED_RECOVERY_ACTIONS:
            if action in eligible:
                _block_action(blocked_actions, action, "high_risk_block")
        escalation_required = True
    elif risk_score >= HIGH_RISK_ESCALATION_THRESHOLD:
        # Mandatory escalation, but don't block automated actions
        escalation_required = True

    # ================================================================
    # STEP 6: CHECK RETRY CAP (Rule 4)
    # ================================================================
    if attempt_number >= MAX_AUTO_RETRIES:
        if "retry" in eligible:
            _block_action(blocked_actions, "retry", "retry_limit_reached")

    # ================================================================
    # STEP 7: CHECK CONTACT FATIGUE (Rule 5)
    # At or above threshold: block ALL contact actions
    # (reminder, payment_link, discount)
    # ================================================================
    if contact_fatigue >= MAX_CONTACT_FATIGUE:
        for action in CONTACT_ACTIONS:
            if action in eligible:
                _block_action(blocked_actions, action, "contact_fatigue_limit")

    # ================================================================
    # STEP 8: CHECK DISCOUNT LIMIT (Rule 7)
    # ================================================================
    if discount_percent > MAX_DISCOUNT_PERCENT:
        if "discount" in eligible:
            _block_action(blocked_actions, "discount", "discount_limit_exceeded")

    # ================================================================
    # STEP 9: PRODUCE FINAL RESULT
    # ================================================================
    allowed = sorted(eligible - set(blocked_actions.keys()))

    # Determine policy_status
    if not allowed:
        policy_status = "terminal"
        terminal = True
        # If nothing is allowed at all and escalation hasn't been set,
        # escalate as safe fallback
        if not escalation_required:
            escalation_required = True
    elif escalation_required or len(blocked_actions) > 0:
        policy_status = "restricted"
    else:
        policy_status = "allowed"

    # Ensure escalate is in allowed if escalation is required and it's eligible
    if escalation_required and "escalate" in eligible and "escalate" not in blocked_actions:
        if "escalate" not in allowed:
            allowed.append("escalate")
            allowed.sort()

    return {
        "transaction_id": transaction_id,
        "policy_status": policy_status,
        "allowed_actions": allowed,
        "blocked_actions": blocked_actions,
        "blocked_reasons": blocked_actions,  # same ref: action -> [reasons]
        "escalation_required": escalation_required,
        "terminal": terminal,
        "policy_version": POLICY_VERSION,
        "evaluated_at": datetime.utcnow().isoformat(),
    }


def _validate_input(transaction):
    """Validate required fields. Returns error string or None."""
    if not isinstance(transaction, dict):
        return "input_not_dict"

    required = ["failure_type", "amount", "risk_score", "attempt_number",
                "contact_fatigue_score", "hours_since_failure"]
    for field in required:
        if field not in transaction:
            return f"missing_{field}"

    # Type/range checks
    try:
        amount = float(transaction["amount"])
        if amount < 0:
            return "invalid_amount_negative"
    except (TypeError, ValueError):
        return "invalid_amount"

    try:
        risk_score = float(transaction["risk_score"])
        if not (0.0 <= risk_score <= 1.0):
            return "invalid_risk_score_range"
    except (TypeError, ValueError):
        return "invalid_risk_score"

    try:
        attempt = int(transaction["attempt_number"])
        if attempt < 1:
            return "invalid_attempt_number"
    except (TypeError, ValueError):
        return "invalid_attempt_number"

    try:
        fatigue = float(transaction["contact_fatigue_score"])
        if not (0.0 <= fatigue <= 1.0):
            return "invalid_contact_fatigue_range"
    except (TypeError, ValueError):
        return "invalid_contact_fatigue"

    try:
        hours = float(transaction["hours_since_failure"])
        if hours < 0:
            return "invalid_hours_negative"
    except (TypeError, ValueError):
        return "invalid_hours_since_failure"

    ft = transaction["failure_type"]
    from ml.policy.eligibility import ELIGIBILITY
    if ft not in ELIGIBILITY:
        return f"unknown_failure_type_{ft}"

    return None


def _safe_failure_result(transaction, error_reason):
    """Return a safe deterministic result when input is invalid."""
    return {
        "transaction_id": transaction.get("transaction_id", "unknown") if isinstance(transaction, dict) else "unknown",
        "policy_status": "terminal",
        "allowed_actions": ["escalate"],
        "blocked_actions": {"all_automated": [error_reason]},
        "blocked_reasons": {"validation_error": [error_reason]},
        "escalation_required": True,
        "terminal": True,
        "policy_version": POLICY_VERSION,
        "evaluated_at": datetime.utcnow().isoformat(),
    }
