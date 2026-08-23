"""
M2: Final Test Set Evaluation — evaluate_test_set.py
=====================================================
Loads the LOCKED model from train_model.py and evaluates on the held-out
test split. This script runs ONCE, post-lock. Do not use test results
to tune the model.

Produces:
  - Model metrics (ROC-AUC, PR-AUC, Log Loss, Brier Score, Accuracy)
  - Calibration decile table
  - Action-conditional proof table (3+ required cases)
  - Breakdown by action and failure_type
  - Action comparison CSV
  - All saved to ml/evaluation/

Usage:
    python evaluate_test_set.py
"""

import json
import os
import warnings

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    log_loss,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

# ============================================================
# 0. CONFIGURATION
# ============================================================

DATA_PATH = "action_expanded_training_data.csv"
MODEL_PATH = os.path.join("ml", "models", "recovery_model.joblib")
EVAL_DIR = os.path.join("ml", "evaluation")

LOG1P_FIELDS = ["amount", "lifetime_successful_txns", "lifetime_failed_txns"]
TARGET = "outcome"

CATEGORICAL_FEATURES = [
    "failure_type",
    "action",
    "segment",
    "payment_method",
    "failure_action",
    "segment_action",
]

# M1 eligibility matrix (for action-conditional proof table)
ELIGIBILITY = {
    "temporary_bank_decline": {"retry", "payment_link", "reminder", "discount", "wait", "close"},
    "network_timeout":        {"retry", "payment_link", "reminder", "wait", "close"},
    "card_expired":           {"payment_link", "reminder", "discount", "wait", "close"},
    "risk_block":             {"wait", "close"},
    "customer_abandoned":     {"payment_link", "reminder", "discount", "wait", "close"},
    "subscription_mandate_fail": {"payment_link", "reminder", "discount", "wait", "close"},
    "insufficient_funds":     {"retry", "reminder", "payment_link", "wait", "close"},
}


# ============================================================
# 1. LOAD DATA + MODEL
# ============================================================

def prepare_features(df):
    """Apply log1p transforms."""
    df = df.copy()
    df["log1p_amount"] = np.log1p(df["amount"])
    df["log1p_lifetime_successful_txns"] = np.log1p(df["lifetime_successful_txns"])
    df["log1p_lifetime_failed_txns"] = np.log1p(df["lifetime_failed_txns"])
    return df


def get_feature_columns():
    numeric_final = [
        "risk_score",
        "attempt_number",
        "contact_fatigue_score",
        "log1p_amount",
        "log1p_lifetime_successful_txns",
        "log1p_lifetime_failed_txns",
    ]
    return CATEGORICAL_FEATURES + numeric_final


def load_data_and_model():
    print("=" * 70)
    print("LOADING MODEL AND TEST DATA")
    print("=" * 70)

    pipeline = joblib.load(MODEL_PATH)
    print(f"  Model loaded: {MODEL_PATH}")

    df = pd.read_csv(DATA_PATH)
    df = prepare_features(df)

    df_test = df[df["split"] == "test"].copy()
    print(f"  Test split: {len(df_test)} rows, {df_test['transaction_id'].nunique()} transactions, "
          f"{df_test['customer_id'].nunique()} customers")

    feature_cols = get_feature_columns()
    X_test = df_test[feature_cols]
    y_test = df_test[TARGET].values

    y_prob = pipeline.predict_proba(X_test)[:, 1]
    y_pred = pipeline.predict(X_test)

    df_test = df_test.copy()
    df_test["predicted_prob"] = y_prob
    df_test["predicted_class"] = y_pred

    return pipeline, df, df_test, X_test, y_test, y_prob, y_pred


# ============================================================
# 2. MODEL METRICS
# ============================================================

def compute_metrics(y_test, y_prob, y_pred):
    print("\n" + "=" * 70)
    print("MODEL METRICS (test set)")
    print("=" * 70)

    metrics = {
        "roc_auc": round(roc_auc_score(y_test, y_prob), 4),
        "pr_auc": round(average_precision_score(y_test, y_prob), 4),
        "log_loss": round(log_loss(y_test, y_prob), 4),
        "brier_score": round(brier_score_loss(y_test, y_prob), 4),
        "accuracy": round(accuracy_score(y_test, y_pred), 4),
    }

    for name, value in metrics.items():
        print(f"  {name}: {value}")

    return metrics


# ============================================================
# 3. CALIBRATION TABLE
# ============================================================

def calibration_table(y_test, y_prob):
    print("\n" + "=" * 70)
    print("CALIBRATION TABLE (deciles)")
    print("=" * 70)

    df_cal = pd.DataFrame({"y_true": y_test, "y_prob": y_prob})
    df_cal["bucket"] = pd.qcut(df_cal["y_prob"], q=10, duplicates="drop")

    table = df_cal.groupby("bucket", observed=True).agg(
        count=("y_true", "count"),
        mean_predicted=("y_prob", "mean"),
        actual_rate=("y_true", "mean"),
    ).reset_index()

    table["bucket"] = table["bucket"].astype(str)
    table["mean_predicted"] = table["mean_predicted"].round(4)
    table["actual_rate"] = table["actual_rate"].round(4)
    table["gap"] = (table["actual_rate"] - table["mean_predicted"]).round(4)

    print(table.to_string(index=False))

    # Summary assessment
    avg_gap = table["gap"].abs().mean()
    print(f"\n  Mean absolute calibration gap: {avg_gap:.4f}")
    if avg_gap < 0.03:
        print("  Assessment: WELL CALIBRATED")
    elif avg_gap < 0.06:
        print("  Assessment: REASONABLY CALIBRATED")
    else:
        print("  Assessment: CALIBRATION NEEDS IMPROVEMENT")

    return table


# ============================================================
# 4. ACTION-CONDITIONAL PROOF TABLE
# ============================================================

def action_conditional_proof(pipeline, df_test):
    """For several real transactions, hold context fixed, vary action,
    show predicted recovery probability per eligible action."""
    print("\n" + "=" * 70)
    print("ACTION-CONDITIONAL PROOF (test set)")
    print("=" * 70)
    print("(For each transaction, context is fixed; only action varies.)")

    feature_cols = get_feature_columns()

    # Select one transaction each for the 3 required failure types
    required_fts = ["card_expired", "subscription_mandate_fail", "temporary_bank_decline"]

    # Also add examples for diversity if available
    optional_fts = ["network_timeout", "customer_abandoned", "risk_block"]

    all_proof_rows = []

    for ft in required_fts + optional_fts:
        ft_txns = df_test[df_test["failure_type"] == ft]["transaction_id"].unique()
        if len(ft_txns) == 0:
            print(f"\n  WARNING: No test transactions for {ft} — skipping")
            continue

        # Pick the first available transaction
        txn_id = ft_txns[0]
        txn_rows = df_test[df_test["transaction_id"] == txn_id]
        base_row = txn_rows.iloc[0]

        eligible_actions = sorted(ELIGIBILITY[ft])

        print(f"\n  Transaction {txn_id} — failure_type: {ft}")
        print(f"    segment={base_row['segment']}, risk_score={base_row['risk_score']:.4f}, "
              f"amount={base_row['amount']:.2f}, attempt={base_row['attempt_number']}, "
              f"payment={base_row['payment_method']}")
        print(f"    {'Action':<15} {'P(recovery)':<12}")
        print(f"    {'-'*27}")

        for action in eligible_actions:
            # Build a synthetic row with this action
            row_data = base_row.copy()
            row_data["action"] = action
            row_data["failure_action"] = f"{ft}__{action}"
            row_data["segment_action"] = f"{base_row['segment']}__{action}"

            row_df = pd.DataFrame([row_data])[feature_cols]
            prob = pipeline.predict_proba(row_df)[:, 1][0]

            print(f"    {action:<15} {prob:.4f}")
            all_proof_rows.append({
                "transaction_id": txn_id,
                "failure_type": ft,
                "segment": base_row["segment"],
                "risk_score": round(base_row["risk_score"], 4),
                "amount": round(base_row["amount"], 2),
                "attempt_number": base_row["attempt_number"],
                "payment_method": base_row["payment_method"],
                "action": action,
                "predicted_prob": round(prob, 4),
            })

    proof_df = pd.DataFrame(all_proof_rows)
    return proof_df


# ============================================================
# 5. BREAKDOWN ANALYSIS
# ============================================================

def breakdown_analysis(df_test, y_test, y_prob):
    print("\n" + "=" * 70)
    print("BREAKDOWN ANALYSIS (test set)")
    print("=" * 70)

    df_eval = df_test.copy()
    df_eval["y_true"] = y_test
    df_eval["y_prob"] = y_prob

    # --- By action ---
    print("\n  BY ACTION:")
    print(f"  {'Action':<15} {'Count':>6} {'AUC':>7} {'Brier':>7} {'RecRate':>8}")
    print(f"  {'-'*45}")
    action_results = []
    for action in sorted(df_eval["action"].unique()):
        mask = df_eval["action"] == action
        sub = df_eval[mask]
        count = len(sub)
        try:
            auc = roc_auc_score(sub["y_true"], sub["y_prob"])
        except ValueError:
            auc = float("nan")
        brier = brier_score_loss(sub["y_true"], sub["y_prob"])
        rec_rate = sub["y_true"].mean()
        print(f"  {action:<15} {count:>6} {auc:>7.4f} {brier:>7.4f} {rec_rate:>8.4f}")
        action_results.append({
            "action": action,
            "count": count,
            "auc": round(auc, 4),
            "brier": round(brier, 4),
            "recovery_rate": round(rec_rate, 4),
        })

    # --- By failure_type ---
    print(f"\n  BY FAILURE_TYPE:")
    print(f"  {'Failure Type':<30} {'Count':>6} {'AUC':>7} {'Brier':>7} {'RecRate':>8}")
    print(f"  {'-'*60}")
    ft_results = []
    for ft in sorted(df_eval["failure_type"].unique()):
        mask = df_eval["failure_type"] == ft
        sub = df_eval[mask]
        count = len(sub)
        try:
            auc = roc_auc_score(sub["y_true"], sub["y_prob"])
        except ValueError:
            auc = float("nan")
        brier = brier_score_loss(sub["y_true"], sub["y_prob"])
        rec_rate = sub["y_true"].mean()
        print(f"  {ft:<30} {count:>6} {auc:>7.4f} {brier:>7.4f} {rec_rate:>8.4f}")
        ft_results.append({
            "failure_type": ft,
            "count": count,
            "auc": round(auc, 4),
            "brier": round(brier, 4),
            "recovery_rate": round(rec_rate, 4),
        })

    return pd.DataFrame(action_results), pd.DataFrame(ft_results)


# ============================================================
# 6. PLOTS
# ============================================================

def generate_plots(y_test, y_prob, cal_table):
    """Generate evaluation plots."""
    os.makedirs(EVAL_DIR, exist_ok=True)

    # ROC Curve
    fpr, tpr, _ = roc_curve(y_test, y_prob)
    auc = roc_auc_score(y_test, y_prob)
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(fpr, tpr, label=f"LogReg (AUC={auc:.4f})", linewidth=2)
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Random")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC Curve — Action-Conditional LogReg")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(EVAL_DIR, "roc_curve.png"), dpi=150)
    plt.close()

    # PR Curve
    precision, recall, _ = precision_recall_curve(y_test, y_prob)
    pr_auc = average_precision_score(y_test, y_prob)
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(recall, precision, label=f"LogReg (PR-AUC={pr_auc:.4f})", linewidth=2)
    baseline = y_test.mean()
    ax.axhline(y=baseline, color="gray", linestyle="--", alpha=0.5, label=f"Baseline ({baseline:.3f})")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision-Recall Curve — Action-Conditional LogReg")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(EVAL_DIR, "pr_curve.png"), dpi=150)
    plt.close()

    # Calibration plot
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Perfect calibration")
    ax.plot(cal_table["mean_predicted"], cal_table["actual_rate"],
            "o-", linewidth=2, markersize=8, label="Model")
    ax.set_xlabel("Mean Predicted Probability")
    ax.set_ylabel("Actual Recovery Rate")
    ax.set_title("Calibration Plot — Action-Conditional LogReg")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(EVAL_DIR, "calibration_curve.png"), dpi=150)
    plt.close()

    print(f"\n  Plots saved to {EVAL_DIR}/")


# ============================================================
# 7. SAVE ALL OUTPUTS
# ============================================================

def save_outputs(metrics, cal_table, proof_df, action_breakdown, ft_breakdown):
    os.makedirs(EVAL_DIR, exist_ok=True)

    # Metrics JSON
    with open(os.path.join(EVAL_DIR, "model_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    # Calibration JSON
    cal_dict = cal_table.to_dict(orient="records")
    with open(os.path.join(EVAL_DIR, "calibration_results.json"), "w") as f:
        json.dump(cal_dict, f, indent=2, default=str)

    # Action comparison CSV
    proof_df.to_csv(os.path.join(EVAL_DIR, "action_comparison.csv"), index=False)

    # Breakdown CSVs
    action_breakdown.to_csv(os.path.join(EVAL_DIR, "breakdown_by_action.csv"), index=False)
    ft_breakdown.to_csv(os.path.join(EVAL_DIR, "breakdown_by_failure_type.csv"), index=False)

    print(f"\n  All evaluation outputs saved to {EVAL_DIR}/")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    # 1. Load
    pipeline, df_full, df_test, X_test, y_test, y_prob, y_pred = load_data_and_model()

    # 2. Metrics
    metrics = compute_metrics(y_test, y_prob, y_pred)

    # 3. Calibration
    cal_table = calibration_table(y_test, y_prob)

    # 4. Action-conditional proof
    proof_df = action_conditional_proof(pipeline, df_test)

    # 5. Breakdowns
    action_breakdown, ft_breakdown = breakdown_analysis(df_test, y_test, y_prob)

    # 6. Plots
    generate_plots(y_test, y_prob, cal_table)

    # 7. Save
    save_outputs(metrics, cal_table, proof_df, action_breakdown, ft_breakdown)

    # 8. Final summary
    print("\n" + "=" * 70)
    print("M2 EVALUATION COMPLETE")
    print("=" * 70)
    print(f"\n  ROC-AUC:     {metrics['roc_auc']}")
    print(f"  PR-AUC:      {metrics['pr_auc']}")
    print(f"  Log Loss:    {metrics['log_loss']}")
    print(f"  Brier Score: {metrics['brier_score']}")
    print(f"  Accuracy:    {metrics['accuracy']}")
    print(f"\n  All outputs in: {EVAL_DIR}/")
    print(f"\n  DO NOT use these results to re-tune the model.")
    print("=" * 70)
