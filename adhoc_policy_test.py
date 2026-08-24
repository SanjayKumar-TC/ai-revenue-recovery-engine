"""Ad-hoc M3 policy test: dual-rule trigger (amount ceiling + high risk block)."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ml.policy.policy_engine import evaluate_policy

txn = {
    "transaction_id": 9999,
    "failure_type": "temporary_bank_decline",
    "amount": 75000.0,
    "risk_score": 0.90,
    "attempt_number": 1,
    "contact_fatigue_score": 0.10,
    "hours_since_failure": 6.0,
    "already_recovered": False,
    "discount_percent": 0.0,
}

result = evaluate_policy(txn)

print("=" * 70)
print("AD-HOC M3 TEST: DUAL-RULE TRIGGER")
print("  amount=75000 (>50000) + risk_score=0.90 (>=0.85)")
print("=" * 70)
print(f"\n  policy_status:       {result['policy_status']}")
print(f"  terminal:            {result['terminal']}")
print(f"  escalation_required: {result['escalation_required']}")
print(f"  policy_version:      {result['policy_version']}")
print(f"\n  allowed_actions:     {result['allowed_actions']}")
print(f"\n  blocked_actions:")
for action, reasons in sorted(result['blocked_actions'].items()):
    print(f"    {action:20s} -> {reasons}")

# Verify expectations
auto_actions = {"retry", "payment_link", "reminder", "discount"}
allowed_set = set(result["allowed_actions"])
blocked = result["blocked_actions"]

checks = {
    "no automated recovery allowed": len(auto_actions & allowed_set) == 0,
    "amount_above_auto_limit recorded": any("amount_above_auto_limit" in reasons for reasons in blocked.values()),
    "high_risk_block recorded": any("high_risk_block" in reasons for reasons in blocked.values()),
    "escalation_required = true": result["escalation_required"] == True,
    "wait allowed": "wait" in allowed_set,
    "close allowed": "close" in allowed_set,
    "escalate allowed": "escalate" in allowed_set,
}

print(f"\n  --- VERIFICATION ---")
all_pass = True
for check_name, passed in checks.items():
    status = "PASS" if passed else "FAIL"
    if not passed:
        all_pass = False
    print(f"    {check_name}: {status}")

print(f"\n  OVERALL: {'PASS' if all_pass else 'FAIL'}")
print("=" * 70)
