"""
M5 Step 0: Blocking pre-check — inspect M1 data before experiment.
"""
import pandas as pd
import sys

print("=" * 70)
print("M5 STEP 0: BLOCKING PRE-CHECK")
print("=" * 70)

# Load data
ht = pd.read_csv("action_expanded_with_hidden_truth.csv")
tr = pd.read_csv("action_expanded_training_data.csv")

print(f"\nHidden truth file: {ht.shape[0]} rows, {ht.shape[1]} columns")
print(f"Training data file: {tr.shape[0]} rows, {tr.shape[1]} columns")

# ============================================================
# a) Actions with realized outcomes
# ============================================================
print("\n" + "=" * 70)
print("a) ACTIONS WITH REALIZED OUTCOMES")
print("=" * 70)
actions_in_ht = sorted(ht["action"].unique())
print(f"Actions present: {actions_in_ht}")
print(f"Count: {len(actions_in_ht)}")
for a in actions_in_ht:
    subset = ht[ht["action"] == a]
    outcomes = subset["outcome"].value_counts()
    print(f"  {a:20s} — {len(subset)} rows, outcome dist: "
          f"0={outcomes.get(0, 0)}, 1={outcomes.get(1, 0)}")

# ============================================================
# b) Does "escalate" have a realized outcome?
# ============================================================
print("\n" + "=" * 70)
print("b) ESCALATE OUTCOME CHECK")
print("=" * 70)
has_escalate = "escalate" in actions_in_ht
print(f"'escalate' in hidden truth actions: {has_escalate}")
if has_escalate:
    esc = ht[ht["action"] == "escalate"]
    print(f"  escalate rows: {len(esc)}")
    print(f"  escalate outcomes: {esc['outcome'].value_counts().to_dict()}")
else:
    print("  escalate has NO realized outcome in hidden truth data.")
    print("  M3 introduced 'escalate' as a policy action, but M1's")
    print("  eligibility matrix never generated an outcome for it.")
    print()
    print("  Proposed convention:")
    print("    Option 1 (recommended headline): escalated transactions")
    print("      counted as not-recovered (conservative; understates both)")
    print("    Option 2 (supplementary): escalated transactions reported")
    print("      separately and excluded from primary denominator")
    print("  Recommend: report BOTH, with Option 1 as headline.")

# ============================================================
# c) Failure types present
# ============================================================
print("\n" + "=" * 70)
print("c) FAILURE TYPES PRESENT")
print("=" * 70)
failure_types = sorted(ht["failure_type"].unique())
print(f"Failure types ({len(failure_types)}): {failure_types}")
for ft in failure_types:
    count = len(ht[ht["failure_type"] == ft])
    txn_count = ht[ht["failure_type"] == ft]["transaction_id"].nunique()
    print(f"  {ft:30s} — {count} rows, {txn_count} unique transactions")

# Check against M1 eligibility
from ml.policy.eligibility import ELIGIBILITY
elig_fts = set(ELIGIBILITY.keys())
data_fts = set(failure_types)
print(f"\nEligibility matrix failure types: {sorted(elig_fts)}")
print(f"Data failure types:               {sorted(data_fts)}")
if elig_fts == data_fts:
    print("MATCH: all failure types align")
else:
    print(f"MISMATCH: in eligibility only: {elig_fts - data_fts}")
    print(f"MISMATCH: in data only: {data_fts - elig_fts}")

# ============================================================
# d) Test transaction count + coverage
# ============================================================
print("\n" + "=" * 70)
print("d) TEST TRANSACTION COUNT AND COVERAGE")
print("=" * 70)

test_ht = ht[ht["split"] == "test"]
test_txn_ids = sorted(test_ht["transaction_id"].unique())
print(f"Test transactions in hidden truth: {len(test_txn_ids)}")

test_tr = tr[tr["split"] == "test"]
test_txn_ids_tr = sorted(test_tr["transaction_id"].unique())
print(f"Test transactions in training data: {len(test_txn_ids_tr)}")
print(f"Transaction ID sets match: {set(test_txn_ids) == set(test_txn_ids_tr)}")

# Check coverage: for each test transaction, which actions have outcomes?
missing_pairs = []
for txn_id in test_txn_ids:
    txn_rows = test_ht[test_ht["transaction_id"] == txn_id]
    ft = txn_rows["failure_type"].iloc[0]
    eligible = ELIGIBILITY.get(ft, set())
    actions_present = set(txn_rows["action"].unique())
    # Only check non-escalate actions (since escalate may not have outcomes)
    eligible_non_esc = eligible - {"escalate"}
    missing = eligible_non_esc - actions_present
    if missing:
        missing_pairs.append((txn_id, ft, missing))

print(f"Missing (transaction, action) pairs: {len(missing_pairs)}")
if missing_pairs:
    for txn_id, ft, missing in missing_pairs[:5]:
        print(f"  txn={txn_id}, failure_type={ft}, missing={missing}")
    if len(missing_pairs) > 5:
        print(f"  ... and {len(missing_pairs) - 5} more")
else:
    print("  Every (test transaction × eligible non-escalate action) pair has a realized outcome.")

# ============================================================
# e) Single decision vs multi-step episode
# ============================================================
print("\n" + "=" * 70)
print("e) SINGLE DECISION vs MULTI-STEP EPISODE")
print("=" * 70)

# Check attempt_number distribution
attempt_dist = ht["attempt_number"].value_counts().sort_index()
print("attempt_number distribution (all data):")
for att, cnt in attempt_dist.items():
    txn_cnt = ht[ht["attempt_number"] == att]["transaction_id"].nunique()
    print(f"  attempt_number={att}: {cnt} rows, {txn_cnt} unique transactions")

# Check if any transaction appears with multiple attempt_numbers
txn_attempts = ht.groupby("transaction_id")["attempt_number"].nunique()
multi_attempt_txns = txn_attempts[txn_attempts > 1]
print(f"\nTransactions with multiple attempt_numbers: {len(multi_attempt_txns)}")

if len(multi_attempt_txns) == 0:
    print("  Each transaction has exactly ONE attempt_number.")
    print("  -> Each transaction is ONE decision point.")
    print("  -> attempt_number is a FIELD (context), not a step counter.")
    print("  -> Single-decision semantics confirmed.")
    print("  -> The baseline's position in its sequence is READ from")
    print("     attempt_number, not simulated.")
else:
    print(f"  WARNING: {len(multi_attempt_txns)} transactions have multiple attempt_numbers!")
    print("  This would indicate multi-step episodes. STOP and report.")

print("\n" + "=" * 70)
print("STEP 0 COMPLETE — AWAITING APPROVAL")
print("=" * 70)
