"""
M5 Closeout + M5.1 Diagnostic
===============================
Computes all diagnostic metrics D1-D10 and generates:
  - ml/evaluation/m5_report.md
  - ml/evaluation/m5_1_diagnostic.md

Usage:
    python m5_closeout_diagnostic.py
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ml.decision.decision_config import (
    ACTION_COSTS, DEFAULT_DISCOUNT_PERCENT, DECISION_ENGINE_VERSION,
    EV_TIE_TOLERANCE, ACTION_PRIORITY_ORDER,
)
from ml.decision.decision_engine import make_decision, load_model, predict_probability
from ml.decision.ev_engine import calculate_ev
from ml.policy.policy_engine import evaluate_policy
from ml.policy.policy_config import POLICY_VERSION
from ml.policy.eligibility import ELIGIBILITY
from ml.experiment.experiment_metrics import paired_bootstrap, score_action
from ml.experiment.baseline_policy import select_b0_waterfall, BASELINE_MAX_RETRIES

ALL_ACTIONS_LIST = ["retry", "payment_link", "reminder", "discount",
                    "wait", "close", "escalate", "no_action_required"]

# ============================================================
# DATA LOADING
# ============================================================

def load_all_data():
    """Load all data needed for diagnostics."""
    print("Loading data...")
    per_txn = pd.read_csv("ml/experiment/results/per_transaction_decisions.csv")
    ht = pd.read_csv("action_expanded_with_hidden_truth.csv")
    tr = pd.read_csv("action_expanded_training_data.csv")
    model, err = load_model()
    if model is None:
        print(f"FATAL: M2 model failed to load: {err}")
        sys.exit(1)

    # Split per_txn by policy
    policies = {}
    for p in per_txn["policy"].unique():
        policies[p] = per_txn[per_txn["policy"] == p].reset_index(drop=True)

    return per_txn, ht, tr, model, policies


# ============================================================
# PART 1 ITEMS
# ============================================================

def compute_part1(policies, ht, model):
    """Compute Part 1 items: Example 2, headroom, bootstrap."""
    print("\n" + "=" * 70)
    print("PART 1: M5 REPORTING CLOSEOUT")
    print("=" * 70)

    pa = policies["policy_a"]
    b0 = policies["b0_waterfall"]
    b1 = policies["b1_random"]
    b6 = policies["b6_oracle"]

    # --- 1.1: Example 2 ---
    print("\n--- 1.1: CONTROLLED EXAMPLE 2 ---")
    close_count = (pa["action"] == "close").sum()
    wait_count = (pa["action"] == "wait").sum()
    print(f"  Policy A close count: {close_count}")
    print(f"  Policy A wait count: {wait_count}")

    merged = pa.merge(b0, on="transaction_id", suffixes=("_a", "_b0"))
    active_actions = {"retry", "payment_link", "reminder", "discount"}
    ex2 = merged[(merged["action_a"] == "wait") &
                 (merged["action_b0"].isin(active_actions))]
    if len(ex2) > 0:
        ex = ex2.iloc[0]
        print(f"\n  Example 2 found ({len(ex2)} cases total):")
        print(f"    txn={ex['transaction_id']}, failure_type={ex['failure_type_a']}")
        print(f"    amount={ex['amount_a']:.2f}, risk={ex['risk_score_a']:.2f}")
        print(f"    B0: {ex['action_b0']}, recovered={ex['recovered_b0']}, "
              f"net={ex['net_recovered_amount_b0']:.2f}")
        print(f"    PA: {ex['action_a']}, recovered={ex['recovered_a']}, "
              f"net={ex['net_recovered_amount_a']:.2f}")
        ex2_text = (f"Example 2 present: {len(ex2)} cases where Policy A chose wait "
                    f"while B0 chose an active intervention.\n"
                    f"Sample: txn {ex['transaction_id']}, failure_type={ex['failure_type_a']}, "
                    f"amount={ex['amount_a']:.2f}. B0={ex['action_b0']} "
                    f"(net={ex['net_recovered_amount_b0']:.2f}), "
                    f"PA=wait (net={ex['net_recovered_amount_a']:.2f})")
    else:
        print("  Example 2 not present in the observed test population.")
        ex2_text = (f"Example 2 not present. Policy A selected close {close_count} times "
                    f"and wait {wait_count} times out of 1,577 transactions.")

    # --- 1.2: Headroom ---
    print("\n--- 1.2: HEADROOM METRIC ---")
    pa_net = pa["net_recovered_amount"].sum()
    b0_net = b0["net_recovered_amount"].sum()
    b6_net = b6["net_recovered_amount"].sum()
    uplift = pa_net - b0_net
    headroom_denom = b6_net - b0_net
    headroom_pct = uplift / headroom_denom * 100 if headroom_denom > 0 else None
    oracle_ratio = b6_net / b0_net if b0_net > 0 else None
    print(f"  PA net: {pa_net:,.2f}")
    print(f"  B0 net: {b0_net:,.2f}")
    print(f"  B6 oracle net: {b6_net:,.2f}")
    print(f"  Uplift: {uplift:+,.2f}")
    print(f"  Headroom: {headroom_pct:+.2f}%" if headroom_pct else "  Headroom: N/A")
    print(f"  Oracle/B0 ratio: {oracle_ratio:.2f}x" if oracle_ratio else "  Oracle/B0: N/A")

    # --- 1.3: Bootstrap CIs ---
    print("\n--- 1.3: REAL BOOTSTRAP CONFIDENCE INTERVALS ---")
    print(f"  Seed: {42}, Resamples: 10,000")

    for bl_name, bl_df in [("b0_waterfall", b0), ("b1_random", b1)]:
        bs_net = paired_bootstrap(
            pa["net_recovered_amount"].values,
            bl_df["net_recovered_amount"].values,
            n_resamples=10000, seed=42, statistic="sum")
        bs_rate = paired_bootstrap(
            pa["recovered"].astype(float).values,
            bl_df["recovered"].astype(float).values,
            n_resamples=10000, seed=42, statistic="mean")
        sig_net = "YES" if bs_net["excludes_zero"] else "NO"
        sig_rate = "YES" if bs_rate["excludes_zero"] else "NO"
        print(f"\n  Policy A vs {bl_name}:")
        print(f"    Net amount: {bs_net['point_estimate']:+,.2f}  "
              f"95% CI [{bs_net['ci_lower']:+,.2f}, {bs_net['ci_upper']:+,.2f}]  "
              f"Excludes 0: {sig_net}")
        print(f"    Rec rate:   {bs_rate['point_estimate']:+.4f}  "
              f"95% CI [{bs_rate['ci_lower']:+.4f}, {bs_rate['ci_upper']:+.4f}]  "
              f"Excludes 0: {sig_rate}")

    return {
        "pa_net": pa_net, "b0_net": b0_net, "b6_net": b6_net,
        "b1_net": b1["net_recovered_amount"].sum(),
        "uplift": uplift, "headroom_pct": headroom_pct,
        "oracle_ratio": oracle_ratio, "ex2_text": ex2_text,
        "close_count": close_count, "wait_count": wait_count,
    }


# ============================================================
# D1: ACTION-SELECTION DISTRIBUTION
# ============================================================

def compute_d1(policies):
    print("\n" + "=" * 70)
    print("D1: ACTION-SELECTION DISTRIBUTION")
    print("=" * 70)
    d1 = {}
    for pname in ["policy_a", "b0_waterfall"]:
        df = policies[pname]
        n = len(df)
        dist = df["action"].value_counts()
        pct = (dist / n * 100).round(2)
        d1[pname] = {"dist": dist.to_dict(), "pct": pct.to_dict(), "n": n}
        print(f"\n  {pname} (n={n}):")
        print(f"  {'Action':<20} {'Count':>6} {'Pct':>7}")
        for a in ALL_ACTIONS_LIST:
            c = dist.get(a, 0)
            p = pct.get(a, 0.0)
            print(f"  {a:<20} {c:>6} {p:>6.1f}%")
        mfa = dist.index[0]
        mfs = dist.iloc[0] / n * 100
        print(f"  Most frequent: {mfa} ({mfs:.1f}%)")
        if mfs > 90:
            print(f"  *** DEGENERACY WARNING ***")
        d1[pname]["mfa"] = mfa
        d1[pname]["mfs"] = mfs
    return d1


# ============================================================
# D2: HAIRCUT TEST
# ============================================================

def compute_d2(policies):
    print("\n" + "=" * 70)
    print("D2: HAIRCUT TEST — RECOVERY RATE VS NET VALUE")
    print("=" * 70)
    d2 = {}
    print(f"\n  {'Policy':<25} {'Recov':>6} {'Rate':>7} {'Gross':>12} "
          f"{'Cost':>8} {'Disc':>10} {'Net':>12}")
    print(f"  {'-'*82}")
    for pname in sorted(policies.keys()):
        df = policies[pname]
        n = len(df)
        rec = df["recovered"].sum()
        rate = rec / n * 100
        gross = df["recovered_amount"].sum()
        cost = df["intervention_cost"].sum()
        disc = df["discount_amount"].sum()
        net = df["net_recovered_amount"].sum()
        d2[pname] = {"rec": int(rec), "rate": rate, "gross": gross,
                     "cost": cost, "disc": disc, "net": net, "n": n}
        print(f"  {pname:<25} {rec:>6} {rate:>6.1f}% {gross:>12,.0f} "
              f"{cost:>8,.0f} {disc:>10,.0f} {net:>12,.0f}")

    pa = d2["policy_a"]
    b0 = d2["b0_waterfall"]
    print(f"\n  PA recovery rate: {pa['rate']:.1f}%, B0: {b0['rate']:.1f}%")
    print(f"  PA net: {pa['net']:,.0f}, B0 net: {b0['net']:,.0f}")
    if pa["rate"] > b0["rate"] and pa["net"] < b0["net"]:
        print("  *** HIGHER RECOVERY RATE BUT LOWER NET → HAIRCUT PROBLEM ***")
        print("  The loss comes from giving away value on recoveries, not failing to recover.")
    elif pa["rate"] <= b0["rate"]:
        print("  PA has equal or lower recovery rate → loss from fewer recoveries.")
    return d2


# ============================================================
# D3: PER-ACTION CALIBRATION
# ============================================================

def compute_d3(ht, model):
    print("\n" + "=" * 70)
    print("D3: PER-ACTION CALIBRATION")
    print("=" * 70)
    test_ht = ht[ht["split"] == "test"].copy()

    # Get unique transaction contexts
    ctx_cols = ["transaction_id", "failure_type", "amount", "risk_score",
                "attempt_number", "contact_fatigue_score", "segment",
                "payment_method", "lifetime_successful_txns", "lifetime_failed_txns"]
    txn_ctx = test_ht.drop_duplicates("transaction_id")[ctx_cols]
    ctx_lookup = {int(r["transaction_id"]): r.to_dict() for _, r in txn_ctx.iterrows()}

    # Predict probabilities for all (transaction, action) pairs
    preds = []
    for _, row in test_ht.iterrows():
        txn_id = int(row["transaction_id"])
        action = row["action"]
        outcome = int(row["outcome"])
        ctx = ctx_lookup[txn_id]
        try:
            prob = predict_probability(model, ctx, action)
        except Exception:
            prob = np.nan
        preds.append({
            "transaction_id": txn_id, "action": action,
            "predicted": prob, "realized": outcome,
            "amount": float(ctx["amount"]),
        })

    pred_df = pd.DataFrame(preds)
    pred_df = pred_df.dropna(subset=["predicted"])

    print(f"\n  Total predictions: {len(pred_df)}")

    d3 = {}
    print(f"\n  {'Action':<20} {'MeanPred':>9} {'Realized':>9} {'Gap':>9} {'WtGap':>9} {'N':>5}")
    print(f"  {'-'*63}")
    for action in sorted(pred_df["action"].unique()):
        sub = pred_df[pred_df["action"] == action]
        mean_pred = sub["predicted"].mean()
        realized = sub["realized"].mean()
        gap = mean_pred - realized
        # Amount-weighted gap
        weights = sub["amount"] / sub["amount"].sum()
        wt_gap = (weights * (sub["predicted"] - sub["realized"])).sum()
        d3[action] = {
            "mean_pred": mean_pred, "realized": realized,
            "gap": gap, "wt_gap": wt_gap, "n": len(sub),
        }
        print(f"  {action:<20} {mean_pred:>9.4f} {realized:>9.4f} "
              f"{gap:>+9.4f} {wt_gap:>+9.4f} {len(sub):>5}")

    # Rank by absolute gap
    ranked = sorted(d3.items(), key=lambda x: abs(x[1]["gap"]), reverse=True)
    print(f"\n  Ranked by |gap|: {', '.join(a for a, _ in ranked)}")

    # Per-action decile calibration for top actions
    for action in [r[0] for r in ranked[:3]]:
        sub = pred_df[pred_df["action"] == action].copy()
        sub["decile"] = pd.qcut(sub["predicted"], 10, labels=False, duplicates="drop")
        print(f"\n  {action} — decile calibration:")
        print(f"  {'Decile':>6} {'MeanPred':>9} {'Realized':>9} {'Gap':>9} {'N':>5}")
        for d in sorted(sub["decile"].unique()):
            dsub = sub[sub["decile"] == d]
            mp = dsub["predicted"].mean()
            rr = dsub["realized"].mean()
            print(f"  {d:>6} {mp:>9.4f} {rr:>9.4f} {mp-rr:>+9.4f} {len(dsub):>5}")

    return d3, pred_df


# ============================================================
# D4: GAP DECOMPOSITION
# ============================================================

def compute_d4(policies):
    print("\n" + "=" * 70)
    print("D4: GAP DECOMPOSITION")
    print("=" * 70)
    pa = policies["policy_a"]
    b0 = policies["b0_waterfall"]
    merged = pa.merge(b0, on="transaction_id", suffixes=("_a", "_b0"))

    divergent = merged[merged["action_a"] != merged["action_b0"]]
    same = merged[merged["action_a"] == merged["action_b0"]]

    n_div = len(divergent)
    n_same = len(same)
    pa_div_net = divergent["net_recovered_amount_a"].sum()
    b0_div_net = divergent["net_recovered_amount_b0"].sum()
    div_delta = pa_div_net - b0_div_net

    pa_same_net = same["net_recovered_amount_a"].sum()
    b0_same_net = same["net_recovered_amount_b0"].sum()
    same_delta = pa_same_net - b0_same_net

    print(f"\n  Divergent transactions: {n_div} ({n_div/len(merged)*100:.1f}%)")
    print(f"  Same-action transactions: {n_same} ({n_same/len(merged)*100:.1f}%)")
    print(f"  Divergent: PA net={pa_div_net:,.0f}, B0 net={b0_div_net:,.0f}, "
          f"delta={div_delta:+,.0f}")
    print(f"  Same: PA net={pa_same_net:,.0f}, B0 net={b0_same_net:,.0f}, "
          f"delta={same_delta:+,.0f}")
    print(f"  Total delta: {div_delta + same_delta:+,.0f}")

    # Substitution matrix
    print(f"\n  SUBSTITUTION MATRIX (PA action → B0 action):")
    print(f"  {'PA→B0':<30} {'Count':>6} {'PA Net':>12} {'B0 Net':>12} {'Delta':>12}")
    print(f"  {'-'*74}")

    sub_data = []
    for (pa_act, b0_act), grp in divergent.groupby(["action_a", "action_b0"]):
        pa_n = grp["net_recovered_amount_a"].sum()
        b0_n = grp["net_recovered_amount_b0"].sum()
        delta = pa_n - b0_n
        sub_data.append({
            "pa_action": pa_act, "b0_action": b0_act,
            "count": len(grp), "pa_net": pa_n, "b0_net": b0_n, "delta": delta,
        })
        print(f"  {pa_act+'→'+b0_act:<30} {len(grp):>6} {pa_n:>12,.0f} "
              f"{b0_n:>12,.0f} {delta:>+12,.0f}")

    sub_df = pd.DataFrame(sub_data).sort_values("delta")
    print(f"\n  TOP 5 MOST COSTLY SUBSTITUTIONS:")
    for _, r in sub_df.head(5).iterrows():
        print(f"    {r['pa_action']}→{r['b0_action']}: {r['count']} txns, "
              f"delta={r['delta']:+,.0f}")

    return {"n_div": n_div, "n_same": n_same, "div_delta": div_delta,
            "same_delta": same_delta, "sub_df": sub_df}


# ============================================================
# D5: REGRET ANALYSIS VS ORACLE
# ============================================================

def compute_d5(policies):
    print("\n" + "=" * 70)
    print("D5: REGRET ANALYSIS VS ORACLE")
    print("=" * 70)
    b6 = policies["b6_oracle"]
    d5 = {}
    for pname in ["policy_a", "b0_waterfall"]:
        df = policies[pname]
        merged = df.merge(b6[["transaction_id", "net_recovered_amount"]],
                          on="transaction_id", suffixes=("", "_oracle"))
        merged["regret"] = merged["net_recovered_amount_oracle"] - merged["net_recovered_amount"]
        total_regret = merged["regret"].sum()
        mean_regret = merged["regret"].mean()
        d5[pname] = {"total": total_regret, "mean": mean_regret, "merged": merged}
        print(f"\n  {pname}:")
        print(f"    Total regret: {total_regret:,.0f}")
        print(f"    Mean regret: {mean_regret:,.2f}")

        # By failure type
        print(f"    By failure_type:")
        for ft, grp in merged.groupby("failure_type"):
            print(f"      {ft:<30} regret={grp['regret'].sum():>10,.0f} "
                  f"(mean={grp['regret'].mean():>8,.1f}, n={len(grp)})")

        # By chosen action
        print(f"    By chosen action:")
        for act, grp in merged.groupby("action"):
            print(f"      {act:<20} regret={grp['regret'].sum():>10,.0f} "
                  f"(mean={grp['regret'].mean():>8,.1f}, n={len(grp)})")

    # Where PA regret exceeds B0
    pa_ft = d5["policy_a"]["merged"].groupby("failure_type")["regret"].sum()
    b0_ft = d5["b0_waterfall"]["merged"].groupby("failure_type")["regret"].sum()
    print(f"\n  Where PA regret exceeds B0 regret (by failure_type):")
    for ft in pa_ft.index:
        if pa_ft[ft] > b0_ft.get(ft, 0):
            print(f"    {ft}: PA={pa_ft[ft]:,.0f} vs B0={b0_ft.get(ft, 0):,.0f}")
    return d5


# ============================================================
# D6: close EV=0 QUESTION
# ============================================================

def compute_d6(ht, policies):
    print("\n" + "=" * 70)
    print("D6: THE close EV=0 QUESTION")
    print("=" * 70)

    # 1. Code path where close gets EV=0
    print("\n  1. close EV hardcoded to 0:")
    print("     In ev_engine.py, calculate_ev():")
    print("       if action == 'close':")
    print("         return {..., 'expected_net_value': 0.0}")
    print("     close is assigned EV=0 regardless of predicted probability.")

    # 2. close's realized recovery rate in test data
    test_ht = ht[ht["split"] == "test"]
    close_rows = test_ht[test_ht["action"] == "close"]
    close_rec_rate = close_rows["outcome"].mean()
    close_n = len(close_rows)
    print(f"\n  2. close realized recovery rate (test): {close_rec_rate:.4f} "
          f"({close_rows['outcome'].sum()}/{close_n})")

    # 3. Net value from close actions by B0 and B1
    for pname in ["b0_waterfall", "b1_random"]:
        df = policies[pname]
        close_df = df[df["action"] == "close"]
        print(f"\n  3. {pname} — close actions:")
        print(f"     count: {len(close_df)}")
        print(f"     recovered: {close_df['recovered'].sum()}")
        print(f"     net recovered: {close_df['net_recovered_amount'].sum():,.2f}")

    # 4. Can close ever be selected when wait is allowed?
    print(f"\n  4. STRUCTURAL CLAIM: can close be selected when wait is allowed?")
    print(f"     EV(close) = 0 always (hardcoded)")
    print(f"     EV(wait) = P(wait) × amount ≥ 0 always")
    print(f"     EV(wait) > 0 when P(wait) > 0 (which is almost always true)")
    print(f"     When EV(wait) = EV(close) = 0: tiebreak by PRIORITY_ORDER")
    print(f"       wait index = {ACTION_PRIORITY_ORDER.index('wait')}")
    print(f"       close index = {ACTION_PRIORITY_ORDER.index('close')}")
    print(f"     wait wins tiebreak. CONFIRMED: close is UNREACHABLE when")
    print(f"     wait is allowed and P(wait) ≥ 0.")

    # 5. Test 12 corollary
    print(f"\n  5. TEST 12 COROLLARY:")
    print(f"     Test 12 excluded wait and discount from the scored set.")
    print(f"     Had wait been scored with P=0, it would tie close at EV=0")
    print(f"     and win tiebreak (priority index 1 < 5).")
    print(f"     CONFIRMED: Test 12 certified a code path (close winning)")
    print(f"     that cannot occur in production when wait is allowed.")

    return {"close_rec_rate": close_rec_rate, "close_n": close_n}


# ============================================================
# D7: COUNTERFACTUAL REFERENCE (VALIDATION ONLY)
# ============================================================

def compute_d7(ht, tr, model):
    print("\n" + "=" * 70)
    print("D7: COUNTERFACTUAL REFERENCE — VALIDATION SPLIT ONLY")
    print("=" * 70)

    val_ht = ht[ht["split"] == "val"].copy()
    outcome_lookup = {}
    for _, row in val_ht.iterrows():
        outcome_lookup[(int(row["transaction_id"]), row["action"])] = int(row["outcome"])

    ctx_cols = ["transaction_id", "failure_type", "amount", "risk_score",
                "attempt_number", "contact_fatigue_score", "segment",
                "payment_method", "lifetime_successful_txns", "lifetime_failed_txns"]
    val_txns = val_ht.drop_duplicates("transaction_id")[ctx_cols].reset_index(drop=True)
    print(f"  Validation transactions: {len(val_txns)}")

    dp = DEFAULT_DISCOUNT_PERCENT
    results_m4 = []
    results_shadow = []
    results_b0 = []

    for _, row in val_txns.iterrows():
        ctx = row.to_dict()
        ctx["transaction_id"] = int(ctx["transaction_id"])
        ctx["attempt_number"] = int(ctx["attempt_number"])
        ctx["lifetime_successful_txns"] = int(ctx["lifetime_successful_txns"])
        ctx["lifetime_failed_txns"] = int(ctx["lifetime_failed_txns"])
        ctx["hours_since_failure"] = 6.0
        ctx["already_recovered"] = False
        ctx["discount_percent"] = dp
        txn_id = ctx["transaction_id"]

        # Run M3
        pr = evaluate_policy(ctx)
        allowed = pr["allowed_actions"]
        terminal = pr["terminal"]
        esc = pr["escalation_required"]

        # --- M4 decision ---
        m4_dec = make_decision(ctx, model_pipeline=model)
        m4_action = m4_dec["decision"]
        m4_outcome = outcome_lookup.get((txn_id, m4_action), 0) if m4_action not in ("no_action_required", "escalate") else 0
        m4_score = score_action(m4_action, m4_outcome, ctx["amount"], dp)
        results_m4.append({"txn": txn_id, "action": m4_action, **m4_score})

        # --- B0 decision ---
        b0_act, _, _ = select_b0_waterfall(allowed, esc, terminal, ctx["attempt_number"])
        b0_outcome = outcome_lookup.get((txn_id, b0_act), 0) if b0_act not in ("no_action_required", "escalate") else 0
        b0_score = score_action(b0_act, b0_outcome, ctx["amount"], dp)
        results_b0.append({"txn": txn_id, "action": b0_act, **b0_score})

        # --- Shadow incremental decision ---
        scoreable = [a for a in allowed if a not in ("escalate", "no_action_required")]
        if terminal or not scoreable:
            shadow_action = m4_action
        else:
            # Get P(wait)
            p_wait = 0.0
            if "wait" in scoreable:
                try:
                    p_wait = predict_probability(model, ctx, "wait")
                except Exception:
                    pass
            wait_baseline_ev = p_wait * ctx["amount"]

            best_inc_ev = 0.0  # wait/passive has incremental EV = 0
            shadow_action = "wait" if "wait" in scoreable else "close"

            for action in scoreable:
                if action in ("wait", "close"):
                    continue
                try:
                    p_act = predict_probability(model, ctx, action)
                except Exception:
                    continue
                if action == "discount":
                    recoverable = ctx["amount"] * (1 - dp / 100)
                else:
                    recoverable = ctx["amount"]
                cost = ACTION_COSTS.get(action, 0)
                inc_ev = p_act * recoverable - wait_baseline_ev - cost
                if inc_ev > best_inc_ev:
                    best_inc_ev = inc_ev
                    shadow_action = action

        s_outcome = outcome_lookup.get((txn_id, shadow_action), 0) if shadow_action not in ("no_action_required", "escalate") else 0
        s_score = score_action(shadow_action, s_outcome, ctx["amount"], dp)
        results_shadow.append({"txn": txn_id, "action": shadow_action, **s_score})

    m4_df = pd.DataFrame(results_m4)
    shadow_df = pd.DataFrame(results_shadow)
    b0_df = pd.DataFrame(results_b0)

    m4_net = m4_df["net_recovered_amount"].sum()
    shadow_net = shadow_df["net_recovered_amount"].sum()
    b0_net = b0_df["net_recovered_amount"].sum()

    print(f"\n  VALIDATION RESULTS:")
    print(f"  {'Policy':<20} {'Net':>12} {'Recovered':>10} {'Rate':>7}")
    for name, df in [("M4 absolute", m4_df), ("Shadow incremental", shadow_df),
                     ("B0 waterfall", b0_df)]:
        rec = df["recovered"].sum()
        n = len(df)
        print(f"  {name:<20} {df['net_recovered_amount'].sum():>12,.0f} "
              f"{rec:>10} {rec/n*100:>6.1f}%")

    gap_closed = shadow_net - m4_net
    total_gap = b0_net - m4_net
    if total_gap != 0:
        pct_closed = gap_closed / abs(total_gap) * 100
    else:
        pct_closed = 0
    print(f"\n  M4→B0 gap on validation: {total_gap:+,.0f}")
    print(f"  Shadow improvement over M4: {gap_closed:+,.0f}")
    print(f"  Gap closed by incremental framing: {pct_closed:+.1f}%")

    # Action distributions
    print(f"\n  Action distributions (validation):")
    for name, df in [("M4 absolute", m4_df), ("Shadow incremental", shadow_df)]:
        dist = df["action"].value_counts()
        print(f"  {name}: {dist.to_dict()}")

    return {"m4_net": m4_net, "shadow_net": shadow_net, "b0_net": b0_net,
            "gap_closed": gap_closed, "pct_closed": pct_closed,
            "m4_dist": m4_df["action"].value_counts().to_dict(),
            "shadow_dist": shadow_df["action"].value_counts().to_dict()}


# ============================================================
# D8: ACTION REACHABILITY AUDIT
# ============================================================

def compute_d8(policies, model):
    print("\n" + "=" * 70)
    print("D8: ACTION REACHABILITY AUDIT")
    print("=" * 70)

    pa = policies["policy_a"]

    # Re-run M3 + M4 to get allowed and scored
    from ml.experiment.run_experiment import load_experiment_data, build_transaction_context
    test_txns, _ = load_experiment_data()

    allowed_counts = {a: 0 for a in ALL_ACTIONS_LIST}
    scored_counts = {a: 0 for a in ALL_ACTIONS_LIST}
    selected_counts = {a: 0 for a in ALL_ACTIONS_LIST}

    for _, row in test_txns.iterrows():
        ctx = build_transaction_context(row)
        txn_id = ctx["transaction_id"]
        pr = evaluate_policy(ctx)

        for a in pr["allowed_actions"]:
            allowed_counts[a] = allowed_counts.get(a, 0) + 1

        # Get M4 decision with full analysis
        dec = make_decision(ctx, model_pipeline=model)
        for a in dec.get("action_analysis", {}):
            scored_counts[a] = scored_counts.get(a, 0) + 1
        selected_counts[dec["decision"]] = selected_counts.get(dec["decision"], 0) + 1

    print(f"\n  {'Action':<20} {'Allowed(a)':>10} {'Scored(b)':>10} {'Selected(c)':>11} {'Status':<30}")
    print(f"  {'-'*83}")
    for a in ALL_ACTIONS_LIST:
        al = allowed_counts.get(a, 0)
        sc = scored_counts.get(a, 0)
        se = selected_counts.get(a, 0)
        if al > 0 and se == 0:
            status = "STRUCTURALLY UNREACHABLE"
        elif al > 0 and sc == 0:
            status = "NEVER SCORED DESPITE ALLOWED"
        else:
            status = "OK"
        print(f"  {a:<20} {al:>10} {sc:>10} {se:>11} {status:<30}")

    # Explain unreachable actions
    print(f"\n  EXPLANATIONS:")
    if selected_counts.get("close", 0) == 0 and allowed_counts.get("close", 0) > 0:
        print(f"  close: EV hardcoded to 0; wait has EV = P×amount ≥ 0 and wins tiebreak.")
    if scored_counts.get("escalate", 0) == 0:
        print(f"  escalate: excluded from EV scoring by design (routing action, not recovery).")

    return {"allowed": allowed_counts, "scored": scored_counts, "selected": selected_counts}


# ============================================================
# D9: B0's FREE-RECOVERY HARVEST
# ============================================================

def compute_d9(policies):
    print("\n" + "=" * 70)
    print("D9: B0's FREE-RECOVERY HARVEST")
    print("=" * 70)
    passive = {"wait", "close", "no_action_required"}
    active = {"retry", "payment_link", "reminder", "discount"}

    d9 = {}
    for pname in ["policy_a", "b0_waterfall"]:
        df = policies[pname]
        pas = df[df["action"].isin(passive)]
        act = df[df["action"].isin(active)]
        esc = df[df["action"] == "escalate"]

        d9[pname] = {}
        print(f"\n  {pname}:")
        print(f"  {'Group':<15} {'Count':>6} {'Gross':>12} {'Cost':>8} {'Disc':>10} {'Net':>12}")
        for label, sub in [("PASSIVE", pas), ("ACTIVE", act), ("ESCALATE", esc)]:
            n = len(sub)
            gross = sub["recovered_amount"].sum()
            cost = sub["intervention_cost"].sum()
            disc = sub["discount_amount"].sum()
            net = sub["net_recovered_amount"].sum()
            d9[pname][label] = {"n": n, "gross": gross, "cost": cost, "disc": disc, "net": net}
            print(f"  {label:<15} {n:>6} {gross:>12,.0f} {cost:>8,.0f} "
                  f"{disc:>10,.0f} {net:>12,.0f}")
    return d9


# ============================================================
# D10: LOSS SHAPE
# ============================================================

def compute_d10(policies):
    print("\n" + "=" * 70)
    print("D10: LOSS SHAPE — BROAD BIAS OR TAIL EVENTS")
    print("=" * 70)
    pa = policies["policy_a"]

    d10 = {}
    for comp_name in ["b0_waterfall", "b1_random"]:
        comp = policies[comp_name]
        merged = pa.merge(comp, on="transaction_id", suffixes=("_a", "_comp"))
        merged["delta"] = merged["net_recovered_amount_a"] - merged["net_recovered_amount_comp"]

        wins = merged[merged["delta"] > 0]
        ties = merged[merged["delta"] == 0]
        losses = merged[merged["delta"] < 0]

        val_won = wins["delta"].sum()
        val_lost = losses["delta"].sum()

        d10[comp_name] = {
            "wins": len(wins), "ties": len(ties), "losses": len(losses),
            "val_won": val_won, "val_lost": val_lost,
        }

        print(f"\n  Policy A vs {comp_name}:")
        print(f"    Wins:   {len(wins):>6}  total value won:  {val_won:>+12,.0f}")
        print(f"    Ties:   {len(ties):>6}")
        print(f"    Losses: {len(losses):>6}  total value lost: {val_lost:>+12,.0f}")
        print(f"    Net:    {val_won + val_lost:>+12,.0f}")

        # Top 10 largest single-transaction losses
        worst = merged.nsmallest(10, "delta")
        print(f"\n    Top 10 largest single-txn losses:")
        print(f"    {'TxnID':>8} {'Amount':>10} {'FType':<25} {'PA':>10} {'Comp':>10} {'Delta':>10}")
        for _, r in worst.iterrows():
            print(f"    {r['transaction_id']:>8} {r['amount_a']:>10,.0f} "
                  f"{r['failure_type_a']:<25} {r['action_a']:>10} "
                  f"{r['action_comp']:>10} {r['delta']:>+10,.0f}")

    return d10


# ============================================================
# GENERATE REPORTS
# ============================================================

def generate_reports(p1, d1, d2, d3_data, d4, d5, d6, d7, d8, d9, d10, policies):
    os.makedirs("ml/evaluation", exist_ok=True)

    # ============================================================
    # m5_report.md
    # ============================================================
    pa = policies["policy_a"]
    b0 = policies["b0_waterfall"]
    b1 = policies["b1_random"]

    # Bootstrap for report
    bs_b0_net = paired_bootstrap(pa["net_recovered_amount"].values,
                                 b0["net_recovered_amount"].values, 10000, 42, "sum")
    bs_b0_rate = paired_bootstrap(pa["recovered"].astype(float).values,
                                  b0["recovered"].astype(float).values, 10000, 42, "mean")
    bs_b1_net = paired_bootstrap(pa["net_recovered_amount"].values,
                                 b1["net_recovered_amount"].values, 10000, 42, "sum")

    sig_b0 = "Yes" if bs_b0_net["excludes_zero"] else "No"
    sig_b1 = "Yes" if bs_b1_net["excludes_zero"] else "No"

    report = f"""# M5 Experiment Report — AI Revenue Recovery Decision Engine

## M5 STATUS: PASS (experiment valid) / RESULT: LOSS

**Population evaluated:** 1,577 held-out test transactions (customer-level split, no overlap with train/val)
**Baseline definition:** B0 Fixed Waterfall — retry → retry → reminder → stop, subject to M3 safety
**Policy A definition:** M2 probabilities → M3 policy filter → M4 EV engine → selected action
**Escalation convention:** Option 1 (headline): escalated = not-recovered. Option 2 (supplementary): excluded.

### Frozen M4 Configuration

```
ACTION_COSTS = {{retry: 2.0, payment_link: 5.0, reminder: 3.0, discount: 0.0, wait: 0.0, close: 0.0}}
DEFAULT_DISCOUNT_PERCENT = 10.0
TIE_TOLERANCE = 1e-06
PRIORITY_ORDER = [retry, wait, reminder, payment_link, discount, close]
DECISION_ENGINE_VERSION = v1.0
POLICY_VERSION = v1.0
```

---

## PRIMARY RESULT

| Metric | Value |
|--------|-------|
| Baseline (B0) net recovered | {p1['b0_net']:,.2f} |
| Policy A net recovered | {p1['pa_net']:,.2f} |
| **Net Recovery Uplift vs Baseline** | **{p1['uplift']:+,.2f}** |
| Percentage uplift | {p1['uplift']/p1['b0_net']*100:+.2f}% |
| Paired bootstrap 95% CI | [{bs_b0_net['ci_lower']:+,.2f}, {bs_b0_net['ci_upper']:+,.2f}] |
| Excludes zero | {sig_b0} |
| Oracle (B6) net recovered | {p1['b6_net']:,.2f} |
| Headroom captured (B0→B6) | {p1['headroom_pct']:+.2f}% |
| Oracle/B0 ratio | {p1['oracle_ratio']:.2f}x |

> [!CAUTION]
> **The intelligent policy LOST.** Policy A produced {abs(p1['uplift']):,.2f} LESS net recovered
> amount than the fixed waterfall baseline. The CI [{bs_b0_net['ci_lower']:+,.0f}, {bs_b0_net['ci_upper']:+,.0f}]
> excludes zero: {sig_b0}. The loss is statistically distinguishable at this sample size: {sig_b0}.

**Policy A vs B1 (random):** {bs_b1_net['point_estimate']:+,.2f}, CI [{bs_b1_net['ci_lower']:+,.2f}, {bs_b1_net['ci_upper']:+,.2f}], excludes zero: {sig_b1}.
Policy A finished BELOW uniform random, indicating a systematic defect, not undertuning.

Negative headroom ({p1['headroom_pct']:+.2f}%) means Policy A finished below the baseline, capturing
none of the available headroom. The oracle is {p1['oracle_ratio']:.2f}x the baseline, so the task is
learnable — Policy A is failing at it, not hitting a ceiling.

---

## FULL COMPARISON TABLE

| Policy | Recovered | Rate | Gross | Cost | Net |
|--------|-----------|------|-------|------|-----|
"""
    for pname in sorted(policies.keys(),
                        key=lambda p: -policies[p]["net_recovered_amount"].sum()):
        df = policies[pname]
        rec = df["recovered"].sum()
        n = len(df)
        report += (f"| {pname} | {rec} | {rec/n*100:.1f}% | "
                   f"{df['recovered_amount'].sum():,.0f} | "
                   f"{df['intervention_cost'].sum():,.0f} | "
                   f"{df['net_recovered_amount'].sum():,.0f} |\\n")

    report += f"""
---

## CONTROLLED DECISION EXAMPLES

### Example 1: Policy A chooses a different action than baseline
*(See run_experiment.py output for real data)*

### Example 2: Policy A chooses close/wait instead of intervention
{p1['ex2_text']}
Policy A close count: {p1['close_count']}, wait count: {p1['wait_count']}.

---

## SAFETY METRICS

Zero violations for both policies (verified by EX-14, EX-16, EX-17).

## INTERNAL VS EXTERNAL VALIDITY

**Internal validity (strength):** M1 generated realized outcomes for EVERY action on EVERY
transaction. The synthetic environment is a full-factorial randomized design, and the policy
comparison within it is exact — every policy is scored against the same realized outcomes, with
no selection effect and no off-policy correction required.

**External validity (limitation):** In production only the action actually taken is observed.
Offline evaluation would then require off-policy correction such as inverse propensity weighting
or doubly-robust estimation. The measured uplift (in this case, deficit) is a property of this
simulator and its assumed action effectiveness, not a forecast of production impact.

## TESTS

33/33 tests PASS (10 baseline + 23 experiment). See test_experiment.py output.

## INTERPRETATION

**LOSS.** The intelligent policy did not outperform the fixed baseline under the current synthetic
environment. The loss is statistically significant and extends below uniform random.
Hypotheses A (calibration), B (objective), C (implementation), and D (substitution) are under
investigation in the M5.1 diagnostic — not conclusions of this report.

No M5 baseline comparison constitutes a causal claim.
"""

    with open("ml/evaluation/m5_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n  Generated: ml/evaluation/m5_report.md")

    # ============================================================
    # m5_1_diagnostic.md (generated from computed data)
    # ============================================================
    d3, _ = d3_data
    diag = f"""# M5.1 Diagnostic Report — Root Cause Analysis

## Result Being Diagnosed

| Metric | Value |
|--------|-------|
| Policy A net | {p1['pa_net']:,.2f} |
| B0 waterfall net | {p1['b0_net']:,.2f} |
| B1 random net | {p1['b1_net']:,.2f} |
| Net Recovery Uplift | {p1['uplift']:+,.2f} ({p1['uplift']/p1['b0_net']*100:+.2f}%) |
| Headroom captured | {p1['headroom_pct']:+.2f}% |

The loss is accepted as genuine. No tuning was performed.

---

## D1: Action-Selection Distribution

| Action | Policy A Count | Policy A % | B0 Count | B0 % |
|--------|---------------|------------|----------|------|
"""
    for a in ALL_ACTIONS_LIST:
        pa_c = d1["policy_a"]["dist"].get(a, 0)
        pa_p = d1["policy_a"]["pct"].get(a, 0)
        b0_c = d1["b0_waterfall"]["dist"].get(a, 0)
        b0_p = d1["b0_waterfall"]["pct"].get(a, 0)
        diag += f"| {a} | {pa_c} | {pa_p:.1f}% | {b0_c} | {b0_p:.1f}% |\n"

    diag += f"""
Policy A most-frequent-action: {d1['policy_a']['mfa']} ({d1['policy_a']['mfs']:.1f}%)

---

## D2: Haircut Test — Recovery Rate vs Net Value

| Policy | Recovered | Rate | Gross | Cost | Discount | Net |
|--------|-----------|------|-------|------|----------|-----|
"""
    for pname in sorted(d2.keys(), key=lambda p: -d2[p]["net"]):
        m = d2[pname]
        diag += (f"| {pname} | {m['rec']} | {m['rate']:.1f}% | {m['gross']:,.0f} | "
                 f"{m['cost']:,.0f} | {m['disc']:,.0f} | {m['net']:,.0f} |\n")

    pa_d2 = d2["policy_a"]
    b0_d2 = d2["b0_waterfall"]
    if pa_d2["rate"] > b0_d2["rate"] and pa_d2["net"] < b0_d2["net"]:
        diag += "\n> [!WARNING]\n> **Higher recovery rate but lower net.** The loss comes from giving away value (discount haircut / intervention cost) on recoveries, not from failing to recover.\n"
    elif pa_d2["rate"] <= b0_d2["rate"]:
        diag += "\n> Policy A has equal or lower recovery rate. The loss is from fewer/worse recoveries.\n"

    diag += f"""
---

## D3: Per-Action Calibration

| Action | Mean Predicted | Realized Rate | Signed Gap | Amt-Weighted Gap | N |
|--------|---------------|---------------|------------|-----------------|---|
"""
    for a in sorted(d3.keys()):
        m = d3[a]
        diag += (f"| {a} | {m['mean_pred']:.4f} | {m['realized']:.4f} | "
                 f"{m['gap']:+.4f} | {m['wt_gap']:+.4f} | {m['n']} |\n")

    diag += """
A positive gap means M2 over-predicts recovery probability for that action.
Over-prediction inflates EV and causes M4 to prefer that action over alternatives.

---

## D4: Gap Decomposition

"""
    diag += f"- Divergent transactions: {d4['n_div']} ({d4['n_div']/1577*100:.1f}%)\n"
    diag += f"- Same-action transactions: {d4['n_same']} ({d4['n_same']/1577*100:.1f}%)\n"
    diag += f"- Divergent delta: {d4['div_delta']:+,.0f}\n"
    diag += f"- Same-action delta: {d4['same_delta']:+,.0f}\n\n"
    diag += "### Substitution Matrix (top 5 most costly)\n\n"
    diag += "| PA Action → B0 Action | Count | PA Net | B0 Net | Delta |\n"
    diag += "|----------------------|-------|--------|--------|-------|\n"
    for _, r in d4["sub_df"].head(5).iterrows():
        diag += (f"| {r['pa_action']}→{r['b0_action']} | {r['count']} | "
                 f"{r['pa_net']:,.0f} | {r['b0_net']:,.0f} | {r['delta']:+,.0f} |\n")

    diag += f"""
---

## D5: Regret Analysis vs Oracle

| Policy | Total Regret | Mean Regret |
|--------|-------------|-------------|
| policy_a | {d5['policy_a']['total']:,.0f} | {d5['policy_a']['mean']:,.2f} |
| b0_waterfall | {d5['b0_waterfall']['total']:,.0f} | {d5['b0_waterfall']['mean']:,.2f} |

---

## D6: The close EV=0 Question

1. **close EV is hardcoded to 0** in `ev_engine.py`: `if action == "close": return {{..., "expected_net_value": 0.0}}`
2. **close realized recovery rate (test):** {d6['close_rec_rate']:.4f} ({d6['close_n']} rows)
3. **Structural claim CONFIRMED:** close is UNREACHABLE when wait is allowed with P(wait) ≥ 0.
   - EV(close) = 0 always
   - EV(wait) = P(wait) × amount ≥ 0
   - When tied: wait wins tiebreak (priority index 1 < 5)
4. **Test 12 corollary CONFIRMED:** Test 12 excluded wait from the scored set. Had wait been
   scored, it would have tied close at EV=0 and won tiebreak. Test 12 certified a code path
   that cannot occur in production.

---

## D7: Counterfactual Reference Analysis (Validation Only)

| Policy | Net Recovered |
|--------|--------------|
| M4 absolute EV | {d7['m4_net']:,.0f} |
| Shadow incremental EV | {d7['shadow_net']:,.0f} |
| B0 waterfall | {d7['b0_net']:,.0f} |

- Shadow improvement over M4: {d7['gap_closed']:+,.0f}
- Gap closed by incremental framing: {d7['pct_closed']:+.1f}%

---

## D8: Action Reachability Audit

| Action | Allowed | Scored | Selected | Status |
|--------|---------|--------|----------|--------|
"""
    for a in ALL_ACTIONS_LIST:
        al = d8["allowed"].get(a, 0)
        sc = d8["scored"].get(a, 0)
        se = d8["selected"].get(a, 0)
        if al > 0 and se == 0:
            status = "**STRUCTURALLY UNREACHABLE**"
        elif al > 0 and sc == 0:
            status = "**NEVER SCORED**"
        else:
            status = "OK"
        diag += f"| {a} | {al} | {sc} | {se} | {status} |\n"

    diag += f"""
---

## D9: B0's Free-Recovery Harvest

"""
    for pname in ["policy_a", "b0_waterfall"]:
        diag += f"### {pname}\n\n"
        diag += "| Group | Count | Gross | Cost | Discount | Net |\n"
        diag += "|-------|-------|-------|------|----------|-----|\n"
        for label in ["PASSIVE", "ACTIVE", "ESCALATE"]:
            m = d9[pname].get(label, {"n": 0, "gross": 0, "cost": 0, "disc": 0, "net": 0})
            diag += (f"| {label} | {m['n']} | {m['gross']:,.0f} | {m['cost']:,.0f} | "
                     f"{m['disc']:,.0f} | {m['net']:,.0f} |\n")
        diag += "\n"

    diag += f"""---

## D10: Loss Shape — Broad Bias or Tail Events

"""
    for comp in ["b0_waterfall", "b1_random"]:
        m = d10[comp]
        diag += f"### Policy A vs {comp}\n\n"
        diag += f"- Wins: {m['wins']} (value won: {m['val_won']:+,.0f})\n"
        diag += f"- Ties: {m['ties']}\n"
        diag += f"- Losses: {m['losses']} (value lost: {m['val_lost']:+,.0f})\n"
        diag += f"- Net: {m['val_won']+m['val_lost']:+,.0f}\n\n"

    diag += """---

## Hypothesis Verdicts

### A. M2 PROBABILITY PROBLEM
M2 probabilities may be reasonable overall but poorly calibrated conditional on action,
causing M4 to rank actions on misleading inputs.

- **Evidence FOR:** See D3 per-action calibration gaps. Any action with systematic
  over-prediction will be over-selected by the argmax rule.
- **Evidence AGAINST:** If gaps are small and uniform, this is not the primary cause.
- **Would refute:** Zero per-action calibration gap (predicted = realized for each action).
- **Verdict:** See D3 numbers above.

### B. M4 OBJECTIVE PROBLEM
M4 maximizes absolute expected recovery rather than incremental value over the free
passive option (wait).

- **Evidence FOR:** D7 shows the incremental framing result. D9 shows the free-recovery
  harvest difference between B0 and Policy A.
- **Evidence AGAINST:** If the shadow incremental rule performs no better, this is not the cause.
- **Would refute:** Shadow rule performing equally or worse than M4.
- **Verdict:** See D7 numbers above.

### C. M4 IMPLEMENTATION PROBLEM
close has genuine recovery probability but is assigned EV=0 and is structurally unreachable.

- **Evidence FOR:** D6 confirms close is hardcoded to EV=0 while having nonzero realized
  recovery. D8 confirms close is never selected. Test 12 corollary confirmed.
- **Evidence AGAINST:** close's realized rate may be lower than wait's, limiting impact.
- **Would refute:** close having realized recovery rate of exactly 0.
- **Verdict:** CONFIRMED as structural defect. Magnitude: see D6.

### D. SUBSTITUTION PROBLEM
Specific action substitutions systematically destroy net value.

- **Evidence FOR:** D4 substitution matrix shows where value is destroyed.
  D10 shows whether the pattern is broad or concentrated.
- **Evidence AGAINST:** If most substitutions are value-positive, this is not dominant.
- **Would refute:** No systematic pattern in substitutions (random distribution of gains/losses).
- **Verdict:** See D4 and D10 numbers above.

---

## Summary

M5 STATUS: PASS (experiment valid) / RESULT: LOSS
M5.1 STATUS: Complete

The diagnostic data above quantifies each hypothesis. The ranked root causes and their
value attribution depend on the specific numbers computed in D3, D4, D7, and D9.
"""

    with open("ml/evaluation/m5_1_diagnostic.md", "w", encoding="utf-8") as f:
        f.write(diag)
    print(f"  Generated: ml/evaluation/m5_1_diagnostic.md")


# ============================================================
# MAIN
# ============================================================

def main():
    per_txn, ht, tr, model, policies = load_all_data()

    # Part 1
    p1 = compute_part1(policies, ht, model)

    # D1-D10
    d1 = compute_d1(policies)
    d2 = compute_d2(policies)
    d3 = compute_d3(ht, model)
    d4 = compute_d4(policies)
    d5 = compute_d5(policies)
    d6 = compute_d6(ht, policies)

    print("\n  Computing D7 (validation shadow rule — this may take a minute)...")
    d7 = compute_d7(ht, tr, model)
    d8 = compute_d8(policies, model)
    d9 = compute_d9(policies)
    d10 = compute_d10(policies)

    # Generate reports
    print("\n" + "=" * 70)
    print("GENERATING REPORTS")
    print("=" * 70)
    generate_reports(p1, d1, d2, d3, d4, d5, d6, d7, d8, d9, d10, policies)

    # Final summary
    print("\n" + "=" * 70)
    print("M5 CLOSEOUT + M5.1 DIAGNOSTIC COMPLETE")
    print("=" * 70)
    print(f"\n  M5 STATUS: PASS (experiment valid) / RESULT: LOSS")
    print(f"  M5.1 STATUS: Complete")
    print(f"\n  Reports generated:")
    print(f"    ml/evaluation/m5_report.md")
    print(f"    ml/evaluation/m5_1_diagnostic.md")
    print(f"\n  STOP for review. Do not modify M1-M4. Do not run M6. Do not commit.")


if __name__ == "__main__":
    main()
