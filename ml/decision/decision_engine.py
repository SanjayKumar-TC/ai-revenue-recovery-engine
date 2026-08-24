"""
M4: Decision Engine
====================
Orchestrates the full decision pipeline:

    Transaction Context
        → M3 Policy Engine (safety/eligibility)
        → M2 Probability Model (P(recovery|context,action))
        → M4 EV Engine (expected net value)
        → Decision (best permitted action)

POLICY FIRST: an action blocked by M3 is never scored or selected.
Neither probability nor EV can override a policy restriction.
"""

import os
from datetime import datetime

import joblib
import numpy as np
import pandas as pd

from ml.decision.decision_config import (
    ACTION_COSTS,
    ACTION_PRIORITY_ORDER,
    DECISION_ENGINE_VERSION,
    DEFAULT_DISCOUNT_PERCENT,
    EV_TIE_TOLERANCE,
)
from ml.decision.ev_engine import calculate_ev, calculate_ev_for_actions
from ml.policy.policy_config import POLICY_VERSION
from ml.policy.policy_engine import evaluate_policy

# ---------------------------------------------------------------------------
# M2 Model Loading
# ---------------------------------------------------------------------------

MODEL_PATH = os.path.join("ml", "models", "recovery_model.joblib")

# Feature columns matching M2's pipeline exactly
CATEGORICAL_FEATURES = [
    "failure_type", "action", "segment", "payment_method",
    "failure_action", "segment_action",
]
NUMERIC_FEATURES = [
    "risk_score", "attempt_number", "contact_fatigue_score",
    "log1p_amount", "log1p_lifetime_successful_txns", "log1p_lifetime_failed_txns",
]
FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES


def load_model(model_path=None):
    """Load the M2 model pipeline. Returns (pipeline, None) or (None, error_str)."""
    path = model_path or MODEL_PATH
    try:
        pipeline = joblib.load(path)
        return pipeline, None
    except Exception as e:
        return None, str(e)


def predict_probability(pipeline, transaction, action):
    """
    Use the M2 pipeline to predict P(recovery | context, action).
    Builds a single-row DataFrame matching the M2 feature schema.
    """
    row = {
        "failure_type": transaction["failure_type"],
        "action": action,
        "segment": transaction["segment"],
        "payment_method": transaction["payment_method"],
        "failure_action": f"{transaction['failure_type']}__{action}",
        "segment_action": f"{transaction['segment']}__{action}",
        "risk_score": transaction["risk_score"],
        "attempt_number": transaction["attempt_number"],
        "contact_fatigue_score": transaction["contact_fatigue_score"],
        "log1p_amount": np.log1p(transaction["amount"]),
        "log1p_lifetime_successful_txns": np.log1p(transaction.get("lifetime_successful_txns", 0)),
        "log1p_lifetime_failed_txns": np.log1p(transaction.get("lifetime_failed_txns", 0)),
    }
    df = pd.DataFrame([row])[FEATURE_COLUMNS]
    prob = pipeline.predict_proba(df)[:, 1][0]
    return float(prob)


# ---------------------------------------------------------------------------
# Tie-Breaking
# ---------------------------------------------------------------------------

def _tiebreak_key(ev_result):
    """
    Sort key for deterministic tie-breaking when EVs are equal.
    Cascade:
      1. Lower intervention cost (ascending)
      2. Higher predicted probability (descending → negate)
      3. Fixed priority order (ascending index)
    """
    action = ev_result["action"]
    cost = ev_result["intervention_cost"]
    prob = ev_result["predicted_probability"]
    try:
        priority = ACTION_PRIORITY_ORDER.index(action)
    except ValueError:
        priority = len(ACTION_PRIORITY_ORDER)
    return (cost, -prob, priority)


def select_best_action(ev_results):
    """
    Select the action with highest EV, with deterministic tie-breaking.

    Returns: (best_action_str, best_ev_result, decision_reason)
    """
    if not ev_results:
        return None, None, "no_actions_to_evaluate"

    sorted_actions = sorted(
        ev_results.values(),
        key=lambda r: (-r["expected_net_value"], _tiebreak_key(r))
    )

    best = sorted_actions[0]

    if len(sorted_actions) > 1:
        second = sorted_actions[1]
        if abs(best["expected_net_value"] - second["expected_net_value"]) < EV_TIE_TOLERANCE:
            reason = "highest_expected_net_value_tiebreak"
        else:
            reason = "highest_expected_net_value"
    else:
        reason = "highest_expected_net_value"

    return best["action"], best, reason


# ---------------------------------------------------------------------------
# Decision Engine — Main Entry Point
# ---------------------------------------------------------------------------

def make_decision(transaction, model_pipeline=None, _policy_result_override=None):
    """
    Full decision pipeline: M3 → M2 → EV → Decision.

    Parameters
    ----------
    transaction : dict — transaction context
    model_pipeline : object or None
        If a valid sklearn pipeline, used directly for prediction.
        If None, loads from disk.
        If a non-None object that fails prediction, triggers model-unavailable path.
    _policy_result_override : dict or None — for testing, bypasses M3 call
    """
    timestamp = datetime.utcnow().isoformat()
    txn_id = transaction.get("transaction_id", "unknown") if isinstance(transaction, dict) else "unknown"

    # ================================================================
    # STEP 1: EVALUATE M3 POLICY
    # ================================================================
    if _policy_result_override is not None:
        policy_result = _policy_result_override
    else:
        policy_result = evaluate_policy(transaction)

    allowed_actions = policy_result.get("allowed_actions", [])
    blocked_actions = policy_result.get("blocked_actions", {})
    escalation_required = policy_result.get("escalation_required", False)
    terminal = policy_result.get("terminal", False)

    # ================================================================
    # STEP 2: HANDLE TERMINAL — EMPTY ALLOWED ACTIONS
    # ================================================================
    if terminal and len(allowed_actions) == 0:
        all_reasons = set()
        for reasons_list in blocked_actions.values():
            if isinstance(reasons_list, list):
                all_reasons.update(reasons_list)

        if "already_recovered" in all_reasons:
            decision_reason = "already_recovered_terminal"
        elif "recovery_window_expired" in all_reasons:
            decision_reason = "recovery_window_expired_terminal"
        else:
            decision_reason = "terminal_all_blocked"

        return {
            "transaction_id": txn_id,
            "policy_version": POLICY_VERSION,
            "decision": "no_action_required",
            "decision_type": "terminal_no_action",
            "decision_reason": decision_reason,
            "escalation_required": escalation_required,
            "terminal": True,
            "selected_probability": None,
            "selected_ev": None,
            "action_analysis": {},
            "allowed_actions": allowed_actions,
            "blocked_actions": blocked_actions,
            "model_version": "N/A",
            "decision_engine_version": DECISION_ENGINE_VERSION,
            "evaluated_at": timestamp,
        }

    # ================================================================
    # STEP 3: HANDLE TERMINAL — SINGLE FORCED ACTION (e.g. close)
    # ================================================================
    if terminal and len(allowed_actions) == 1:
        single_action = allowed_actions[0]

        all_reasons = set()
        for reasons_list in blocked_actions.values():
            if isinstance(reasons_list, list):
                all_reasons.update(reasons_list)

        if "recovery_window_expired" in all_reasons:
            decision_reason = "terminal_recovery_window_expired"
        else:
            decision_reason = "single_permitted_action"

        amount = transaction.get("amount", 0) if isinstance(transaction, dict) else 0
        ev_result = calculate_ev(single_action, 0.0, amount)

        return {
            "transaction_id": txn_id,
            "policy_version": POLICY_VERSION,
            "decision": single_action,
            "decision_type": "terminal_forced_action",
            "decision_reason": decision_reason,
            "escalation_required": escalation_required,
            "terminal": True,
            "selected_probability": None,
            "selected_ev": ev_result["expected_net_value"],
            "action_analysis": {single_action: ev_result},
            "allowed_actions": allowed_actions,
            "blocked_actions": blocked_actions,
            "model_version": "N/A",
            "decision_engine_version": DECISION_ENGINE_VERSION,
            "evaluated_at": timestamp,
        }

    # ================================================================
    # STEP 4: LOAD M2 MODEL
    # ================================================================
    pipeline = model_pipeline
    if pipeline is None:
        pipeline, load_error = load_model()
        if pipeline is None:
            return _model_unavailable_result(
                txn_id, policy_result, load_error, timestamp
            )

    # ================================================================
    # STEP 5: PREDICT PROBABILITIES FOR ALLOWED ACTIONS ONLY
    # ================================================================
    # Escalate does NOT participate in normal EV optimization
    scoreable_actions = [a for a in allowed_actions if a != "escalate"]

    action_probabilities = {}
    for action in scoreable_actions:
        try:
            prob = predict_probability(pipeline, transaction, action)
            action_probabilities[action] = prob
        except Exception as e:
            # If prediction fails, model is effectively unavailable
            return _model_unavailable_result(
                txn_id, policy_result, f"prediction_failed_{action}: {e}", timestamp
            )

    # ================================================================
    # STEP 6: CALCULATE EV FOR ALL SCOREABLE ACTIONS
    # ================================================================
    amount = transaction.get("amount", 0)
    discount_percent = transaction.get("discount_percent", None)

    ev_results = calculate_ev_for_actions(action_probabilities, amount, discount_percent)

    # ================================================================
    # STEP 7: HANDLE SINGLE SCOREABLE ACTION (non-terminal)
    # ================================================================
    if len(ev_results) == 1:
        action_name = list(ev_results.keys())[0]
        ev_result = ev_results[action_name]
        return {
            "transaction_id": txn_id,
            "policy_version": POLICY_VERSION,
            "decision": action_name,
            "decision_type": "single_permitted_action",
            "decision_reason": "single_permitted_action",
            "escalation_required": escalation_required,
            "terminal": terminal,
            "selected_probability": ev_result["predicted_probability"],
            "selected_ev": ev_result["expected_net_value"],
            "action_analysis": ev_results,
            "allowed_actions": allowed_actions,
            "blocked_actions": blocked_actions,
            "model_version": "M2_logistic_regression",
            "decision_engine_version": DECISION_ENGINE_VERSION,
            "evaluated_at": timestamp,
        }

    # ================================================================
    # STEP 8: HANDLE ZERO SCOREABLE ACTIONS (e.g. only escalate allowed)
    # ================================================================
    if len(ev_results) == 0:
        if escalation_required and "escalate" in allowed_actions:
            return {
                "transaction_id": txn_id,
                "policy_version": POLICY_VERSION,
                "decision": "escalate",
                "decision_type": "escalation_only",
                "decision_reason": "escalation_required_by_policy",
                "escalation_required": True,
                "terminal": terminal,
                "selected_probability": None,
                "selected_ev": None,
                "action_analysis": {},
                "allowed_actions": allowed_actions,
                "blocked_actions": blocked_actions,
                "model_version": "N/A",
                "decision_engine_version": DECISION_ENGINE_VERSION,
                "evaluated_at": timestamp,
            }
        else:
            return {
                "transaction_id": txn_id,
                "policy_version": POLICY_VERSION,
                "decision": "no_action_required",
                "decision_type": "safe_fallback",
                "decision_reason": "no_scoreable_actions",
                "escalation_required": escalation_required,
                "terminal": True,
                "selected_probability": None,
                "selected_ev": None,
                "action_analysis": {},
                "allowed_actions": allowed_actions,
                "blocked_actions": blocked_actions,
                "model_version": "N/A",
                "decision_engine_version": DECISION_ENGINE_VERSION,
                "evaluated_at": timestamp,
            }

    # ================================================================
    # STEP 9: SELECT BEST ACTION BY EV (with tie-breaking)
    # ================================================================
    best_action, best_ev, decision_reason = select_best_action(ev_results)

    return {
        "transaction_id": txn_id,
        "policy_version": POLICY_VERSION,
        "decision": best_action,
        "decision_type": "ev_optimization",
        "decision_reason": decision_reason,
        "escalation_required": escalation_required,
        "terminal": terminal,
        "selected_probability": best_ev["predicted_probability"],
        "selected_ev": best_ev["expected_net_value"],
        "action_analysis": ev_results,
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "model_version": "M2_logistic_regression",
        "decision_engine_version": DECISION_ENGINE_VERSION,
        "evaluated_at": timestamp,
    }


def _model_unavailable_result(txn_id, policy_result, error, timestamp):
    """Deterministic fallback when M2 model is unavailable."""
    allowed = policy_result.get("allowed_actions", [])
    escalation_required = policy_result.get("escalation_required", False)
    terminal = policy_result.get("terminal", False)

    if "escalate" in allowed:
        decision = "escalate"
        decision_type = "model_unavailable"
        decision_reason = "model_unavailable_escalation"
    elif terminal:
        decision = "no_action_required"
        decision_type = "model_unavailable"
        decision_reason = "model_unavailable_terminal"
    else:
        # Double-fallback: escalate not available, not terminal
        decision = "no_action_required"
        decision_type = "safe_fallback"
        decision_reason = "model_unavailable_no_escalation"

    return {
        "transaction_id": txn_id,
        "policy_version": POLICY_VERSION,
        "decision": decision,
        "decision_type": decision_type,
        "decision_reason": decision_reason,
        "escalation_required": True,
        "terminal": terminal,
        "selected_probability": None,
        "selected_ev": None,
        "action_analysis": {},
        "allowed_actions": allowed,
        "blocked_actions": policy_result.get("blocked_actions", {}),
        "model_version": f"unavailable: {error}",
        "decision_engine_version": DECISION_ENGINE_VERSION,
        "evaluated_at": timestamp,
    }
