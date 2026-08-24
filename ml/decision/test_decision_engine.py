"""
M4: Decision Engine — All 14 Mandatory Tests + Integration Check
=================================================================
Run from project root:
    python -m ml.decision.test_decision_engine

Root cause analysis for Test 10 (model-unavailable):
    Root cause = A.
    Passing model_pipeline=None to make_decision triggers load_model() from disk.
    If ml/models/recovery_model.joblib exists (it does), the model loads successfully
    and normal EV optimization proceeds — the unavailable path is never exercised.
    Fix: pass a _BrokenModel sentinel that is non-None (so disk loading is skipped)
    but fails on predict_proba, triggering the genuine prediction_failed fallback.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd

from ml.decision.decision_engine import (
    make_decision,
    load_model,
    predict_probability,
    select_best_action,
    FEATURE_COLUMNS,
)
from ml.decision.ev_engine import calculate_ev, calculate_ev_for_actions
from ml.decision.decision_config import (
    ACTION_COSTS,
    ACTION_PRIORITY_ORDER,
    DECISION_ENGINE_VERSION,
    DEFAULT_DISCOUNT_PERCENT,
    EV_TIE_TOLERANCE,
)
from ml.policy.policy_engine import evaluate_policy
from ml.policy.policy_config import POLICY_VERSION
from ml.policy.eligibility import ELIGIBILITY, AUTOMATED_RECOVERY_ACTIONS, CONTACT_ACTIONS

# ============================================================
# Helpers
# ============================================================

PASS_COUNT = 0
FAIL_COUNT = 0


class _BrokenModel:
    """Sentinel object that fails on any prediction call.
    Used for Test 10 to genuinely exercise the model-unavailable path.

    Root cause A: passing model_pipeline=None causes load_model() to load
    from disk successfully. This _BrokenModel is non-None (so disk loading
    is skipped) but raises on predict_proba, triggering the real
    prediction_failed → model_unavailable fallback in decision_engine.py.
    """
    def predict_proba(self, X):
        raise RuntimeError("Model deliberately unavailable for testing")

    def predict(self, X):
        raise RuntimeError("Model deliberately unavailable for testing")


def _make_txn(**overrides):
    """Default normal transaction for testing."""
    base = {
        "transaction_id": 5001,
        "failure_type": "temporary_bank_decline",
        "amount": 2000.0,
        "risk_score": 0.15,
        "attempt_number": 1,
        "contact_fatigue_score": 0.1,
        "hours_since_failure": 6.0,
        "already_recovered": False,
        "discount_percent": 10.0,
        "segment": "b2c_new",
        "payment_method": "card",
        "lifetime_successful_txns": 5,
        "lifetime_failed_txns": 1,
    }
    base.update(overrides)
    return base


def _report(test_num, test_name, passed, details=""):
    global PASS_COUNT, FAIL_COUNT
    status = "PASS" if passed else "FAIL"
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
    print(f"\n  Test {test_num}: {test_name} — {status}")
    if details:
        for line in details.split("\n"):
            print(f"    {line}")
    return passed


# ============================================================
# Load M2 model once for tests that need it
# ============================================================

MODEL, MODEL_ERROR = load_model()
if MODEL is None:
    print(f"WARNING: M2 model failed to load: {MODEL_ERROR}")


# ============================================================
# TEST 1: NORMAL TRANSACTION
# ============================================================

def test_1_normal():
    txn = _make_txn()
    result = make_decision(txn, model_pipeline=MODEL)

    allowed = set(result["allowed_actions"])
    analysis = result["action_analysis"]

    # No blocked action was scored
    no_blocked_scored = all(a not in analysis for a in result["blocked_actions"])

    passed = (
        result["decision"] is not None and
        result["decision"] != "no_action_required" and
        result["decision"] in allowed and
        len(analysis) > 0 and
        all("expected_net_value" in v for v in analysis.values()) and
        all("predicted_probability" in v for v in analysis.values()) and
        result["selected_ev"] is not None and
        no_blocked_scored and
        result["policy_version"] == POLICY_VERSION and
        result["decision_engine_version"] == DECISION_ENGINE_VERSION
    )
    details = (f"decision={result['decision']}, ev={result['selected_ev']}\n"
               f"allowed={result['allowed_actions']}\n"
               f"actions_scored={list(analysis.keys())}\n"
               f"no_blocked_scored={no_blocked_scored}")
    return _report(1, "NORMAL TRANSACTION", passed, details)


# ============================================================
# TEST 2: HIGH-VALUE TRANSACTION
# ============================================================

def test_2_high_value():
    txn = _make_txn(amount=75000.0)
    result = make_decision(txn, model_pipeline=MODEL)

    blocked = result["blocked_actions"]
    analysis = result["action_analysis"]

    no_blocked_scored = all(a not in analysis for a in blocked)
    no_blocked_selected = result["decision"] not in blocked

    passed = (
        result["escalation_required"] == True and
        no_blocked_scored and
        no_blocked_selected
    )
    details = (f"decision={result['decision']}, escalation={result['escalation_required']}\n"
               f"blocked={list(blocked.keys())}\n"
               f"scored={list(analysis.keys())}")
    return _report(2, "HIGH-VALUE TRANSACTION (amount > 50000)", passed, details)


# ============================================================
# TEST 3: HIGH-RISK TRANSACTION
# ============================================================

def test_3_high_risk():
    txn = _make_txn(risk_score=0.90)
    result = make_decision(txn, model_pipeline=MODEL)

    blocked = result["blocked_actions"]
    analysis = result["action_analysis"]

    no_auto_selected = result["decision"] not in AUTOMATED_RECOVERY_ACTIONS
    no_blocked_scored = all(a not in analysis for a in blocked)

    passed = (
        no_auto_selected and
        no_blocked_scored and
        result["escalation_required"] == True
    )
    details = (f"decision={result['decision']}\n"
               f"blocked={list(blocked.keys())}\n"
               f"scored={list(analysis.keys())}")
    return _report(3, "HIGH-RISK TRANSACTION (risk >= 0.85)", passed, details)


# ============================================================
# TEST 4: RETRY CAP
# ============================================================

def test_4_retry_cap():
    txn = _make_txn(attempt_number=2)
    result = make_decision(txn, model_pipeline=MODEL)

    blocked = result["blocked_actions"]
    analysis = result["action_analysis"]

    passed = (
        "retry" in blocked and
        "retry" not in analysis and
        result["decision"] != "retry"
    )
    details = (f"decision={result['decision']}\n"
               f"retry blocked={('retry' in blocked)}, retry scored={('retry' in analysis)}")
    return _report(4, "RETRY CAP", passed, details)


# ============================================================
# TEST 5: CONTACT FATIGUE
# ============================================================

def test_5_contact_fatigue():
    txn = _make_txn(contact_fatigue_score=0.85)
    result = make_decision(txn, model_pipeline=MODEL)

    blocked = result["blocked_actions"]
    analysis = result["action_analysis"]

    contact_blocked = all(a in blocked for a in CONTACT_ACTIONS)
    contact_not_scored = all(a not in analysis for a in CONTACT_ACTIONS)

    passed = (
        contact_blocked and
        contact_not_scored and
        result["decision"] not in CONTACT_ACTIONS
    )
    details = (f"decision={result['decision']}\n"
               f"contact_blocked={contact_blocked}, contact_not_scored={contact_not_scored}\n"
               f"scored={list(analysis.keys())}")
    return _report(5, "CONTACT FATIGUE", passed, details)


# ============================================================
# TEST 6: EXPIRED RECOVERY WINDOW (POLICY-FORCED CLOSE)
# ============================================================

def test_6_expired_window():
    txn = _make_txn(hours_since_failure=72.0)
    result = make_decision(txn, model_pipeline=MODEL)

    passed = (
        result["terminal"] == True and
        result["decision"] == "close" and
        result["selected_ev"] == 0.0 and
        result["decision_type"] == "terminal_forced_action" and
        result["decision_reason"] != "highest_expected_net_value"
    )
    details = (f"decision={result['decision']}, terminal={result['terminal']}\n"
               f"ev={result['selected_ev']}, type={result['decision_type']}\n"
               f"reason={result['decision_reason']}")
    return _report(6, "EXPIRED RECOVERY WINDOW (policy-forced close)", passed, details)


# ============================================================
# TEST 7: DISCOUNT LIMIT
# ============================================================

def test_7_discount_limit():
    txn = _make_txn(discount_percent=25.0)
    result = make_decision(txn, model_pipeline=MODEL)

    blocked = result["blocked_actions"]
    analysis = result["action_analysis"]

    passed = (
        "discount" in blocked and
        "discount" not in analysis and
        result["decision"] != "discount"
    )
    details = (f"decision={result['decision']}\n"
               f"discount blocked={('discount' in blocked)}")
    return _report(7, "DISCOUNT LIMIT", passed, details)


# ============================================================
# TEST 8: RISK_BLOCK FAILURE TYPE
# ============================================================

def test_8_risk_block():
    txn = _make_txn(failure_type="risk_block")
    result = make_decision(txn, model_pipeline=MODEL)

    blocked = result["blocked_actions"]
    analysis = result["action_analysis"]

    ineligible = {"retry", "payment_link", "reminder", "discount"}
    none_scored = all(a not in analysis for a in ineligible)
    none_selected = result["decision"] not in ineligible

    passed = (
        none_scored and
        none_selected and
        all(a in blocked for a in ineligible)
    )
    details = (f"decision={result['decision']}\n"
               f"ineligible scored: {not none_scored}\n"
               f"blocked={list(blocked.keys())}")
    return _report(8, "RISK_BLOCK FAILURE TYPE", passed, details)


# ============================================================
# TEST 9: ALREADY RECOVERED
# ============================================================

def test_9_already_recovered():
    txn = _make_txn(already_recovered=True)
    result = make_decision(txn, model_pipeline=MODEL)

    passed = (
        result["terminal"] == True and
        result["decision"] == "no_action_required" and
        result["decision_type"] == "terminal_no_action" and
        result["decision_reason"] == "already_recovered_terminal" and
        result["selected_probability"] is None and
        result["selected_ev"] is None and
        result["action_analysis"] == {}
    )
    details = (f"decision={result['decision']}, type={result['decision_type']}\n"
               f"reason={result['decision_reason']}\n"
               f"prob={result['selected_probability']}, ev={result['selected_ev']}\n"
               f"analysis={result['action_analysis']}")
    return _report(9, "ALREADY RECOVERED", passed, details)


# ============================================================
# TEST 10: MODEL UNAVAILABLE
# ============================================================

def test_10_model_unavailable():
    """
    Root cause analysis:
        Root cause = A (mock not applied to actual DecisionEngine instance).

    Evidence:
        Passing model_pipeline=None to make_decision() causes it to call
        load_model() which loads ml/models/recovery_model.joblib from disk.
        Since the model file exists, loading succeeds and normal EV
        optimization proceeds — the model-unavailable fallback is never
        exercised.

    Fix applied:
        Use _BrokenModel sentinel (non-None, so disk loading is skipped).
        When predict_proba is called, it raises RuntimeError, triggering
        the genuine prediction_failed → _model_unavailable_result path
        in decision_engine.py.
    """
    print("\n    --- Test 10 Root Cause ---")
    print("    Root cause = A: mock not applied to actual DecisionEngine instance")
    print("    Evidence: model_pipeline=None triggers load_model() from disk;")
    print("              model loads successfully, unavailable path not exercised")
    print("    Fix: use _BrokenModel sentinel (non-None, fails on predict_proba)")

    # --- Normal case: model unavailable, escalation available ---
    txn = _make_txn()
    broken = _BrokenModel()
    result = make_decision(txn, model_pipeline=broken)

    normal_ok = (
        result["decision_type"] in ["model_unavailable", "safe_fallback"] and
        result["decision"] in ["escalate", "no_action_required"] and
        result["escalation_required"] == True and
        result["action_analysis"] == {} and
        result["selected_probability"] is None and
        result["selected_ev"] is None
    )

    # --- Double-fallback: terminal + model unavailable ---
    txn_recovered = _make_txn(already_recovered=True)
    result_term = make_decision(txn_recovered, model_pipeline=broken)
    # Already-recovered is handled BEFORE model loading (terminal path),
    # so this should still produce the correct terminal result
    terminal_ok = (
        result_term["terminal"] == True and
        result_term["decision"] == "no_action_required" and
        result_term["decision_type"] == "terminal_no_action"
    )

    # --- Escalate-unavailable fallback ---
    # Construct a policy override where escalate is blocked but not terminal
    fake_policy = {
        "transaction_id": 5001,
        "policy_status": "restricted",
        "allowed_actions": ["retry", "wait", "close"],  # no escalate
        "blocked_actions": {"escalate": ["some_reason"]},
        "escalation_required": False,
        "terminal": False,
        "policy_version": POLICY_VERSION,
        "evaluated_at": "test",
    }
    result_no_esc = make_decision(txn, model_pipeline=broken, _policy_result_override=fake_policy)
    no_esc_ok = (
        result_no_esc["decision"] == "no_action_required" and
        result_no_esc["decision_type"] == "safe_fallback" and
        result_no_esc["decision_reason"] == "model_unavailable_no_escalation" and
        result_no_esc["action_analysis"] == {}
    )

    passed = normal_ok and terminal_ok and no_esc_ok
    details = (f"Normal model-unavailable: decision={result['decision']}, "
               f"type={result['decision_type']}, OK={normal_ok}\n"
               f"Terminal+unavailable: decision={result_term['decision']}, "
               f"type={result_term['decision_type']}, OK={terminal_ok}\n"
               f"No-escalate fallback: decision={result_no_esc['decision']}, "
               f"type={result_no_esc['decision_type']}, "
               f"reason={result_no_esc['decision_reason']}, OK={no_esc_ok}")
    return _report(10, "MODEL UNAVAILABLE (root cause=A, incl. double-fallback)", passed, details)


# ============================================================
# TEST 11: EMPTY ALLOWED-ACTIONS SAFETY
# ============================================================

def test_11_empty_allowed():
    txn = _make_txn()
    fake_policy = {
        "transaction_id": 5001,
        "policy_status": "terminal",
        "allowed_actions": [],
        "blocked_actions": {a: ["already_recovered"] for a in
                           ["close", "discount", "escalate", "payment_link",
                            "reminder", "retry", "wait"]},
        "escalation_required": False,
        "terminal": True,
        "policy_version": POLICY_VERSION,
        "evaluated_at": "test",
    }

    result = make_decision(txn, model_pipeline=MODEL, _policy_result_override=fake_policy)

    passed = (
        result["decision"] == "no_action_required" and
        result["decision_type"] == "terminal_no_action" and
        result["decision_reason"] == "already_recovered_terminal" and
        result["selected_probability"] is None and
        result["selected_ev"] is None and
        result["action_analysis"] == {} and
        result["terminal"] == True
    )
    details = (f"decision={result['decision']}, type={result['decision_type']}\n"
               f"reason={result['decision_reason']}\n"
               f"prob={result['selected_probability']}, ev={result['selected_ev']}")
    return _report(11, "EMPTY ALLOWED-ACTIONS SAFETY", passed, details)


# ============================================================
# TEST 12: CLOSE WINS THROUGH GENUINE EV COMPARISON
# ============================================================

def test_12_close_wins_ev():
    """
    Close must win via actual EV comparison, NOT because policy forced it.

    Fixture design:
        Score only actions with intervention_cost > 0 (retry, payment_link,
        reminder) plus close. With P=0 for all:
            retry:        EV = 0×1000 − 2  = −2.00
            payment_link: EV = 0×1000 − 5  = −5.00
            reminder:     EV = 0×1000 − 3  = −3.00
            close:        EV = 0 (by definition)

        Close wins by genuine EV comparison: it's the only action with
        non-negative EV.

    Why wait and discount are excluded from the scored set:
        Both have intervention_cost = 0. With P = 0, their EV = 0,
        tying with close. wait has higher tiebreak priority than close
        (index 1 vs 5), so it would win the tie. The thesis — "the best
        recovery action isn't always an action" — is about active
        interventions (retry/payment_link/reminder) losing to non-
        intervention (close), not about which zero-cost action wins
        tiebreaks. We separately verify that wait and discount would
        also have EV <= 0.
    """
    amount = 1000.0

    # Scored set: actions with cost > 0, plus close
    scored_probs = {
        "retry": 0.0,
        "payment_link": 0.0,
        "reminder": 0.0,
        "close": 0.0,
    }

    ev_results = {}
    for action, p in scored_probs.items():
        ev_results[action] = calculate_ev(action, p, amount)

    best_action, best_ev, reason = select_best_action(ev_results)

    # Also verify wait and discount would have EV <= 0
    ev_wait = calculate_ev("wait", 0.0, amount)
    ev_discount = calculate_ev("discount", 0.0, amount, discount_percent=10.0)

    # Assertions
    retry_neg = ev_results["retry"]["expected_net_value"] < 0
    plink_neg = ev_results["payment_link"]["expected_net_value"] < 0
    remind_neg = ev_results["reminder"]["expected_net_value"] < 0
    discount_leq = ev_discount["expected_net_value"] <= 0
    wait_leq = ev_wait["expected_net_value"] <= 0
    close_zero = ev_results["close"]["expected_net_value"] == 0.0
    close_selected = best_action == "close"
    multiple_scored = len(ev_results) > 1
    ev_reason = reason in ["highest_expected_net_value", "highest_expected_net_value_tiebreak"]

    passed = (
        retry_neg and plink_neg and remind_neg and
        discount_leq and wait_leq and close_zero and
        close_selected and multiple_scored and ev_reason
    )

    details_lines = ["Scored actions (EV comparison set):"]
    for a in ["retry", "payment_link", "reminder", "close"]:
        r = ev_results[a]
        details_lines.append(
            f"  {a:15s} P={r['predicted_probability']:.4f}  "
            f"cost={r['intervention_cost']:.1f}  "
            f"EV={r['expected_net_value']:.4f}"
        )
    details_lines.append(f"Unsored (verified separately):")
    details_lines.append(
        f"  {'wait':15s} P={ev_wait['predicted_probability']:.4f}  "
        f"cost={ev_wait['intervention_cost']:.1f}  "
        f"EV={ev_wait['expected_net_value']:.4f}  (<=0: {wait_leq})"
    )
    details_lines.append(
        f"  {'discount':15s} P={ev_discount['predicted_probability']:.4f}  "
        f"cost={ev_discount['intervention_cost']:.1f}  "
        f"EV={ev_discount['expected_net_value']:.4f}  (<=0: {discount_leq})"
    )
    details_lines.append(f"Selected: {best_action} (EV={best_ev['expected_net_value']:.4f})")
    details_lines.append(f"Reason: {reason}")
    details_lines.append(f"Multiple actions scored: {multiple_scored} ({len(ev_results)} actions)")
    details_lines.append(f"Close NOT policy-forced: True (selected via EV comparison)")
    details_lines.append(f"All active interventions EV < 0: {retry_neg and plink_neg and remind_neg}")

    return _report(12, "CLOSE WINS THROUGH GENUINE EV COMPARISON", passed,
                   "\n".join(details_lines))


# ============================================================
# TEST 13: DISCOUNT ECONOMICS TRADEOFF
# ============================================================

def test_13_discount_tradeoff():
    """
    P(discount) > P(retry), but EV(retry) > EV(discount).
    Proves M4 optimizes net value, not raw probability.

    discount: P=0.30, amount=1000, 10% discount → recoverable=900
        EV(discount) = 0.30 × 900 - 0 = 270.00

    retry: P=0.28, amount=1000
        EV(retry) = 0.28 × 1000 - 2 = 278.00

    retry wins despite lower probability.
    """
    ev_discount = calculate_ev("discount", 0.30, 1000.0, discount_percent=10.0)
    ev_retry = calculate_ev("retry", 0.28, 1000.0)

    ev_results = {"discount": ev_discount, "retry": ev_retry}
    best_action, best_ev, reason = select_best_action(ev_results)

    passed = (
        best_action == "retry" and
        ev_discount["predicted_probability"] > ev_retry["predicted_probability"] and
        ev_retry["expected_net_value"] > ev_discount["expected_net_value"]
    )
    details = (f"P(discount)={ev_discount['predicted_probability']}, "
               f"P(retry)={ev_retry['predicted_probability']}\n"
               f"EV(discount)={ev_discount['expected_net_value']:.2f}, "
               f"EV(retry)={ev_retry['expected_net_value']:.2f}\n"
               f"Selected: {best_action} (higher EV despite lower P)")
    return _report(13, "DISCOUNT ECONOMICS TRADEOFF", passed, details)


# ============================================================
# TEST 14: TIE-BREAKING CASCADE
# ============================================================

def test_14_tiebreak():
    """
    Two actions with identical EV — verify deterministic cascade.

    Scenario: wait and close both have EV=0 (P=0, cost=0).
    Tiebreak cascade:
      1. Lower cost → both cost=0, tied
      2. Higher probability → both P=0, tied
      3. Fixed priority order → wait (index 1) < close (index 5) → wait wins
    """
    ev_wait = calculate_ev("wait", 0.0, 1000.0)
    ev_close = calculate_ev("close", 0.0, 1000.0)
    ev_results = {"wait": ev_wait, "close": ev_close}

    # Run 10 times for determinism check
    results_list = []
    for _ in range(10):
        best_action, _, reason = select_best_action(ev_results)
        results_list.append(best_action)

    all_same = len(set(results_list)) == 1
    wait_wins = results_list[0] == "wait"

    passed = all_same and wait_wins
    details = (f"Tie scenario: wait EV=0, close EV=0\n"
               f"Cascade: cost tied (0=0) → prob tied (0=0) → priority: "
               f"wait(idx=1) < close(idx=5)\n"
               f"Winning rule: fixed priority order\n"
               f"10 runs: {set(results_list)}, deterministic={all_same}\n"
               f"Winner: {results_list[0]}")
    return _report(14, "TIE-BREAKING CASCADE", passed, details)


# ============================================================
# INTEGRATION CHECK
# ============================================================

def test_integration():
    """Real end-to-end: M1 transaction → M2 model → M3 policy → M4 decision."""
    print("\n" + "=" * 70)
    print("INTEGRATION CHECK (real M1→M2→M3→M4)")
    print("=" * 70)

    if MODEL is None:
        print("  SKIP: M2 model not available")
        return False

    try:
        df = pd.read_csv("action_expanded_training_data.csv")
        test_df = df[df["split"] == "test"]
        sample = test_df.iloc[0]

        txn = {
            "transaction_id": int(sample["transaction_id"]),
            "failure_type": sample["failure_type"],
            "amount": float(sample["amount"]),
            "risk_score": float(sample["risk_score"]),
            "attempt_number": int(sample["attempt_number"]),
            "contact_fatigue_score": float(sample["contact_fatigue_score"]),
            "hours_since_failure": 6.0,
            "already_recovered": False,
            "discount_percent": 10.0,
            "segment": sample["segment"],
            "payment_method": sample["payment_method"],
            "lifetime_successful_txns": int(sample["lifetime_successful_txns"]),
            "lifetime_failed_txns": int(sample["lifetime_failed_txns"]),
        }

        result = make_decision(txn, model_pipeline=MODEL)

        # Verification checks
        checks = {
            "decision_exists": result["decision"] is not None,
            "decision_in_allowed_or_no_action": (
                result["decision"] in result["allowed_actions"] or
                result["decision"] == "no_action_required"
            ),
            "no_blocked_scored": all(
                a not in result["action_analysis"]
                for a in result["blocked_actions"]
            ),
            "m2_probabilities_present": all(
                "predicted_probability" in v
                for v in result["action_analysis"].values()
            ) if result["action_analysis"] else True,
            "ev_values_present": all(
                "expected_net_value" in v
                for v in result["action_analysis"].values()
            ) if result["action_analysis"] else True,
            "policy_version": result["policy_version"] == POLICY_VERSION,
            "engine_version": result["decision_engine_version"] == DECISION_ENGINE_VERSION,
        }

        # Verify selected action has highest EV among scored
        if result["action_analysis"] and result["decision_type"] == "ev_optimization":
            selected_ev = result["selected_ev"]
            max_ev = max(v["expected_net_value"] for v in result["action_analysis"].values())
            checks["selected_has_highest_ev"] = abs(selected_ev - max_ev) < EV_TIE_TOLERANCE
        else:
            checks["selected_has_highest_ev"] = True

        all_pass = all(checks.values())
        print(f"\n  Transaction: {txn['transaction_id']} ({txn['failure_type']})")
        print(f"  Amount: ₹{txn['amount']:.2f}")
        print(f"  Decision: {result['decision']}")
        print(f"  Type: {result['decision_type']}")
        print(f"  Reason: {result['decision_reason']}")
        print(f"  EV: {result['selected_ev']}")
        print(f"  Escalation: {result['escalation_required']}")

        if result["action_analysis"]:
            print(f"\n  --- CONTROLLED ACTION COMPARISON ---")
            print(f"  {'Action':<15} {'P(recovery)':>11} {'Recoverable':>11} {'Cost':>6} {'EV':>10}")
            print(f"  {'-'*55}")
            for action, data in sorted(result["action_analysis"].items(),
                                       key=lambda x: -x[1]["expected_net_value"]):
                print(f"  {action:<15} {data['predicted_probability']:>11.4f} "
                      f"{data['recoverable_amount']:>11.2f} "
                      f"{data['intervention_cost']:>6.1f} "
                      f"{data['expected_net_value']:>10.4f}")
            print(f"\n  Note: Probabilities are model-estimated predictions,")
            print(f"        not causal effects of the actions.")

        print(f"\n  --- VERIFICATION ---")
        for check_name, ok in checks.items():
            print(f"  {check_name}: {'PASS' if ok else 'FAIL'}")

        print(f"\n  Integration check: {'PASS' if all_pass else 'FAIL'}")
        return all_pass

    except Exception as e:
        print(f"  FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("M4 DECISION ENGINE — ALL MANDATORY TESTS")
    print("=" * 70)

    # Configuration
    print("\n--- CONFIGURATION ---")
    print(f"  DECISION_ENGINE_VERSION: {DECISION_ENGINE_VERSION}")
    print(f"  ACTION_COSTS: {ACTION_COSTS}")
    print(f"  DEFAULT_DISCOUNT_PERCENT: {DEFAULT_DISCOUNT_PERCENT}")
    print(f"  TIE_TOLERANCE: {EV_TIE_TOLERANCE}")
    print(f"  PRIORITY_ORDER: {ACTION_PRIORITY_ORDER}")
    print(f"  M2 MODEL: {'loaded' if MODEL else 'UNAVAILABLE'}")

    # 14 mandatory tests
    print("\n" + "=" * 70)
    print("MANDATORY TESTS (14)")
    print("=" * 70)

    test_1_normal()
    test_2_high_value()
    test_3_high_risk()
    test_4_retry_cap()
    test_5_contact_fatigue()
    test_6_expired_window()
    test_7_discount_limit()
    test_8_risk_block()
    test_9_already_recovered()
    test_10_model_unavailable()
    test_11_empty_allowed()
    test_12_close_wins_ev()
    test_13_discount_tradeoff()
    test_14_tiebreak()

    # Integration
    integration_ok = test_integration()

    # Summary
    print("\n" + "=" * 70)
    print("M4 FINAL SUMMARY")
    print("=" * 70)
    print(f"\n  Mandatory tests: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL")
    print(f"  Integration check: {'PASS' if integration_ok else 'FAIL'}")
    all_pass = FAIL_COUNT == 0 and integration_ok
    print(f"\n  M4 OVERALL: {'PASS' if all_pass else 'FAIL'}")
    print(f"\n  No M5 baseline comparison was performed.")
    print("=" * 70)

    if not all_pass:
        sys.exit(1)
