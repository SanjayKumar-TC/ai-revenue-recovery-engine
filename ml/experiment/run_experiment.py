"""
M5: Run Experiment
===================
Single reproducible experiment comparing Policy A (M4) against all baselines.

Usage:
    python -m ml.experiment.run_experiment
"""

import os
import sys
import hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd

from ml.decision.decision_config import (
    ACTION_COSTS, DEFAULT_DISCOUNT_PERCENT, DECISION_ENGINE_VERSION,
    EV_TIE_TOLERANCE, ACTION_PRIORITY_ORDER,
)
from ml.decision.decision_engine import make_decision, load_model
from ml.policy.policy_engine import evaluate_policy
from ml.policy.policy_config import POLICY_VERSION
from ml.experiment.baseline_policy import (
    select_b0_waterfall, select_b1_random, select_constant_action,
    select_b6_oracle, BASELINE_MAX_RETRIES,
)
from ml.experiment.experiment_metrics import (
    score_action, compute_policy_metrics, paired_bootstrap,
    action_breakdown, group_breakdown,
)

# ============================================================
# Configuration
# ============================================================

BOOTSTRAP_SEED = 42
BOOTSTRAP_RESAMPLES = 10000
RANDOM_BASELINE_SEED = 123
RESULTS_DIR = os.path.join("ml", "experiment", "results")

HIDDEN_TRUTH_COLS_FORBIDDEN = {"true_prob_HIDDEN", "latent_score"}

ALL_POLICIES = [
    "policy_a", "b0_waterfall", "b1_random",
    "b2_always_retry", "b3_always_payment_link",
    "b4_always_reminder", "b5_always_discount", "b6_oracle",
]


# ============================================================
# Data Loading
# ============================================================

def load_experiment_data():
    """Load hidden truth data and build outcome lookup."""
    ht = pd.read_csv("action_expanded_with_hidden_truth.csv")
    test_ht = ht[ht["split"] == "test"].copy()

    # Build outcome lookup: (transaction_id, action) → outcome
    outcome_lookup = {}
    for _, row in test_ht.iterrows():
        key = (int(row["transaction_id"]), row["action"])
        outcome_lookup[key] = int(row["outcome"])

    # Get unique test transactions (take first row per transaction for context)
    context_cols = [
        "transaction_id", "customer_id", "segment", "customer_age_days",
        "lifetime_successful_txns", "lifetime_failed_txns", "risk_score",
        "amount", "failure_type", "payment_method", "attempt_number",
        "is_subscription", "contact_fatigue_score",
    ]
    test_txns = test_ht.drop_duplicates(subset="transaction_id")[context_cols].copy()
    test_txns = test_txns.sort_values("transaction_id").reset_index(drop=True)

    return test_txns, outcome_lookup


def build_transaction_context(row):
    """Build a transaction context dict from a DataFrame row."""
    ctx = {
        "transaction_id": int(row["transaction_id"]),
        "failure_type": row["failure_type"],
        "amount": float(row["amount"]),
        "risk_score": float(row["risk_score"]),
        "attempt_number": int(row["attempt_number"]),
        "contact_fatigue_score": float(row["contact_fatigue_score"]),
        "segment": row["segment"],
        "payment_method": row["payment_method"],
        "lifetime_successful_txns": int(row["lifetime_successful_txns"]),
        "lifetime_failed_txns": int(row["lifetime_failed_txns"]),
        # Experiment defaults — consistent across all policies
        "hours_since_failure": 6.0,
        "already_recovered": False,
        "discount_percent": DEFAULT_DISCOUNT_PERCENT,
    }
    # Assert no hidden truth columns
    for col in HIDDEN_TRUTH_COLS_FORBIDDEN:
        assert col not in ctx, f"LEAK: {col} found in transaction context"
    return ctx


# ============================================================
# Policy Evaluation
# ============================================================

def evaluate_all_policies(txn_ctx, policy_result, model_pipeline,
                          outcome_lookup, rng_b1):
    """
    Evaluate all policies for a single transaction.

    Returns dict: {policy_name: {action, source, fallback, outcome, scores...}}
    """
    txn_id = txn_ctx["transaction_id"]
    amount = txn_ctx["amount"]
    allowed = policy_result["allowed_actions"]
    escalation_required = policy_result["escalation_required"]
    terminal = policy_result["terminal"]
    attempt = txn_ctx["attempt_number"]
    dp = DEFAULT_DISCOUNT_PERCENT

    results = {}

    # --- POLICY A: M4 Decision Engine ---
    decision = make_decision(txn_ctx, model_pipeline=model_pipeline)
    pa_action = decision["decision"]
    pa_outcome = outcome_lookup.get((txn_id, pa_action), 0) if pa_action not in ("no_action_required", "escalate") else 0
    pa_scores = score_action(pa_action, pa_outcome, amount, dp)
    results["policy_a"] = {
        "action": pa_action,
        "source": decision.get("decision_reason", ""),
        "fallback_used": False,
        "escalation_required": decision.get("escalation_required", False),
        "terminal": decision.get("terminal", False),
        **pa_scores,
        "_decision_full": decision,
    }

    # --- B0: Fixed Waterfall ---
    b0_action, b0_src, b0_fb = select_b0_waterfall(
        allowed, escalation_required, terminal, attempt)
    b0_outcome = outcome_lookup.get((txn_id, b0_action), 0) if b0_action not in ("no_action_required", "escalate") else 0
    b0_scores = score_action(b0_action, b0_outcome, amount, dp)
    results["b0_waterfall"] = {
        "action": b0_action, "source": b0_src, "fallback_used": b0_fb,
        "escalation_required": escalation_required, "terminal": terminal,
        **b0_scores,
    }

    # --- B1: Random Eligible ---
    b1_action, b1_src, b1_fb = select_b1_random(
        allowed, escalation_required, terminal, rng_b1)
    b1_outcome = outcome_lookup.get((txn_id, b1_action), 0) if b1_action not in ("no_action_required", "escalate") else 0
    b1_scores = score_action(b1_action, b1_outcome, amount, dp)
    results["b1_random"] = {
        "action": b1_action, "source": b1_src, "fallback_used": b1_fb,
        "escalation_required": escalation_required, "terminal": terminal,
        **b1_scores,
    }

    # --- B2–B5: Constant-Action ---
    for label, pref in [("b2_always_retry", "retry"),
                        ("b3_always_payment_link", "payment_link"),
                        ("b4_always_reminder", "reminder"),
                        ("b5_always_discount", "discount")]:
        c_action, c_src, c_fb = select_constant_action(
            pref, allowed, escalation_required, terminal)
        c_outcome = outcome_lookup.get((txn_id, c_action), 0) if c_action not in ("no_action_required", "escalate") else 0
        c_scores = score_action(c_action, c_outcome, amount, dp)
        results[label] = {
            "action": c_action, "source": c_src, "fallback_used": c_fb,
            "escalation_required": escalation_required, "terminal": terminal,
            **c_scores,
        }

    # --- B6: Oracle ---
    b6_action, b6_src, b6_fb = select_b6_oracle(
        allowed, escalation_required, terminal,
        txn_id, amount, outcome_lookup, dp)
    b6_outcome = outcome_lookup.get((txn_id, b6_action), 0) if b6_action not in ("no_action_required", "escalate") else 0
    b6_scores = score_action(b6_action, b6_outcome, amount, dp)
    results["b6_oracle"] = {
        "action": b6_action, "source": b6_src, "fallback_used": b6_fb,
        "escalation_required": escalation_required, "terminal": terminal,
        **b6_scores,
    }

    return results


# ============================================================
# Safety Verification
# ============================================================

def verify_safety(policy_name, action, policy_result, txn_ctx):
    """Check a single policy decision against M3 constraints. Returns list of violations."""
    violations = []
    allowed = set(policy_result["allowed_actions"])
    terminal = policy_result["terminal"]

    if action == "no_action_required":
        return violations  # Valid terminal/fallback

    if action not in allowed and action != "escalate":
        violations.append(f"{policy_name}: action '{action}' not in allowed_actions")

    if terminal and action not in allowed and action != "no_action_required":
        violations.append(f"{policy_name}: non-terminal action '{action}' on terminal txn")

    return violations


# ============================================================
# Main Experiment
# ============================================================

def run_experiment():
    """Run the full M5 experiment. Returns all results for reporting."""

    print("=" * 70)
    print("M5 EXPERIMENT: BASELINE POLICIES + OFFLINE EVALUATION")
    print("=" * 70)

    # --- Print frozen M4 config ---
    print("\n--- FROZEN M4 CONFIGURATION ---")
    print(f"  ACTION_COSTS = {ACTION_COSTS}")
    print(f"  DEFAULT_DISCOUNT_PERCENT = {DEFAULT_DISCOUNT_PERCENT}")
    print(f"  TIE_TOLERANCE = {EV_TIE_TOLERANCE}")
    print(f"  PRIORITY_ORDER = {ACTION_PRIORITY_ORDER}")
    print(f"  DECISION_ENGINE_VERSION = {DECISION_ENGINE_VERSION}")
    print(f"  POLICY_VERSION = {POLICY_VERSION}")
    print(f"  BASELINE_MAX_RETRIES = {BASELINE_MAX_RETRIES}")
    print(f"  BOOTSTRAP_SEED = {BOOTSTRAP_SEED}")
    print(f"  BOOTSTRAP_RESAMPLES = {BOOTSTRAP_RESAMPLES}")
    print(f"  RANDOM_BASELINE_SEED = {RANDOM_BASELINE_SEED}")

    # --- Load data ---
    print("\n--- LOADING DATA ---")
    test_txns, outcome_lookup = load_experiment_data()
    n_txns = len(test_txns)
    print(f"  Test transactions: {n_txns}")
    print(f"  Outcome lookup entries: {len(outcome_lookup)}")

    # --- Load M2 model ---
    print("\n--- LOADING M2 MODEL ---")
    model, model_err = load_model()
    if model is None:
        print(f"  FATAL: M2 model failed to load: {model_err}")
        sys.exit(1)
    print("  M2 model loaded: PASS")

    # --- Initialize RNG for B1 ---
    rng_b1 = np.random.RandomState(RANDOM_BASELINE_SEED)

    # --- Evaluate all transactions ---
    print("\n--- EVALUATING ALL POLICIES ---")
    all_results = {p: [] for p in ALL_POLICIES}
    all_violations = []

    for idx, row in test_txns.iterrows():
        txn_ctx = build_transaction_context(row)
        txn_id = txn_ctx["transaction_id"]

        # Assert no hidden truth in context
        for col in HIDDEN_TRUTH_COLS_FORBIDDEN:
            assert col not in txn_ctx, f"LEAK: {col} in txn {txn_id}"

        # Run M3 policy (shared across all policies for safety parity)
        policy_result = evaluate_policy(txn_ctx)

        # Evaluate all policies
        results = evaluate_all_policies(
            txn_ctx, policy_result, model, outcome_lookup, rng_b1
        )

        # Collect results and verify safety
        for policy_name, res in results.items():
            record = {
                "transaction_id": txn_id,
                "failure_type": txn_ctx["failure_type"],
                "amount": txn_ctx["amount"],
                "risk_score": txn_ctx["risk_score"],
                "attempt_number": txn_ctx["attempt_number"],
                "contact_fatigue_score": txn_ctx["contact_fatigue_score"],
                "segment": txn_ctx["segment"],
                "action": res["action"],
                "source": res["source"],
                "fallback_used": res["fallback_used"],
                "recovered": res["recovered"],
                "recovered_amount": res["recovered_amount"],
                "intervention_cost": res["intervention_cost"],
                "discount_amount": res["discount_amount"],
                "net_recovered_amount": res["net_recovered_amount"],
                "escalation_required": res["escalation_required"],
                "terminal": res["terminal"],
            }
            all_results[policy_name].append(record)

            # Safety check
            viols = verify_safety(policy_name, res["action"], policy_result, txn_ctx)
            all_violations.extend(viols)

        if (idx + 1) % 500 == 0:
            print(f"  Processed {idx + 1}/{n_txns} transactions...")

    print(f"  Processed {n_txns}/{n_txns} transactions — done.")

    # --- Build DataFrames ---
    dfs = {}
    for policy_name in ALL_POLICIES:
        dfs[policy_name] = pd.DataFrame(all_results[policy_name])

    # --- Safety violations ---
    print(f"\n--- SAFETY VIOLATIONS ---")
    print(f"  Total violations: {len(all_violations)}")
    if all_violations:
        for v in all_violations[:10]:
            print(f"    {v}")

    # --- Compute metrics ---
    print("\n--- COMPUTING METRICS ---")
    metrics = {}
    for policy_name in ALL_POLICIES:
        metrics[policy_name] = compute_policy_metrics(dfs[policy_name])

    # --- Print summary table ---
    print("\n" + "=" * 70)
    print("COMPARISON TABLE — ALL POLICIES")
    print("=" * 70)
    print(f"\n  {'Policy':<25} {'Recovered':>10} {'Rate':>7} {'Gross':>12} "
          f"{'Cost':>8} {'Net':>12} {'MostFreq':>10} {'Share':>6}")
    print(f"  {'-'*90}")

    sorted_policies = sorted(ALL_POLICIES,
                             key=lambda p: metrics[p]["net_recovered_amount"],
                             reverse=True)
    for p in sorted_policies:
        m = metrics[p]
        print(f"  {p:<25} {m['transactions_recovered']:>10} "
              f"{m['recovery_rate']:>6.1f}% "
              f"{m['gross_recovered_amount']:>12,.0f} "
              f"{m['total_intervention_cost']:>8,.0f} "
              f"{m['net_recovered_amount']:>12,.0f} "
              f"{m['most_frequent_action']:>10} "
              f"{m['most_frequent_action_share']:>5.1f}%")

    # --- Primary result ---
    pa_net = metrics["policy_a"]["net_recovered_amount"]
    b0_net = metrics["b0_waterfall"]["net_recovered_amount"]
    b6_net = metrics["b6_oracle"]["net_recovered_amount"]

    uplift = pa_net - b0_net
    if b0_net > 0:
        uplift_pct = uplift / b0_net * 100
        uplift_pct_str = f"{uplift_pct:+.2f}%"
    else:
        uplift_pct = None
        uplift_pct_str = "not computable (baseline net <= 0)"

    headroom = b6_net - b0_net
    if headroom > 0:
        headroom_pct = (pa_net - b0_net) / headroom * 100
    else:
        headroom_pct = None

    print(f"\n--- PRIMARY RESULT ---")
    print(f"  Baseline (B0) net recovered:  {b0_net:>12,.2f}")
    print(f"  Policy A net recovered:       {pa_net:>12,.2f}")
    print(f"  Net Recovery Uplift:          {uplift:>12,.2f}")
    print(f"  Percentage uplift:            {uplift_pct_str}")
    print(f"  Oracle (B6) net recovered:    {b6_net:>12,.2f}")
    if headroom_pct is not None:
        print(f"  Headroom captured (B0→B6):    {headroom_pct:.1f}%")

    # --- Paired bootstrap ---
    print(f"\n--- PAIRED BOOTSTRAP (seed={BOOTSTRAP_SEED}, n={BOOTSTRAP_RESAMPLES}) ---")

    for baseline_name in ALL_POLICIES:
        if baseline_name == "policy_a":
            continue
        pa_vals = dfs["policy_a"]["net_recovered_amount"].values
        bl_vals = dfs[baseline_name]["net_recovered_amount"].values

        # Net recovered amount
        bs_net = paired_bootstrap(pa_vals, bl_vals,
                                  n_resamples=BOOTSTRAP_RESAMPLES,
                                  seed=BOOTSTRAP_SEED, statistic="sum")
        # Recovery rate
        pa_rec = dfs["policy_a"]["recovered"].astype(float).values
        bl_rec = dfs[baseline_name]["recovered"].astype(float).values
        bs_rate = paired_bootstrap(pa_rec, bl_rec,
                                   n_resamples=BOOTSTRAP_RESAMPLES,
                                   seed=BOOTSTRAP_SEED, statistic="mean")

        sig = "YES" if bs_net["excludes_zero"] else "NO"
        print(f"\n  Policy A vs {baseline_name}:")
        print(f"    Net amount diff:  {bs_net['point_estimate']:>+12,.2f}  "
              f"95% CI [{bs_net['ci_lower']:>+12,.2f}, {bs_net['ci_upper']:>+12,.2f}]  "
              f"Excludes 0: {sig}")
        print(f"    Recovery rate diff: {bs_rate['point_estimate']:>+.4f}  "
              f"95% CI [{bs_rate['ci_lower']:>+.4f}, {bs_rate['ci_upper']:>+.4f}]")

    # --- Degeneracy check ---
    print(f"\n--- DEGENERACY CHECK ---")
    for p in ALL_POLICIES:
        m = metrics[p]
        flag = " *** DEGENERACY WARNING ***" if m["most_frequent_action_share"] > 90 else ""
        print(f"  {p:<25} most_frequent={m['most_frequent_action']:<15} "
              f"share={m['most_frequent_action_share']:.1f}%{flag}")

    # --- Action breakdown ---
    print(f"\n--- ACTION BREAKDOWN ---")
    for p in ["policy_a", "b0_waterfall"]:
        print(f"\n  {p}:")
        ab = action_breakdown(dfs[p])
        print(f"  {'Action':<20} {'Count':>6} {'RecRate':>8} {'Gross':>10} {'Cost':>6} {'Net':>10}")
        for _, r in ab.iterrows():
            if r["count"] > 0:
                print(f"  {r['action']:<20} {r['count']:>6} {r['recovery_rate']:>7.1f}% "
                      f"{r['gross_recovered']:>10,.0f} {r['intervention_cost']:>6,.0f} "
                      f"{r['net_recovered']:>10,.0f}")
            else:
                print(f"  {r['action']:<20} {r['count']:>6}     —          —      —          —")

    # --- Failure-type breakdown ---
    print(f"\n--- FAILURE-TYPE BREAKDOWN ---")
    for p in ["policy_a", "b0_waterfall"]:
        print(f"\n  {p}:")
        fb = group_breakdown(dfs[p], "failure_type")
        print(f"  {'Failure Type':<30} {'Count':>6} {'RecRate':>8} {'Net':>12}")
        for _, r in fb.iterrows():
            print(f"  {r['failure_type']:<30} {r['count']:>6} {r['recovery_rate']:>7.1f}% "
                  f"{r['net_recovered']:>12,.0f}")

    # --- Segment breakdown ---
    print(f"\n--- SEGMENT BREAKDOWN ---")
    for p in ["policy_a", "b0_waterfall"]:
        print(f"\n  {p}:")
        sb = group_breakdown(dfs[p], "segment")
        print(f"  {'Segment':<20} {'Count':>6} {'RecRate':>8} {'Net':>12}")
        for _, r in sb.iterrows():
            print(f"  {r['segment']:<20} {r['count']:>6} {r['recovery_rate']:>7.1f}% "
                  f"{r['net_recovered']:>12,.0f}")

    # --- Amount band breakdown ---
    print(f"\n--- AMOUNT BAND BREAKDOWN ---")
    for p in ["policy_a", "b0_waterfall"]:
        df = dfs[p].copy()
        df["amount_band"] = pd.cut(df["amount"], bins=[0, 1000, 10000, float("inf")],
                                   labels=["<1000", "1000-10000", ">10000"])
        print(f"\n  {p}:")
        ab = group_breakdown(df, "amount_band")
        print(f"  {'Band':<15} {'Count':>6} {'RecRate':>8} {'Net':>12}")
        for _, r in ab.iterrows():
            print(f"  {r['amount_band']:<15} {r['count']:>6} {r['recovery_rate']:>7.1f}% "
                  f"{r['net_recovered']:>12,.0f}")

    # --- Risk band breakdown ---
    print(f"\n--- RISK BAND BREAKDOWN ---")
    for p in ["policy_a", "b0_waterfall"]:
        df = dfs[p].copy()
        df["risk_band"] = pd.cut(df["risk_score"], bins=[0, 0.75, 0.85, 1.0],
                                 labels=["<0.75", "0.75-0.85", ">0.85"],
                                 include_lowest=True)
        print(f"\n  {p}:")
        rb = group_breakdown(df, "risk_band")
        print(f"  {'Band':<15} {'Count':>6} {'RecRate':>8} {'Net':>12}")
        for _, r in rb.iterrows():
            print(f"  {r['risk_band']:<15} {r['count']:>6} {r['recovery_rate']:>7.1f}% "
                  f"{r['net_recovered']:>12,.0f}")

    # --- Cells where Policy A does NOT beat B0 ---
    print(f"\n--- FAILURE-TYPE CELLS WHERE POLICY A DOES NOT BEAT B0 ---")
    fb_a = group_breakdown(dfs["policy_a"], "failure_type")
    fb_b0 = group_breakdown(dfs["b0_waterfall"], "failure_type")
    merged = fb_a.merge(fb_b0, on="failure_type", suffixes=("_a", "_b0"))
    loss_cells = merged[merged["net_recovered_a"] <= merged["net_recovered_b0"]]
    if len(loss_cells) == 0:
        print("  Policy A beats B0 in ALL failure-type cells.")
    else:
        for _, r in loss_cells.iterrows():
            print(f"  {r['failure_type']}: A={r['net_recovered_a']:.0f} vs B0={r['net_recovered_b0']:.0f}")

    # --- Controlled decision examples ---
    print(f"\n--- CONTROLLED DECISION EXAMPLES ---")
    pa_df = dfs["policy_a"]
    b0_df = dfs["b0_waterfall"]
    merged_txn = pa_df.merge(b0_df, on="transaction_id", suffixes=("_a", "_b0"))

    # Example 1: different action
    diff = merged_txn[merged_txn["action_a"] != merged_txn["action_b0"]]
    if len(diff) > 0:
        ex = diff.iloc[0]
        print(f"\n  Example 1: Policy A chooses different action than baseline")
        print(f"    txn={ex['transaction_id']}, failure_type={ex['failure_type_a']}, "
              f"amount={ex['amount_a']:.2f}, risk={ex['risk_score_a']:.2f}")
        print(f"    Baseline: {ex['action_b0']}, recovered={ex['recovered_b0']}, net={ex['net_recovered_amount_b0']:.2f}")
        print(f"    Policy A: {ex['action_a']}, recovered={ex['recovered_a']}, net={ex['net_recovered_amount_a']:.2f}")

    # Example 2: close/wait instead of intervention
    cw = diff[(diff["action_a"].isin(["close", "wait"])) & (~diff["action_b0"].isin(["close", "wait"]))]
    if len(cw) > 0:
        ex = cw.iloc[0]
        print(f"\n  Example 2: Policy A chooses close/wait instead of intervention")
        print(f"    txn={ex['transaction_id']}, failure_type={ex['failure_type_a']}, amount={ex['amount_a']:.2f}")
        print(f"    Baseline: {ex['action_b0']}, recovered={ex['recovered_b0']}, net={ex['net_recovered_amount_b0']:.2f}")
        print(f"    Policy A: {ex['action_a']}, recovered={ex['recovered_a']}, net={ex['net_recovered_amount_a']:.2f}")

    # Example 3: discount where justified
    disc = diff[diff["action_a"] == "discount"]
    if len(disc) > 0:
        ex = disc.iloc[0]
        print(f"\n  Example 3: Policy A chooses discount where economically justified")
        print(f"    txn={ex['transaction_id']}, failure_type={ex['failure_type_a']}, amount={ex['amount_a']:.2f}")
        print(f"    Baseline: {ex['action_b0']}, recovered={ex['recovered_b0']}, net={ex['net_recovered_amount_b0']:.2f}")
        print(f"    Policy A: {ex['action_a']}, recovered={ex['recovered_a']}, net={ex['net_recovered_amount_a']:.2f}")

    # Example 4: retry where appropriate
    ret = merged_txn[(merged_txn["action_a"] == "retry")]
    if len(ret) > 0:
        ex = ret.iloc[0]
        print(f"\n  Example 4: Policy A chooses retry where appropriate")
        print(f"    txn={ex['transaction_id']}, failure_type={ex['failure_type_a']}, amount={ex['amount_a']:.2f}")
        print(f"    Baseline: {ex['action_b0']}, recovered={ex['recovered_b0']}, net={ex['net_recovered_amount_b0']:.2f}")
        print(f"    Policy A: {ex['action_a']}, recovered={ex['recovered_a']}, net={ex['net_recovered_amount_a']:.2f}")

    # --- Save results ---
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Comparison table CSV
    comp_rows = []
    for p in sorted_policies:
        m = metrics[p]
        comp_rows.append({
            "policy": p,
            "transactions_recovered": m["transactions_recovered"],
            "recovery_rate": round(m["recovery_rate"], 2),
            "gross_recovered_amount": round(m["gross_recovered_amount"], 2),
            "total_intervention_cost": round(m["total_intervention_cost"], 2),
            "net_recovered_amount": round(m["net_recovered_amount"], 2),
            "most_frequent_action": m["most_frequent_action"],
            "most_frequent_action_share": round(m["most_frequent_action_share"], 1),
        })
    pd.DataFrame(comp_rows).to_csv(
        os.path.join(RESULTS_DIR, "comparison_table.csv"), index=False)

    # Per-transaction decisions CSV
    all_per_txn = []
    for p in ALL_POLICIES:
        df_p = dfs[p].copy()
        df_p["policy"] = p
        all_per_txn.append(df_p)
    pd.concat(all_per_txn, ignore_index=True).to_csv(
        os.path.join(RESULTS_DIR, "per_transaction_decisions.csv"), index=False)

    print(f"\n--- FILES SAVED ---")
    print(f"  {os.path.join(RESULTS_DIR, 'comparison_table.csv')}")
    print(f"  {os.path.join(RESULTS_DIR, 'per_transaction_decisions.csv')}")

    # --- Oracle sanity check ---
    print(f"\n--- ORACLE SANITY CHECK ---")
    for p in ALL_POLICIES:
        if p == "b6_oracle":
            continue
        assert metrics[p]["net_recovered_amount"] <= metrics["b6_oracle"]["net_recovered_amount"] + 0.01, \
            f"ORACLE VIOLATION: {p} ({metrics[p]['net_recovered_amount']}) > oracle ({metrics['b6_oracle']['net_recovered_amount']})"
        print(f"  {p} <= oracle: PASS")

    # --- Final summary ---
    print(f"\n" + "=" * 70)
    print("M5 EXPERIMENT COMPLETE")
    print("=" * 70)
    print(f"\n  No M5 baseline comparison constitutes a causal claim.")
    print(f"  The intelligent policy produced {uplift:+,.2f} more net recovered")
    print(f"  amount than the baseline in the synthetic evaluation.")
    print(f"  Percentage uplift: {uplift_pct_str}")

    return {
        "metrics": metrics,
        "dfs": dfs,
        "violations": all_violations,
        "uplift": uplift,
        "uplift_pct": uplift_pct,
        "headroom_pct": headroom_pct,
    }


if __name__ == "__main__":
    run_experiment()
