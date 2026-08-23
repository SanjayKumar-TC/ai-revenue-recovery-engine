"""
M2: Action-Conditional Logistic Regression — train_model.py
=============================================================
Trains ONE Logistic Regression model:
    P(recovery | context, action)

Action is a feature, not a separate model.
Uses scikit-learn Pipeline + ColumnTransformer.
Selects hyperparameters on validation split only.
Test split is never touched here.

Usage:
    python train_model.py
"""

import json
import os
import warnings
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

# ============================================================
# 0. CONFIGURATION
# ============================================================

DATA_PATH = "action_expanded_training_data.csv"
MODEL_DIR = os.path.join("ml", "models")
RANDOM_STATE = 42

# Hyperparameter grid (validation-selected)
C_VALUES = [0.01, 0.1, 1.0, 10.0]
CLASS_WEIGHT_OPTIONS = [None, "balanced"]

# Features — LOCKED per spec
CATEGORICAL_FEATURES = [
    "failure_type",
    "action",
    "segment",
    "payment_method",
    "failure_action",
    "segment_action",
]

NUMERIC_RAW = [
    "risk_score",
    "attempt_number",
    "contact_fatigue_score",
    "amount",
    "lifetime_successful_txns",
    "lifetime_failed_txns",
]

# Fields that get log1p transform
LOG1P_FIELDS = ["amount", "lifetime_successful_txns", "lifetime_failed_txns"]

# Fields that should NOT appear as features (leakage / exclusion)
EXCLUDED_FIELDS = [
    "transaction_id",
    "customer_id",
    "timestamp",
    "split",
    "event_type",
    "avg_transaction_value",
    "preferred_channel",
    "latent_score",
    "true_prob_HIDDEN",
    "outcome",  # target, not a feature
]

TARGET = "outcome"

# ============================================================
# 1. LOAD AND VALIDATE DATA
# ============================================================

def load_and_validate():
    print("=" * 70)
    print("STEP 1: LOADING AND VALIDATING M1 DATA")
    print("=" * 70)

    df = pd.read_csv(DATA_PATH)
    print(f"\nLoaded {DATA_PATH}: {df.shape[0]} rows, {df.shape[1]} columns")
    print(f"Columns: {list(df.columns)}")

    # --- Schema checks ---
    required_cols = CATEGORICAL_FEATURES + NUMERIC_RAW + [TARGET, "split", "customer_id", "transaction_id"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    print(f"\nAll required columns present: PASS")

    # --- Leakage checks ---
    print("\n--- LEAKAGE CHECKS ---")
    leakage_results = {}

    # Check 1-4: Hidden/latent fields absent
    hidden_fields = ["latent_score", "true_prob_HIDDEN"]
    for field in hidden_fields:
        present = field in df.columns
        leakage_results[f"{field}_absent"] = not present
        status = "FAIL — FOUND!" if present else "PASS"
        print(f"  {field} absent from features: {status}")

    # Check 5: outcome not accidentally used as input (verified by exclusion from feature lists)
    leakage_results["outcome_not_input"] = TARGET not in CATEGORICAL_FEATURES + NUMERIC_RAW
    print(f"  outcome not in feature lists: {'PASS' if leakage_results['outcome_not_input'] else 'FAIL'}")

    # Check 6: Customer-level split verification
    train_custs = set(df[df["split"] == "train"]["customer_id"].unique())
    val_custs = set(df[df["split"] == "val"]["customer_id"].unique())
    test_custs = set(df[df["split"] == "test"]["customer_id"].unique())

    overlap_tv = train_custs & val_custs
    overlap_tt = train_custs & test_custs
    overlap_vt = val_custs & test_custs

    no_overlap = len(overlap_tv) == 0 and len(overlap_tt) == 0 and len(overlap_vt) == 0
    leakage_results["customer_split_no_overlap"] = no_overlap
    print(f"  Customer overlap train∩val: {len(overlap_tv)}")
    print(f"  Customer overlap train∩test: {len(overlap_tt)}")
    print(f"  Customer overlap val∩test: {len(overlap_vt)}")
    print(f"  Customer-level split verified: {'PASS' if no_overlap else 'FAIL'}")

    # Check 7-8: Preprocessing fitted only on train (enforced by Pipeline design below)
    leakage_results["preprocessing_train_only"] = True  # enforced by code structure
    print(f"  Preprocessing fitted only on train: PASS (enforced by Pipeline design)")

    # Check 9: No future information
    leakage_results["no_future_info"] = True
    for col in ["recovered_amount", "final_outcome", "future_"]:
        if any(col in c for c in df.columns):
            leakage_results["no_future_info"] = False
    print(f"  No future information in features: {'PASS' if leakage_results['no_future_info'] else 'FAIL'}")

    # Check 10: Excluded fields not accidentally in feature lists
    feature_set = set(CATEGORICAL_FEATURES + NUMERIC_RAW)
    excluded_in_features = feature_set & set(EXCLUDED_FIELDS)
    leakage_results["excluded_fields_absent"] = len(excluded_in_features) == 0
    if excluded_in_features:
        print(f"  Excluded fields check: FAIL — {excluded_in_features} found in feature lists!")
    else:
        print(f"  Excluded fields not in feature lists: PASS")

    # Noise absent check
    noise_cols = [c for c in df.columns if "noise" in c.lower()]
    leakage_results["noise_absent"] = len(noise_cols) == 0
    print(f"  Noise columns absent: {'PASS' if leakage_results['noise_absent'] else 'FAIL — ' + str(noise_cols)}")

    # Post-outcome info absent
    post_outcome = [c for c in df.columns if c in ["recovered_amount", "recovery_date"]]
    leakage_results["post_outcome_absent"] = len(post_outcome) == 0
    print(f"  Post-outcome info absent: {'PASS' if leakage_results['post_outcome_absent'] else 'FAIL'}")

    all_pass = all(leakage_results.values())
    if not all_pass:
        failures = [k for k, v in leakage_results.items() if not v]
        raise ValueError(f"LEAKAGE DETECTED: {failures}")
    print(f"\n  ALL LEAKAGE CHECKS: PASS ({len(leakage_results)}/{len(leakage_results)})")

    # --- Split statistics ---
    print("\n--- SPLIT STATISTICS ---")
    for split_name in ["train", "val", "test"]:
        split_df = df[df["split"] == split_name]
        n_rows = len(split_df)
        n_txns = split_df["transaction_id"].nunique()
        n_custs = split_df["customer_id"].nunique()
        recovery_rate = split_df[TARGET].mean()
        print(f"  {split_name}: {n_rows} rows, {n_txns} transactions, {n_custs} customers, "
              f"recovery rate={recovery_rate:.4f}")

    # --- Class balance ---
    print("\n--- CLASS BALANCE ---")
    print(f"  Overall recovery rate: {df[TARGET].mean():.4f}")
    print(f"  Outcome distribution:\n{df[TARGET].value_counts().to_string()}")

    return df, leakage_results


# ============================================================
# 2. FEATURE ENGINEERING + PIPELINE
# ============================================================

def build_pipeline(C, class_weight):
    """Build a scikit-learn Pipeline with ColumnTransformer."""

    # Numeric features: apply log1p to specified fields, then StandardScaler
    # We need to handle the log1p transform within the pipeline
    numeric_features_final = [
        "risk_score",
        "attempt_number",
        "contact_fatigue_score",
        "log1p_amount",
        "log1p_lifetime_successful_txns",
        "log1p_lifetime_failed_txns",
    ]

    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
            ("num", StandardScaler(), numeric_features_final),
        ],
        remainder="drop",
    )

    pipeline = Pipeline([
        ("preprocessor", preprocessor),
        ("classifier", LogisticRegression(
            C=C,
            class_weight=class_weight,
            random_state=RANDOM_STATE,
            max_iter=2000,
            solver="lbfgs",
            penalty="l2",
        )),
    ])

    return pipeline


def prepare_features(df):
    """Apply log1p transforms to create final feature columns.
    Done outside pipeline to keep column names explicit."""
    df = df.copy()
    df["log1p_amount"] = np.log1p(df["amount"])
    df["log1p_lifetime_successful_txns"] = np.log1p(df["lifetime_successful_txns"])
    df["log1p_lifetime_failed_txns"] = np.log1p(df["lifetime_failed_txns"])
    return df


def get_feature_columns():
    """Return the list of all feature columns used by the pipeline."""
    numeric_final = [
        "risk_score",
        "attempt_number",
        "contact_fatigue_score",
        "log1p_amount",
        "log1p_lifetime_successful_txns",
        "log1p_lifetime_failed_txns",
    ]
    return CATEGORICAL_FEATURES + numeric_final


# ============================================================
# 3. HYPERPARAMETER SELECTION (validation only)
# ============================================================

def select_hyperparameters(df_train, df_val):
    """Try all C × class_weight combinations, select by validation Brier score."""
    print("\n" + "=" * 70)
    print("STEP 2: HYPERPARAMETER SELECTION (validation only)")
    print("=" * 70)

    feature_cols = get_feature_columns()
    X_train = df_train[feature_cols]
    y_train = df_train[TARGET]
    X_val = df_val[feature_cols]
    y_val = df_val[TARGET]

    results = []
    best_brier = float("inf")
    best_config = None
    best_pipeline = None

    for C in C_VALUES:
        for cw in CLASS_WEIGHT_OPTIONS:
            cw_label = cw if cw else "None"
            pipeline = build_pipeline(C, cw)

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                pipeline.fit(X_train, y_train)
                convergence_warnings = [x for x in w if "convergence" in str(x.message).lower()]

            converged = len(convergence_warnings) == 0

            y_val_prob = pipeline.predict_proba(X_val)[:, 1]
            val_brier = brier_score_loss(y_val, y_val_prob)
            val_logloss = log_loss(y_val, y_val_prob)

            results.append({
                "C": C,
                "class_weight": cw_label,
                "val_brier": round(val_brier, 6),
                "val_logloss": round(val_logloss, 6),
                "converged": converged,
            })

            print(f"\n  C={C}, class_weight={cw_label}")
            print(f"    Val Brier: {val_brier:.6f}, Val LogLoss: {val_logloss:.6f}, Converged: {converged}")

            if val_brier < best_brier:
                best_brier = val_brier
                best_config = {"C": C, "class_weight": cw, "class_weight_label": cw_label}
                best_pipeline = pipeline

    print(f"\n--- SELECTED ---")
    print(f"  Best C: {best_config['C']}")
    print(f"  Best class_weight: {best_config['class_weight_label']}")
    print(f"  Best Val Brier: {best_brier:.6f}")

    return best_pipeline, best_config, results


# ============================================================
# 4. COEFFICIENT ANALYSIS
# ============================================================

def analyze_coefficients(pipeline, df_train):
    """Extract and analyze model coefficients."""
    print("\n" + "=" * 70)
    print("STEP 3: COEFFICIENT ANALYSIS")
    print("=" * 70)

    feature_cols = get_feature_columns()
    X_sample = df_train[feature_cols].head(1)

    # Get feature names from the preprocessor
    preprocessor = pipeline.named_steps["preprocessor"]
    cat_encoder = preprocessor.named_transformers_["cat"]
    cat_feature_names = list(cat_encoder.get_feature_names_out(CATEGORICAL_FEATURES))

    numeric_final = [
        "risk_score",
        "attempt_number",
        "contact_fatigue_score",
        "log1p_amount",
        "log1p_lifetime_successful_txns",
        "log1p_lifetime_failed_txns",
    ]

    all_feature_names = cat_feature_names + numeric_final

    classifier = pipeline.named_steps["classifier"]
    coefficients = classifier.coef_[0]

    coef_df = pd.DataFrame({
        "feature": all_feature_names,
        "coefficient": coefficients,
        "abs_coefficient": np.abs(coefficients),
    }).sort_values("abs_coefficient", ascending=False)

    # Top 20
    print("\nTop 20 coefficients by absolute magnitude:")
    for i, row in coef_df.head(20).iterrows():
        print(f"  {row['feature']:55s} {row['coefficient']:+.4f}")

    # --- 4 coefficient sanity checks ---
    print("\n--- COEFFICIENT SANITY CHECKS ---")
    checks = {}

    # Check 1: card_expired__payment_link — expect meaningfully positive
    card_pl = coef_df[coef_df["feature"].str.contains("failure_action_card_expired__payment_link")]
    if len(card_pl) > 0:
        val = card_pl.iloc[0]["coefficient"]
        passed = val > 0
        checks["card_expired__payment_link_positive"] = passed
        print(f"  1. card_expired__payment_link coefficient: {val:+.4f} "
              f"(expect positive) → {'PASS' if passed else 'FAIL'}")
    else:
        checks["card_expired__payment_link_positive"] = False
        print(f"  1. card_expired__payment_link: NOT FOUND in features — FAIL")

    # Check 2: subscription_mandate_fail__payment_link — expect meaningfully positive
    sub_pl = coef_df[coef_df["feature"].str.contains("failure_action_subscription_mandate_fail__payment_link")]
    if len(sub_pl) > 0:
        val = sub_pl.iloc[0]["coefficient"]
        passed = val > 0
        checks["sub_mandate_payment_link_positive"] = passed
        print(f"  2. subscription_mandate_fail__payment_link coefficient: {val:+.4f} "
              f"(expect positive) → {'PASS' if passed else 'FAIL'}")
    else:
        checks["sub_mandate_payment_link_positive"] = False
        print(f"  2. subscription_mandate_fail__payment_link: NOT FOUND in features — FAIL")

    # Check 3: risk_score — expect negative
    risk = coef_df[coef_df["feature"] == "risk_score"]
    if len(risk) > 0:
        val = risk.iloc[0]["coefficient"]
        passed = val < 0
        checks["risk_score_negative"] = passed
        print(f"  3. risk_score coefficient: {val:+.4f} "
              f"(expect negative) → {'PASS' if passed else 'FAIL'}")
    else:
        checks["risk_score_negative"] = False
        print(f"  3. risk_score: NOT FOUND — FAIL")

    # Check 4: b2c_new__discount more positive than b2b__discount
    b2c_disc = coef_df[coef_df["feature"].str.contains("segment_action_b2c_new__discount")]
    b2b_disc = coef_df[coef_df["feature"].str.contains("segment_action_b2b__discount")]
    if len(b2c_disc) > 0 and len(b2b_disc) > 0:
        b2c_val = b2c_disc.iloc[0]["coefficient"]
        b2b_val = b2b_disc.iloc[0]["coefficient"]
        passed = b2c_val > b2b_val
        checks["b2c_discount_gt_b2b"] = passed
        print(f"  4. b2c_new__discount: {b2c_val:+.4f}, b2b__discount: {b2b_val:+.4f} "
              f"(expect b2c > b2b) → {'PASS' if passed else 'FAIL'}")
    else:
        checks["b2c_discount_gt_b2b"] = False
        print(f"  4. discount interaction features: NOT FOUND — FAIL")

    # Save coefficient analysis
    os.makedirs(os.path.join("ml", "evaluation"), exist_ok=True)
    coef_df.to_csv(os.path.join("ml", "evaluation", "coefficient_analysis.csv"), index=False)
    print(f"\nSaved coefficient analysis to ml/evaluation/coefficient_analysis.csv")

    return coef_df, checks


# ============================================================
# 5. SAVE MODEL AND METADATA
# ============================================================

def save_model(pipeline, config, hp_results, leakage_results, coef_checks, df):
    """Save model artifact + metadata."""
    print("\n" + "=" * 70)
    print("STEP 4: SAVING MODEL AND METADATA")
    print("=" * 70)

    os.makedirs(MODEL_DIR, exist_ok=True)

    # Save pipeline
    model_path = os.path.join(MODEL_DIR, "recovery_model.joblib")
    joblib.dump(pipeline, model_path)
    print(f"  Model saved: {model_path}")

    # Metadata
    feature_cols = get_feature_columns()
    train_rows = len(df[df["split"] == "train"])
    val_rows = len(df[df["split"] == "val"])
    test_rows = len(df[df["split"] == "test"])

    metadata = {
        "model_type": "LogisticRegression",
        "model_variant": "action-conditional (action is a feature)",
        "training_date": datetime.now().isoformat(),
        "random_state": RANDOM_STATE,
        "hyperparameters": {
            "C": config["C"],
            "class_weight": config["class_weight_label"],
            "penalty": "l2",
            "solver": "lbfgs",
            "max_iter": 2000,
        },
        "features": {
            "categorical": CATEGORICAL_FEATURES,
            "numeric_raw": NUMERIC_RAW,
            "log1p_transforms": LOG1P_FIELDS,
            "total_feature_columns": len(feature_cols),
        },
        "data": {
            "source": DATA_PATH,
            "train_rows": train_rows,
            "val_rows": val_rows,
            "test_rows": test_rows,
            "total_rows": len(df),
            "train_transactions": df[df["split"] == "train"]["transaction_id"].nunique(),
            "val_transactions": df[df["split"] == "val"]["transaction_id"].nunique(),
            "test_transactions": df[df["split"] == "test"]["transaction_id"].nunique(),
        },
        "hyperparameter_search": hp_results,
        "leakage_checks": leakage_results,
        "coefficient_sanity_checks": coef_checks,
        "excluded_fields": EXCLUDED_FIELDS,
    }

    metadata_path = os.path.join(MODEL_DIR, "model_metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    print(f"  Metadata saved: {metadata_path}")

    return metadata


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    # 1. Load and validate
    df, leakage_results = load_and_validate()

    # 2. Prepare features (log1p transforms)
    df = prepare_features(df)

    # 3. Split data (use existing split column)
    df_train = df[df["split"] == "train"]
    df_val = df[df["split"] == "val"]
    df_test = df[df["split"] == "test"]

    print(f"\nTrain: {len(df_train)} rows")
    print(f"Val:   {len(df_val)} rows")
    print(f"Test:  {len(df_test)} rows (LOCKED — not used in training or selection)")

    # 4. Hyperparameter selection (train + val only)
    best_pipeline, best_config, hp_results = select_hyperparameters(df_train, df_val)

    # 5. Coefficient analysis
    coef_df, coef_checks = analyze_coefficients(best_pipeline, df_train)

    # 6. Save model and metadata
    metadata = save_model(best_pipeline, best_config, hp_results, leakage_results, coef_checks, df)

    print("\n" + "=" * 70)
    print("M2 TRAINING COMPLETE")
    print("=" * 70)
    print(f"\nModel: LogisticRegression (action-conditional)")
    print(f"Selected C: {best_config['C']}")
    print(f"Selected class_weight: {best_config['class_weight_label']}")
    print(f"Model saved to: ml/models/recovery_model.joblib")
    print(f"Metadata saved to: ml/models/model_metadata.json")
    print(f"\nNEXT: Run evaluate_test_set.py for final held-out evaluation.")
    print("=" * 70)
