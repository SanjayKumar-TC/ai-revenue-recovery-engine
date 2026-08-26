"""
M5: Experiment Metrics + Paired Bootstrap
==========================================
Calculates all secondary metrics and paired bootstrap confidence intervals.
"""

import numpy as np
import pandas as pd
from ml.decision.decision_config import ACTION_COSTS, DEFAULT_DISCOUNT_PERCENT


# ============================================================
# Scoring a single (action, outcome) pair
# ============================================================

def score_action(action, outcome, amount, discount_percent=None):
    """
    Score a single policy decision against a realized outcome.

    Discount accounting (per M5 spec):
      recovered_amount = amount × (1 - discount_percent/100) if discount + recovered
      Do NOT also subtract discount as a cost. ACTION_COSTS['discount'] = 0.

    Returns dict with: recovered, recovered_amount, intervention_cost,
                       discount_amount, net_recovered_amount
    """
    dp = discount_percent if discount_percent is not None else DEFAULT_DISCOUNT_PERCENT
    recovered = bool(outcome == 1)

    if action == "escalate" or action == "no_action_required":
        # Escalate: no realized outcome → not recovered (Option 1)
        return {
            "recovered": False,
            "recovered_amount": 0.0,
            "intervention_cost": 0.0,
            "discount_amount": 0.0,
            "net_recovered_amount": 0.0,
        }

    intervention_cost = ACTION_COSTS.get(action, 0.0)

    if recovered:
        if action == "discount":
            discount_amount = amount * (dp / 100.0)
            recovered_amount = amount - discount_amount
        else:
            discount_amount = 0.0
            recovered_amount = amount
    else:
        discount_amount = 0.0
        recovered_amount = 0.0

    net_recovered_amount = recovered_amount - intervention_cost

    return {
        "recovered": recovered,
        "recovered_amount": recovered_amount,
        "intervention_cost": intervention_cost,
        "discount_amount": discount_amount,
        "net_recovered_amount": net_recovered_amount,
    }


# ============================================================
# Aggregate Metrics (16 secondary metrics per policy)
# ============================================================

def compute_policy_metrics(results_df):
    """
    Compute all 16 secondary metrics for a single policy's results.

    results_df must have columns:
      transaction_id, action, recovered, recovered_amount,
      intervention_cost, discount_amount, net_recovered_amount,
      escalation_required, terminal, fallback_used
    """
    n = len(results_df)
    if n == 0:
        return {}

    recovered_mask = results_df["recovered"]
    n_recovered = recovered_mask.sum()

    # Action distribution
    action_dist = results_df["action"].value_counts()
    action_pct = (action_dist / n * 100).round(2)

    # Most frequent action share (degeneracy check)
    most_freq_action = action_dist.index[0] if len(action_dist) > 0 else "none"
    most_freq_share = (action_dist.iloc[0] / n * 100) if len(action_dist) > 0 else 0

    # Discount usage
    discount_mask = results_df["action"] == "discount"
    discount_recovered = results_df[discount_mask & recovered_mask]
    n_discount = discount_mask.sum()
    mean_discount = (discount_recovered["discount_amount"].mean()
                     if len(discount_recovered) > 0 else 0.0)

    # Escalation/terminal counts
    n_escalation = results_df["escalation_required"].sum() if "escalation_required" in results_df else 0
    n_terminal = results_df["terminal"].sum() if "terminal" in results_df else 0

    # Automation rate: resolved without escalation and without hard block
    non_escalated = results_df[~results_df.get("escalation_required", pd.Series(False, index=results_df.index)).astype(bool)]
    non_terminal = non_escalated[~non_escalated.get("terminal", pd.Series(False, index=non_escalated.index)).astype(bool)]
    automation_rate = len(non_terminal) / n * 100 if n > 0 else 0

    # Policy-blocked fallback count
    n_fallback = results_df["fallback_used"].sum() if "fallback_used" in results_df else 0

    return {
        "total_transactions": n,
        "transactions_recovered": int(n_recovered),
        "recovery_rate": n_recovered / n * 100,
        "gross_recovered_amount": results_df["recovered_amount"].sum(),
        "total_intervention_cost": results_df["intervention_cost"].sum(),
        "net_recovered_amount": results_df["net_recovered_amount"].sum(),
        "mean_net_recovery": results_df["net_recovered_amount"].mean(),
        "median_net_recovery": results_df["net_recovered_amount"].median(),
        "escalation_count": int(n_escalation),
        "terminal_count": int(n_terminal),
        "action_distribution": action_dist.to_dict(),
        "action_pct": action_pct.to_dict(),
        "policy_blocked_fallback_count": int(n_fallback),
        "discount_usage_count": int(n_discount),
        "mean_discount_amount": float(mean_discount),
        "automation_rate": automation_rate,
        "most_frequent_action": most_freq_action,
        "most_frequent_action_share": most_freq_share,
    }


# ============================================================
# Paired Bootstrap
# ============================================================

def paired_bootstrap(values_a, values_b, n_resamples=10000, seed=42,
                     statistic="sum"):
    """
    Paired bootstrap for difference between two policies.

    Same transaction indices are drawn ONCE and applied to both policies.

    Parameters
    ----------
    values_a, values_b : array-like — per-transaction values (same length)
    n_resamples : int
    seed : int
    statistic : "sum" or "mean"

    Returns
    -------
    dict with: point_estimate, ci_lower, ci_upper, excludes_zero
    """
    a = np.asarray(values_a, dtype=float)
    b = np.asarray(values_b, dtype=float)
    assert len(a) == len(b), "Paired bootstrap requires equal length arrays"
    n = len(a)

    rng = np.random.RandomState(seed)

    if statistic == "sum":
        point_est = a.sum() - b.sum()
    else:
        point_est = a.mean() - b.mean()

    diffs = np.empty(n_resamples)
    for i in range(n_resamples):
        indices = rng.randint(0, n, size=n)
        a_sample = a[indices]
        b_sample = b[indices]
        if statistic == "sum":
            diffs[i] = a_sample.sum() - b_sample.sum()
        else:
            diffs[i] = a_sample.mean() - b_sample.mean()

    ci_lower = np.percentile(diffs, 2.5)
    ci_upper = np.percentile(diffs, 97.5)
    excludes_zero = (ci_lower > 0) or (ci_upper < 0)

    return {
        "point_estimate": float(point_est),
        "ci_lower": float(ci_lower),
        "ci_upper": float(ci_upper),
        "excludes_zero": bool(excludes_zero),
        "n_resamples": n_resamples,
        "seed": seed,
    }


# ============================================================
# Action-Level Breakdown
# ============================================================

def action_breakdown(results_df):
    """Per-action breakdown: count, recovery_rate, gross, cost, net."""
    all_actions = ["retry", "payment_link", "reminder", "discount",
                   "wait", "close", "escalate", "no_action_required"]
    rows = []
    for action in all_actions:
        subset = results_df[results_df["action"] == action]
        n = len(subset)
        if n == 0:
            rows.append({
                "action": action, "count": 0, "recovery_rate": 0.0,
                "gross_recovered": 0.0, "intervention_cost": 0.0,
                "net_recovered": 0.0,
            })
        else:
            rows.append({
                "action": action,
                "count": n,
                "recovery_rate": subset["recovered"].sum() / n * 100,
                "gross_recovered": subset["recovered_amount"].sum(),
                "intervention_cost": subset["intervention_cost"].sum(),
                "net_recovered": subset["net_recovered_amount"].sum(),
            })
    return pd.DataFrame(rows)


# ============================================================
# Generic Group Breakdown
# ============================================================

def group_breakdown(results_df, group_col):
    """Breakdown by an arbitrary column: count, recovery_rate, net_recovered."""
    rows = []
    for val in sorted(results_df[group_col].unique()):
        subset = results_df[results_df[group_col] == val]
        n = len(subset)
        rows.append({
            group_col: val,
            "count": n,
            "recovery_rate": subset["recovered"].sum() / n * 100 if n > 0 else 0,
            "net_recovered": subset["net_recovered_amount"].sum(),
        })
    return pd.DataFrame(rows)
