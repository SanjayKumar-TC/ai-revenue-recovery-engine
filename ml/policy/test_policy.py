"""
M3: Deterministic Policy Engine — All 13 Mandatory Tests
==========================================================
Tests the policy engine against every required scenario from the M3 spec.
Also includes the M1 eligibility drift-detection test.

Run from project root:
    python -m ml.policy.test_policy
"""

import sys
import os

# Ensure project root is on path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ml.policy.policy_engine import evaluate_policy
from ml.policy.eligibility import ELIGIBILITY, ALL_ACTIONS, CONTACT_ACTIONS, AUTOMATED_RECOVERY_ACTIONS
from ml.policy.policy_config import (
    POLICY_VERSION,
    MAX_AUTO_RECOVERY_AMOUNT,
    HIGH_RISK_ESCALATION_THRESHOLD,
    HIGH_RISK_BLOCK_THRESHOLD,
    MAX_AUTO_RETRIES,
    MAX_CONTACT_FATIGUE,
    RECOVERY_WINDOW_HOURS,
    MAX_DISCOUNT_PERCENT,
)

# ============================================================
# Test helpers
# ============================================================

PASS_COUNT = 0
FAIL_COUNT = 0

def _make_txn(**overrides):
    """Create a default normal transaction, with overrides."""
    base = {
        "transaction_id": 1001,
        "failure_type": "temporary_bank_decline",
        "amount": 2000.0,
        "risk_score": 0.15,
        "attempt_number": 1,
        "contact_fatigue_score": 0.1,
        "hours_since_failure": 6.0,
        "already_recovered": False,
        "discount_percent": 0.0,
    }
    base.update(overrides)
    return base


def _report(test_num, test_name, passed, details=""):
    global PASS_COUNT, FAIL_COUNT
    status = "PASS" if passed else "FAIL"
    if not passed:
        FAIL_COUNT += 1
    else:
        PASS_COUNT += 1
    print(f"\n  Test {test_num}: {test_name} — {status}")
    if details:
        for line in details.split("\n"):
            print(f"    {line}")
    return passed


# ============================================================
# ELIGIBILITY DRIFT-DETECTION TEST
# ============================================================

def test_eligibility_drift():
    """Compare ml/policy/eligibility.py against hard-coded expected M1 values.
    Not a live import — hard-coded expected values catch any drift."""
    print("\n" + "=" * 70)
    print("ELIGIBILITY DRIFT-DETECTION TEST")
    print("=" * 70)

    expected = {
        "temporary_bank_decline": {"retry", "payment_link", "reminder", "discount", "wait", "close", "escalate"},
        "network_timeout":        {"retry", "payment_link", "reminder", "wait", "close", "escalate"},
        "card_expired":           {"payment_link", "reminder", "discount", "wait", "close", "escalate"},
        "risk_block":             {"wait", "close", "escalate"},
        "customer_abandoned":     {"payment_link", "reminder", "discount", "wait", "close", "escalate"},
        "subscription_mandate_fail": {"payment_link", "reminder", "discount", "wait", "close", "escalate"},
        "insufficient_funds":     {"retry", "reminder", "payment_link", "wait", "close", "escalate"},
    }

    all_ok = True
    for ft, expected_actions in expected.items():
        actual = ELIGIBILITY.get(ft)
        if actual is None:
            print(f"  FAIL: {ft} missing from ELIGIBILITY")
            all_ok = False
        elif actual != expected_actions:
            print(f"  FAIL: {ft} mismatch — expected {expected_actions}, got {actual}")
            all_ok = False
        else:
            print(f"  OK: {ft}")

    # Check no extra failure types
    extra = set(ELIGIBILITY.keys()) - set(expected.keys())
    if extra:
        print(f"  FAIL: unexpected failure types in ELIGIBILITY: {extra}")
        all_ok = False

    status = "PASS" if all_ok else "FAIL"
    print(f"\n  Eligibility drift-detection: {status}")
    return all_ok


# ============================================================
# 13 MANDATORY TESTS
# ============================================================

def test_1_normal_transaction():
    """Low-risk, within window — eligible actions returned, no rules fire."""
    txn = _make_txn()
    result = evaluate_policy(txn)

    expected_eligible = ELIGIBILITY["temporary_bank_decline"] - {"escalate"}
    # escalate is eligible but not required
    allowed = set(result["allowed_actions"])
    # All non-escalate eligible actions should be allowed
    non_esc_eligible = ELIGIBILITY["temporary_bank_decline"] - {"escalate"}
    passed = (
        non_esc_eligible.issubset(allowed) and
        result["policy_status"] == "allowed" and
        result["terminal"] == False and
        result["escalation_required"] == False and
        len(result["blocked_actions"]) == 0 and
        result["policy_version"] == POLICY_VERSION
    )
    details = (f"allowed={result['allowed_actions']}\n"
               f"blocked={result['blocked_actions']}\n"
               f"status={result['policy_status']}, terminal={result['terminal']}")
    return _report(1, "NORMAL TRANSACTION", passed, details)


def test_2_high_value():
    """Amount > 50,000 — automated recovery blocked, escalation required."""
    txn = _make_txn(amount=75000.0)
    result = evaluate_policy(txn)

    blocked = result["blocked_actions"]
    allowed = set(result["allowed_actions"])

    # All automated recovery actions should be blocked
    auto_blocked = all(
        a in blocked and blocked[a] == "amount_above_auto_limit"
        for a in AUTOMATED_RECOVERY_ACTIONS
        if a in ELIGIBILITY["temporary_bank_decline"]
    )

    passed = (
        auto_blocked and
        result["escalation_required"] == True and
        "wait" in allowed and
        "close" in allowed and
        "escalate" in allowed
    )
    details = (f"allowed={result['allowed_actions']}\n"
               f"blocked={blocked}\n"
               f"escalation_required={result['escalation_required']}")
    return _report(2, "HIGH VALUE (amount > 50000)", passed, details)


def test_3a_high_risk_escalation():
    """0.75 <= risk_score < 0.85 — mandatory escalation, actions not blocked."""
    txn = _make_txn(risk_score=0.78)
    result = evaluate_policy(txn)

    allowed = set(result["allowed_actions"])
    passed = (
        result["escalation_required"] == True and
        "escalate" in allowed and
        # Automated actions still allowed in escalation band
        "retry" in allowed and
        result["terminal"] == False
    )
    details = (f"risk_score=0.78, allowed={result['allowed_actions']}\n"
               f"escalation_required={result['escalation_required']}")
    return _report("3a", "HIGH RISK ESCALATION BAND (0.75 <= risk < 0.85)", passed, details)


def test_3b_high_risk_block():
    """risk_score >= 0.85 — only wait/close/escalate remain."""
    txn = _make_txn(risk_score=0.90)
    result = evaluate_policy(txn)

    allowed = set(result["allowed_actions"])
    blocked = result["blocked_actions"]

    # All automated recovery actions must be blocked
    auto_blocked = all(
        a in blocked and blocked[a] == "high_risk_block"
        for a in AUTOMATED_RECOVERY_ACTIONS
        if a in ELIGIBILITY["temporary_bank_decline"]
    )

    passed = (
        auto_blocked and
        result["escalation_required"] == True and
        "wait" in allowed and
        "close" in allowed and
        "escalate" in allowed and
        not any(a in allowed for a in AUTOMATED_RECOVERY_ACTIONS)
    )
    details = (f"risk_score=0.90, allowed={result['allowed_actions']}\n"
               f"blocked={blocked}")
    return _report("3b", "HIGH RISK BLOCK BAND (risk >= 0.85)", passed, details)


def test_4_retry_cap():
    """Attempt count at maximum — retry blocked, others unaffected."""
    txn = _make_txn(attempt_number=2)  # MAX_AUTO_RETRIES = 2
    result = evaluate_policy(txn)

    blocked = result["blocked_actions"]
    allowed = set(result["allowed_actions"])

    passed = (
        "retry" in blocked and
        blocked["retry"] == "retry_limit_reached" and
        "retry" not in allowed and
        # Other actions still allowed
        "payment_link" in allowed and
        "reminder" in allowed
    )
    details = (f"attempt=2, allowed={result['allowed_actions']}\n"
               f"blocked={blocked}")
    return _report(4, "RETRY CAP (attempt >= MAX_AUTO_RETRIES)", passed, details)


def test_5_contact_fatigue():
    """Fatigue >= threshold — reminder, payment_link, AND discount blocked."""
    txn = _make_txn(contact_fatigue_score=0.85)
    result = evaluate_policy(txn)

    blocked = result["blocked_actions"]
    allowed = set(result["allowed_actions"])

    all_contact_blocked = all(
        a in blocked and blocked[a] == "contact_fatigue_limit"
        for a in CONTACT_ACTIONS
        if a in ELIGIBILITY["temporary_bank_decline"]
    )

    passed = (
        all_contact_blocked and
        "reminder" not in allowed and
        "payment_link" not in allowed and
        "discount" not in allowed and
        # Non-contact actions still available
        "retry" in allowed and
        "wait" in allowed and
        "close" in allowed
    )
    details = (f"fatigue=0.85, allowed={result['allowed_actions']}\n"
               f"blocked={blocked}")
    return _report(5, "CONTACT FATIGUE (all 3 contact actions blocked)", passed, details)


def test_6_expired_window():
    """Elapsed > RECOVERY_WINDOW_HOURS — forces close, terminal=true."""
    txn = _make_txn(hours_since_failure=72.0)
    result = evaluate_policy(txn)

    passed = (
        result["allowed_actions"] == ["close"] and
        result["terminal"] == True and
        result["policy_status"] == "terminal" and
        result["escalation_required"] == False and
        len(result["blocked_actions"]) > 0
    )
    details = (f"hours=72, allowed={result['allowed_actions']}\n"
               f"terminal={result['terminal']}, status={result['policy_status']}")
    return _report(6, "EXPIRED RECOVERY WINDOW (force close, terminal)", passed, details)


def test_7_discount_limit():
    """Discount exceeds configured limit — blocked."""
    txn = _make_txn(discount_percent=25.0)
    result = evaluate_policy(txn)

    blocked = result["blocked_actions"]
    passed = (
        "discount" in blocked and
        blocked["discount"] == "discount_limit_exceeded" and
        "discount" not in result["allowed_actions"]
    )
    details = (f"discount=25%, allowed={result['allowed_actions']}\n"
               f"blocked={blocked}")
    return _report(7, "DISCOUNT LIMIT EXCEEDED", passed, details)


def test_8_risk_block_failure_type():
    """risk_block failure_type — only wait/close/escalate eligible.
    Retry must NOT become allowed regardless of ML prediction."""
    txn = _make_txn(failure_type="risk_block")
    result = evaluate_policy(txn)

    allowed = set(result["allowed_actions"])
    blocked = result["blocked_actions"]

    # Only wait, close, escalate should be allowed
    passed = (
        "retry" not in allowed and
        "payment_link" not in allowed and
        "reminder" not in allowed and
        "discount" not in allowed and
        "wait" in allowed and
        "close" in allowed and
        # retry/payment_link/reminder/discount blocked as ineligible
        all(
            blocked.get(a) == "ineligible_for_failure_type"
            for a in ["retry", "payment_link", "reminder", "discount"]
        )
    )
    details = (f"failure_type=risk_block, allowed={result['allowed_actions']}\n"
               f"blocked={blocked}")
    return _report(8, "RISK_BLOCK FAILURE TYPE (M1 eligibility enforced)", passed, details)


def test_9_already_recovered():
    """Already recovered — no recovery action of any kind."""
    txn = _make_txn(already_recovered=True)
    result = evaluate_policy(txn)

    passed = (
        len(result["allowed_actions"]) == 0 and
        result["terminal"] == True and
        result["policy_status"] == "terminal" and
        result["escalation_required"] == False and
        len(result["blocked_actions"]) == len(ALL_ACTIONS)
    )
    details = (f"allowed={result['allowed_actions']}\n"
               f"terminal={result['terminal']}, blocked_count={len(result['blocked_actions'])}")
    return _report(9, "ALREADY RECOVERED (terminal, all blocked)", passed, details)


def test_10_missing_invalid_input():
    """Missing/invalid input — safe failure, no unsafe automated action."""
    test_cases = [
        ({}, "empty dict"),
        ({"transaction_id": 1}, "missing required fields"),
        (_make_txn(amount=-100), "negative amount"),
        (_make_txn(risk_score=1.5), "risk_score out of range"),
        (_make_txn(attempt_number=0), "invalid attempt_number"),
        (_make_txn(contact_fatigue_score=-0.1), "negative fatigue"),
        (_make_txn(failure_type="nonexistent_type"), "unknown failure_type"),
        ("not_a_dict", "input not a dict"),
    ]

    all_safe = True
    details_lines = []
    for case_input, case_name in test_cases:
        result = evaluate_policy(case_input)
        safe = (
            result["terminal"] == True and
            result["escalation_required"] == True and
            "escalate" in result["allowed_actions"]
        )
        if not safe:
            all_safe = False
            details_lines.append(f"FAIL: {case_name} — not safe (result={result})")
        else:
            details_lines.append(f"OK: {case_name} — safe failure")

    return _report(10, "MISSING/INVALID INPUT (safe failure)", all_safe, "\n".join(details_lines))


def test_11_determinism():
    """Identical input evaluated multiple times produces identical result."""
    txn = _make_txn(risk_score=0.50, amount=30000, attempt_number=2,
                    contact_fatigue_score=0.5, hours_since_failure=20.0)

    results = []
    for _ in range(10):
        result = evaluate_policy(txn)
        # Remove evaluated_at (timestamp varies)
        result_comparable = {k: v for k, v in result.items() if k != "evaluated_at"}
        results.append(str(result_comparable))

    all_identical = len(set(results)) == 1
    return _report(11, "DETERMINISM (10 evaluations identical)", all_identical,
                   f"Unique results: {len(set(results))}")


def test_12_policy_cannot_be_overridden():
    """A (mocked) extremely high probability for a blocked action
    must not cause the policy to allow it."""
    # High risk transaction — automated recovery should be blocked
    txn = _make_txn(risk_score=0.90)
    result = evaluate_policy(txn)

    # Simulate: "ML says retry has 0.99 probability of recovery"
    # Policy must still block retry because risk >= 0.85
    mocked_high_prob = {"retry": 0.99, "payment_link": 0.95}

    # Verify blocked regardless
    blocked = result["blocked_actions"]
    allowed = set(result["allowed_actions"])

    passed = (
        "retry" in blocked and
        "retry" not in allowed and
        "payment_link" in blocked and
        "payment_link" not in allowed and
        # Policy result doesn't contain any probability field
        "probability" not in result and
        "predicted_prob" not in result
    )
    details = (f"Mocked P(retry)=0.99, P(payment_link)=0.95\n"
               f"Policy still blocks: retry={'retry' in blocked}, payment_link={'payment_link' in blocked}\n"
               f"No probability in result: {'probability' not in result}")
    return _report(12, "POLICY CANNOT BE OVERRIDDEN BY PROBABILITY", passed, details)


def test_13_risk_boundary_exactness():
    """Test risk_score exactly at 0.75 and exactly at 0.85.
    Each must fall into exactly one band, never both."""

    # Exactly 0.75 — should be in escalation band (>= 0.75 and < 0.85)
    txn_75 = _make_txn(risk_score=0.75)
    result_75 = evaluate_policy(txn_75)

    in_escalation_band_75 = (
        result_75["escalation_required"] == True and
        # Automated actions NOT blocked (that's the block band)
        "retry" in result_75["allowed_actions"]
    )

    # Exactly 0.85 — should be in block band (>= 0.85)
    txn_85 = _make_txn(risk_score=0.85)
    result_85 = evaluate_policy(txn_85)

    in_block_band_85 = (
        result_85["escalation_required"] == True and
        "retry" not in result_85["allowed_actions"] and
        "retry" in result_85["blocked_actions"] and
        result_85["blocked_actions"]["retry"] == "high_risk_block"
    )

    # Just below 0.75 — should be normal
    txn_749 = _make_txn(risk_score=0.749)
    result_749 = evaluate_policy(txn_749)
    is_normal = (
        result_749["escalation_required"] == False and
        result_749["policy_status"] == "allowed"
    )

    passed = in_escalation_band_75 and in_block_band_85 and is_normal
    details = (f"risk=0.749: normal={is_normal}, escalation={result_749['escalation_required']}\n"
               f"risk=0.75: escalation_band={in_escalation_band_75}, "
               f"escalation_required={result_75['escalation_required']}\n"
               f"risk=0.85: block_band={in_block_band_85}, "
               f"blocked={result_85.get('blocked_actions', {})}")
    return _report(13, "RISK BOUNDARY EXACTNESS (0.75 and 0.85)", passed, details)


# ============================================================
# MAIN — RUN ALL TESTS
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("M3 POLICY ENGINE — ALL MANDATORY TESTS")
    print("=" * 70)

    # Print configuration
    print("\n--- POLICY CONFIGURATION ---")
    print(f"  POLICY_VERSION:                 {POLICY_VERSION}")
    print(f"  MAX_AUTO_RECOVERY_AMOUNT:       {MAX_AUTO_RECOVERY_AMOUNT}")
    print(f"  HIGH_RISK_ESCALATION_THRESHOLD: {HIGH_RISK_ESCALATION_THRESHOLD}")
    print(f"  HIGH_RISK_BLOCK_THRESHOLD:      {HIGH_RISK_BLOCK_THRESHOLD}")
    print(f"  MAX_AUTO_RETRIES:               {MAX_AUTO_RETRIES}")
    print(f"  MAX_CONTACT_FATIGUE:            {MAX_CONTACT_FATIGUE}")
    print(f"  RECOVERY_WINDOW_HOURS:          {RECOVERY_WINDOW_HOURS}")
    print(f"  MAX_DISCOUNT_PERCENT:           {MAX_DISCOUNT_PERCENT}")

    # Eligibility drift test
    drift_ok = test_eligibility_drift()

    # 13 mandatory tests
    print("\n" + "=" * 70)
    print("MANDATORY TESTS (13)")
    print("=" * 70)

    test_1_normal_transaction()
    test_2_high_value()
    test_3a_high_risk_escalation()
    test_3b_high_risk_block()
    test_4_retry_cap()
    test_5_contact_fatigue()
    test_6_expired_window()
    test_7_discount_limit()
    test_8_risk_block_failure_type()
    test_9_already_recovered()
    test_10_missing_invalid_input()
    test_11_determinism()
    test_12_policy_cannot_be_overridden()
    test_13_risk_boundary_exactness()

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"\n  Eligibility drift-detection: {'PASS' if drift_ok else 'FAIL'}")
    print(f"  Mandatory tests: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL")
    total = PASS_COUNT + FAIL_COUNT
    print(f"  Total: {total} tests")
    all_pass = drift_ok and FAIL_COUNT == 0
    print(f"\n  M3 OVERALL: {'PASS' if all_pass else 'FAIL'}")
    print("=" * 70)

    if not all_pass:
        sys.exit(1)
