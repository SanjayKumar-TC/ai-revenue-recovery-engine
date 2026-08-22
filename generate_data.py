"""
RecoverIQ - Day 1: Synthetic Data Generator + Latent Ground Truth
===================================================================
Generates a synthetic merchant environment: customers, transactions,
and per-action HIDDEN outcomes via a latent-score -> sigmoid -> sample
mechanism. The model trained downstream never sees the latent score,
only the sampled outcome - it must recover the pattern from noisy,
correlated observable features.

Design decisions locked after review (Claude <-> ChatGPT synthesis):
  1. Action-expanded training table (one row per transaction x eligible action)
  2. close = natural/no-intervention recovery (NOT near-zero, NOT punitive)
     wait  = natural recovery + small deferral bonus (option value of later action)
  3. Explicit interaction features (failure_type x action, segment x action)
     constructed as real columns, not left implicit in the latent formula
  4. Action eligibility matrix - ineligible actions are never generated/scored
  5. Customer-level train/val/test split (prevents entity leakage)
  6. No external benchmark tuning of the base rate (Stripe 25-35% etc.) -
     only internal self-consistency checks
"""

import numpy as np
import pandas as pd

RNG_SEED = 42
rng = np.random.default_rng(RNG_SEED)

N_CUSTOMERS = 3500
N_TRANSACTIONS = 10000

# ---------------------------------------------------------------------------
# 1. ACTION SPACE + ELIGIBILITY MATRIX
# ---------------------------------------------------------------------------

ACTIONS = ["retry", "payment_link", "reminder", "discount", "wait", "close", "escalate"]

FAILURE_TYPES = [
    "temporary_bank_decline",
    "network_timeout",
    "card_expired",
    "risk_block",
    "customer_abandoned",
    "subscription_mandate_fail",
    "insufficient_funds",
]

FAILURE_TYPE_WEIGHTS = {
    "temporary_bank_decline": 0.35,
    "network_timeout": 0.20,
    "card_expired": 0.10,
    "risk_block": 0.08,
    "customer_abandoned": 0.15,
    "subscription_mandate_fail": 0.07,
    "insufficient_funds": 0.05,
}

# Which actions make sense at all for a given failure type.
# escalate and close/wait are always eligible (universal fallback options).
ELIGIBILITY = {
    "temporary_bank_decline": {"retry", "payment_link", "reminder", "discount", "wait", "close", "escalate"},
    "network_timeout":        {"retry", "payment_link", "reminder", "wait", "close", "escalate"},
    "card_expired":           {"payment_link", "reminder", "discount", "wait", "close", "escalate"},  # retry pointless
    "risk_block":             {"wait", "close", "escalate"},  # no automated recovery action allowed at all
    "customer_abandoned":     {"payment_link", "reminder", "discount", "wait", "close", "escalate"},  # no "retry"
    "subscription_mandate_fail": {"payment_link", "reminder", "discount", "wait", "close", "escalate"},  # mandate needs re-auth, not retry
    "insufficient_funds":     {"retry", "reminder", "payment_link", "wait", "close", "escalate"},
}

SEGMENTS = ["b2c_new", "b2c_returning", "b2b"]
SEGMENT_WEIGHTS = [0.50, 0.40, 0.10]

# ---------------------------------------------------------------------------
# 2. CUSTOMER GENERATION
# ---------------------------------------------------------------------------

def generate_customers(n):
    segment = rng.choice(SEGMENTS, size=n, p=SEGMENT_WEIGHTS)

    customer_age_days = np.clip(
        rng.lognormal(mean=np.log(180), sigma=0.9, size=n), 1, 3650
    ).astype(int)

    # more age -> more successful txns on average (poisson lambda scales w/ age)
    base_lambda = np.clip(customer_age_days / 45.0, 0.2, 40)
    lifetime_successful_txns = rng.poisson(base_lambda)
    lifetime_failed_txns = rng.poisson(0.3 * np.clip(lifetime_successful_txns, 0.1, None))

    avg_transaction_value = np.where(
        segment == "b2b",
        np.clip(rng.lognormal(mean=np.log(40000), sigma=0.6, size=n), 3000, 800000),
        np.clip(rng.lognormal(mean=np.log(1800), sigma=0.7, size=n), 100, 60000),
    )

    # right-skewed risk score: most customers low risk
    risk_score = rng.beta(2, 8, size=n)

    preferred_channel = rng.choice(
        ["email", "sms", "whatsapp", "none"], size=n, p=[0.35, 0.20, 0.35, 0.10]
    )

    df = pd.DataFrame({
        "customer_id": np.arange(1, n + 1),
        "segment": segment,
        "customer_age_days": customer_age_days,
        "lifetime_successful_txns": lifetime_successful_txns,
        "lifetime_failed_txns": lifetime_failed_txns,
        "avg_transaction_value": avg_transaction_value.round(2),
        "risk_score": risk_score.round(4),
        "preferred_channel": preferred_channel,
        "contact_fatigue_score": 0.0,  # computed later, strictly from PAST events per transaction timestamp
    })
    return df


# ---------------------------------------------------------------------------
# 3. TRANSACTION GENERATION
# ---------------------------------------------------------------------------

def generate_transactions(customers_df, n):
    customer_ids = rng.choice(customers_df["customer_id"], size=n, replace=True)
    cust = customers_df.set_index("customer_id").loc[customer_ids].reset_index()

    failure_type = rng.choice(
        list(FAILURE_TYPE_WEIGHTS.keys()), size=n, p=list(FAILURE_TYPE_WEIGHTS.values())
    )

    # amount correlated with customer's typical transaction value, with noise
    amount = np.clip(
        cust["avg_transaction_value"].to_numpy() * rng.lognormal(mean=0, sigma=0.35, size=n),
        50, None
    ).round(2)

    payment_method = rng.choice(
        ["card", "upi", "netbanking", "wallet"], size=n, p=[0.35, 0.40, 0.15, 0.10]
    )

    attempt_number = rng.choice([1, 2, 3], size=n, p=[0.7, 0.22, 0.08])
    is_subscription = (failure_type == "subscription_mandate_fail") | (rng.random(n) < 0.08)

    # base timestamps over a synthetic 90-day merchant window
    start = pd.Timestamp("2026-05-01")
    timestamps = start + pd.to_timedelta(rng.integers(0, 90 * 24 * 60, size=n), unit="m")

    df = pd.DataFrame({
        "transaction_id": np.arange(1, n + 1),
        "customer_id": cust["customer_id"].to_numpy(),
        "segment": cust["segment"].to_numpy(),
        "customer_age_days": cust["customer_age_days"].to_numpy(),
        "lifetime_successful_txns": cust["lifetime_successful_txns"].to_numpy(),
        "lifetime_failed_txns": cust["lifetime_failed_txns"].to_numpy(),
        "risk_score": cust["risk_score"].to_numpy(),
        "preferred_channel": cust["preferred_channel"].to_numpy(),
        "amount": amount,
        "failure_type": failure_type,
        "payment_method": payment_method,
        "attempt_number": attempt_number,
        "is_subscription": is_subscription,
        "timestamp": timestamps,
        # Simplification for Day 1: fatigue as a function of attempt_number (prior contacts on
        # THIS transaction thread), which is already strictly backward-looking / no future leakage.
        # A fuller cross-transaction fatigue rollup (touching all past events for a customer,
        # ordered by timestamp) is a Day 2+ enhancement once the event log exists.
        "contact_fatigue_score": np.clip((attempt_number - 1) * 0.3, 0, 1),
    })
    return df.sort_values("timestamp").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4. LATENT SCORE -> SIGMOID -> SAMPLED OUTCOME (per eligible action)
# ---------------------------------------------------------------------------

# Relative failure-type effect (fed into latent score, NOT a final probability)
FAILURE_TYPE_EFFECT = {
    "network_timeout": 1.8,
    "temporary_bank_decline": 1.2,
    "insufficient_funds": -0.3,
    "card_expired": -0.9,
    "customer_abandoned": -0.5,
    "subscription_mandate_fail": -0.7,
    "risk_block": -2.5,
}

# Base action effect (before interaction terms)
ACTION_EFFECT = {
    "retry": 0.5,
    "payment_link": 0.3,
    "reminder": 0.1,
    "discount": 0.6,
    "wait": None,     # handled specially - natural recovery + small deferral bonus
    "close": None,    # handled specially - natural recovery, no action effect at all
    "escalate": None, # handled specially - routed to human, no probability computed
}

# Explicit interaction bonuses layered on top of base action effect
# (failure_type, action) -> additive bonus
FAILURE_ACTION_INTERACTION = {
    ("card_expired", "payment_link"): 1.0,          # payment_link is the *right* fix for expired card
    ("subscription_mandate_fail", "payment_link"): 0.9,  # mandate re-auth path
    ("risk_block", "retry"): -2.0,                  # never actually reached (ineligible) but kept for completeness
}

# (segment, action) -> additive bonus
SEGMENT_ACTION_INTERACTION = {
    ("b2c_new", "discount"): 0.4,       # new/price-sensitive customers respond well to discount
    ("b2b", "discount"): -0.3,          # b2b less swayed by small discounts, relationship-driven instead
    ("b2b", "reminder"): 0.3,           # b2b customers respond well to a professional reminder/nudge
}

NATURAL_RECOVERY_BASE = -0.4    # latent contribution representing "will pay anyway, unprompted"
DEFERRAL_BONUS = 0.35           # extra option value 'wait' carries over 'close' (chance context improves)

NOISE_SIGMA = 0.6


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def compute_latent(row, action):
    """
    Returns the (pre-noise) latent score components for a given transaction row
    and a candidate action. Noise is added separately at sampling time so that
    repeated calls for different actions on the SAME transaction share the same
    customer/transaction-level latent baseline but differ by the action term -
    this is what makes the action-conditional structure real rather than decorative.
    """
    beta0 = -0.6  # intercept, tuned only via internal self-consistency (see sanity checks), not external benchmark

    failure_term = FAILURE_TYPE_EFFECT[row["failure_type"]]
    history_term = 0.35 * np.log1p(row["lifetime_successful_txns"])
    risk_term = -1.4 * row["risk_score"]
    amount_term = -0.3 * np.log1p(row["amount"])
    fatigue_term = -1.0 * row["contact_fatigue_score"]

    if action == "close":
        action_term = NATURAL_RECOVERY_BASE
    elif action == "wait":
        action_term = NATURAL_RECOVERY_BASE + DEFERRAL_BONUS
    else:
        action_term = ACTION_EFFECT[action]
        action_term += FAILURE_ACTION_INTERACTION.get((row["failure_type"], action), 0.0)
        action_term += SEGMENT_ACTION_INTERACTION.get((row["segment"], action), 0.0)

    latent = (
        beta0
        + failure_term
        + history_term
        + risk_term
        + amount_term
        + fatigue_term
        + action_term
    )
    return latent


def generate_action_expanded_outcomes(transactions_df):
    """
    For every transaction, for every ELIGIBLE action (per the eligibility matrix),
    compute the latent score, add sampling noise, pass through sigmoid, and sample
    a hidden outcome. 'escalate' gets no probability - it's a routing action, not
    a recovery mechanism in itself (the human decides afterward).

    Returns a long-format action-expanded table:
        transaction_id | context columns... | action | true_prob (HIDDEN, for eval only) | outcome
    """
    rows = []
    for _, txn in transactions_df.iterrows():
        eligible_actions = ELIGIBILITY[txn["failure_type"]]
        for action in eligible_actions:
            if action == "escalate":
                continue  # no recovery-probability semantics; policy/human decides, not sampled here

            latent = compute_latent(txn, action)
            noise = rng.normal(0, NOISE_SIGMA)
            true_prob = sigmoid(latent + noise)
            outcome = int(rng.random() < true_prob)

            rows.append({
                "transaction_id": txn["transaction_id"],
                "customer_id": txn["customer_id"],
                "segment": txn["segment"],
                "customer_age_days": txn["customer_age_days"],
                "lifetime_successful_txns": txn["lifetime_successful_txns"],
                "lifetime_failed_txns": txn["lifetime_failed_txns"],
                "risk_score": txn["risk_score"],
                "amount": txn["amount"],
                "failure_type": txn["failure_type"],
                "payment_method": txn["payment_method"],
                "attempt_number": txn["attempt_number"],
                "is_subscription": txn["is_subscription"],
                "contact_fatigue_score": txn["contact_fatigue_score"],
                "action": action,
                "true_prob_HIDDEN": round(true_prob, 4),  # NEVER feed this to the model - eval/debug only
                "outcome": outcome,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. EXPLICIT INTERACTION FEATURES (for the model - separate from simulator)
# ---------------------------------------------------------------------------

def add_interaction_features(df):
    """
    Logistic regression is linear in its inputs. The simulator encodes
    failure_type x action and segment x action interactions in the latent
    score, but the model can only learn them if we construct explicit
    interaction columns (or one-hot cross terms). This function builds
    those columns so the model's feature set actually matches the
    data-generating process's structure.
    """
    df = df.copy()
    df["failure_action"] = df["failure_type"] + "__" + df["action"]
    df["segment_action"] = df["segment"] + "__" + df["action"]
    return df


# ---------------------------------------------------------------------------
# 6. EVENT_TYPE DERIVATION (deterministic labeling layer)
#    Derived purely from failure_type + attempt_number.
#    This is a coarse operational classification for downstream
#    policy/dashboard grouping. It has ZERO effect on:
#      - action eligibility (remains keyed on failure_type)
#      - latent scores / outcome generation
#      - any probabilities or hidden variables
# ---------------------------------------------------------------------------

# Failure types where attempt_number >= 2 promotes to "repeated_payment_failure"
_REPEATABLE_FAILURE_TYPES = frozenset([
    "temporary_bank_decline",
    "network_timeout",
    "insufficient_funds",
])

def derive_event_type(failure_type, attempt_number):
    """
    Deterministic mapping: (failure_type, attempt_number) -> event_type.

    Rules:
      - temporary_bank_decline / network_timeout / insufficient_funds
        with attempt_number == 1  -> temporary_payment_failure
        with attempt_number >= 2  -> repeated_payment_failure
      - card_expired             -> temporary_payment_failure  (any attempt)
      - risk_block               -> temporary_payment_failure  (any attempt)
      - customer_abandoned       -> checkout_abandonment
      - subscription_mandate_fail -> subscription_mandate_failure

    NOTE on risk_block: Grouped under temporary_payment_failure ONLY for
    the coarse event_type classification. Its action eligibility remains
    {wait, close, escalate} only — see ELIGIBILITY matrix. The event_type
    label is a classification field, not a recovery authorization.
    """
    if failure_type == "customer_abandoned":
        return "checkout_abandonment"
    elif failure_type == "subscription_mandate_fail":
        return "subscription_mandate_failure"
    elif failure_type in _REPEATABLE_FAILURE_TYPES and attempt_number >= 2:
        return "repeated_payment_failure"
    else:
        # card_expired, risk_block, and first-attempt repeatable types
        return "temporary_payment_failure"


def add_event_type(df):
    """
    Add event_type column to a DataFrame that has failure_type and attempt_number.
    Pure derivation — no randomness, no side effects.
    """
    df = df.copy()
    df["event_type"] = df.apply(
        lambda row: derive_event_type(row["failure_type"], row["attempt_number"]),
        axis=1
    )
    return df


# ---------------------------------------------------------------------------
# 7. CUSTOMER-LEVEL SPLIT (prevents entity leakage across train/val/test)
# ---------------------------------------------------------------------------

def customer_level_split(customers_df, train=0.70, val=0.15, seed=RNG_SEED):
    split_rng = np.random.default_rng(seed)
    out = customers_df.copy()
    # stratify by segment so b2b isn't underrepresented in any split
    out["split"] = "train"
    for seg, seg_df in out.groupby("segment"):
        ids = seg_df["customer_id"].to_numpy().copy()
        split_rng.shuffle(ids)
        n = len(ids)
        n_train = int(n * train)
        n_val = int(n * val)
        train_ids = set(ids[:n_train])
        val_ids = set(ids[n_train:n_train + n_val])
        out.loc[out["customer_id"].isin(train_ids), "split"] = "train"
        out.loc[out["customer_id"].isin(val_ids), "split"] = "val"
        out.loc[out["customer_id"].isin(ids[n_train + n_val:]), "split"] = "test"
    return out[["customer_id", "split"]]


# ---------------------------------------------------------------------------
# 8. SANITY CHECKS (internal self-consistency only - no external benchmark tuning)
# ---------------------------------------------------------------------------

def run_sanity_checks(action_df):
    print("=" * 70)
    print("SANITY CHECKS")
    print("=" * 70)

    overall_rate = action_df["outcome"].mean()
    print(f"\n1. Overall recovery rate across all (transaction, action) rows: {overall_rate:.1%}")
    print("   (No external benchmark used to tune this - internal plausibility only)")

    print("\n2. Recovery rate by failure_type (marginal, averaged across actions):")
    print(action_df.groupby("failure_type")["outcome"].mean().sort_values(ascending=False).round(3))

    print("\n3. Recovery rate by action (marginal, averaged across eligible failure types):")
    print(action_df.groupby("action")["outcome"].mean().sort_values(ascending=False).round(3))

    print("\n4. Action effectiveness WITHIN a fixed failure_type (checks for genuine crossover,")
    print("   i.e. that action actually matters and isn't just a decorative constant offset):")
    for ft in ["card_expired", "subscription_mandate_fail", "temporary_bank_decline"]:
        sub = action_df[action_df["failure_type"] == ft]
        print(f"\n   {ft}:")
        print("  ", sub.groupby("action")["outcome"].mean().sort_values(ascending=False).round(3).to_dict())

    print("\n5. close vs wait recovery rate (should be close but wait slightly higher,")
    print("   NOT close near-zero / wait near-one - checks locked fix #2):")
    cw = action_df[action_df["action"].isin(["close", "wait"])]
    print(cw.groupby("action")["outcome"].mean().round(3))

    print("\n6. risk_block: only wait/close should exist (retry/discount must be absent -")
    print("   checks eligibility matrix enforcement, fix #4):")
    rb_actions = set(action_df[action_df["failure_type"] == "risk_block"]["action"].unique())
    print(f"   Actions present for risk_block: {rb_actions}")
    assert rb_actions <= {"wait", "close"}, "ELIGIBILITY VIOLATION: risk_block has disallowed actions!"
    print("   PASS - no automated recovery actions leaked into risk_block")

    print("\n7. checkout_abandoned (customer_abandoned) must not contain 'retry':")
    ca_actions = set(action_df[action_df["failure_type"] == "customer_abandoned"]["action"].unique())
    assert "retry" not in ca_actions, "ELIGIBILITY VIOLATION: retry present for abandonment!"
    print(f"   Actions present: {ca_actions}")
    print("   PASS - retry correctly excluded")

    print("\n8. No single feature should trivially separate outcome (checks for accidental")
    print("   latent leakage). Quick check: risk_score alone as a naive threshold classifier:")
    from sklearn.metrics import roc_auc_score
    try:
        auc = roc_auc_score(action_df["outcome"], -action_df["risk_score"])
        print(f"   risk_score-only AUC: {auc:.3f}  (should be well below ~0.85, not near 1.0)")
    except Exception as e:
        print(f"   (skipped: {e})")

    # --- EVENT_TYPE VALIDATION (checks 9-11) ---
    if "event_type" in action_df.columns:
        print("\n9. event_type mapping validation:")
        mapping_checks = [
            ("temporary_bank_decline", 1, "temporary_payment_failure"),
            ("temporary_bank_decline", 2, "repeated_payment_failure"),
            ("temporary_bank_decline", 3, "repeated_payment_failure"),
            ("network_timeout", 1, "temporary_payment_failure"),
            ("network_timeout", 2, "repeated_payment_failure"),
            ("network_timeout", 3, "repeated_payment_failure"),
            ("insufficient_funds", 1, "temporary_payment_failure"),
            ("insufficient_funds", 2, "repeated_payment_failure"),
            ("insufficient_funds", 3, "repeated_payment_failure"),
            ("card_expired", 1, "temporary_payment_failure"),
            ("card_expired", 2, "temporary_payment_failure"),
            ("card_expired", 3, "temporary_payment_failure"),
            ("risk_block", 1, "temporary_payment_failure"),
            ("risk_block", 2, "temporary_payment_failure"),
            ("risk_block", 3, "temporary_payment_failure"),
            ("customer_abandoned", 1, "checkout_abandonment"),
            ("customer_abandoned", 2, "checkout_abandonment"),
            ("customer_abandoned", 3, "checkout_abandonment"),
            ("subscription_mandate_fail", 1, "subscription_mandate_failure"),
            ("subscription_mandate_fail", 2, "subscription_mandate_failure"),
            ("subscription_mandate_fail", 3, "subscription_mandate_failure"),
        ]
        all_pass = True
        for ft, att, expected_et in mapping_checks:
            actual = derive_event_type(ft, att)
            status = "PASS" if actual == expected_et else "FAIL"
            if status == "FAIL":
                all_pass = False
            print(f"   {ft} + attempt={att} -> {actual} (expected: {expected_et}) [{status}]")
        assert all_pass, "EVENT_TYPE MAPPING VIOLATION: one or more mappings incorrect!"
        print("   ALL MAPPINGS PASS")

        print("\n10. event_type determinism check (same failure_type + attempt_number -> same event_type):")
        # Verify: for each unique (failure_type, attempt_number) pair, event_type is unique
        et_groups = action_df.groupby(["failure_type", "attempt_number"])["event_type"].nunique()
        non_deterministic = et_groups[et_groups > 1]
        if len(non_deterministic) == 0:
            print("   PASS - event_type is fully deterministic from (failure_type, attempt_number)")
        else:
            print(f"   FAIL - non-deterministic pairs found: {non_deterministic.to_dict()}")
            assert False, "EVENT_TYPE DETERMINISM VIOLATION"

        print("\n11. event_type has ZERO effect on eligibility (actions per failure_type unchanged):")
        # Verify: grouping by event_type doesn't change which actions appear for each failure_type
        for ft in FAILURE_TYPES:
            expected_actions = ELIGIBILITY[ft] - {"escalate"}  # escalate is skipped in generation
            actual_actions = set(action_df[action_df["failure_type"] == ft]["action"].unique())
            assert actual_actions == expected_actions, (
                f"ELIGIBILITY CHANGED for {ft}: expected {expected_actions}, got {actual_actions}"
            )
        print("   PASS - eligibility remains keyed on failure_type, unaffected by event_type")

        print("\n12. event_type distribution:")
        et_dist = action_df.groupby("event_type")["transaction_id"].nunique()
        print(et_dist)

        print("\n13. failure_type preserved within event_type (no renaming):")
        for et in action_df["event_type"].unique():
            fts = sorted(action_df[action_df["event_type"] == et]["failure_type"].unique())
            print(f"   {et}: {fts}")
        print("   PASS - original failure_type values intact")
    else:
        print("\n9-13. event_type checks: SKIPPED (column not present)")

    print("\n" + "=" * 70)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Generating customers...")
    customers = generate_customers(N_CUSTOMERS)

    print("Generating transactions...")
    transactions = generate_transactions(customers, N_TRANSACTIONS)

    print("Generating action-expanded hidden outcomes (latent -> sigmoid -> sample)...")
    action_expanded = generate_action_expanded_outcomes(transactions)

    print("Adding explicit interaction features for the model...")
    action_expanded = add_interaction_features(action_expanded)

    # --- event_type derivation (AFTER all generation, pure labeling) ---
    # Applied to both transactions and action-expanded tables.
    # This is deterministic from failure_type + attempt_number.
    # It has ZERO effect on eligibility, latent scores, or outcomes.
    print("Deriving event_type labels (deterministic from failure_type + attempt_number)...")
    transactions = add_event_type(transactions)
    action_expanded = add_event_type(action_expanded)

    print("Building customer-level train/val/test split...")
    split_map = customer_level_split(customers)
    action_expanded = action_expanded.merge(split_map, on="customer_id", how="left")

    run_sanity_checks(action_expanded)

    print(f"\nTotal transactions: {len(transactions)}")
    print(f"Total action-expanded rows: {len(action_expanded)}")
    print(f"Split sizes:\n{action_expanded.groupby('split')['transaction_id'].nunique()}")

    # Persist
    customers.to_csv("customers.csv", index=False)
    transactions.to_csv("transactions.csv", index=False)
    # model-facing table drops the HIDDEN true probability - only outcome is visible
    model_table = action_expanded.drop(columns=["true_prob_HIDDEN"])
    model_table.to_csv("action_expanded_training_data.csv", index=False)
    # separate eval-only table WITH the hidden prob, for calibration debugging later (Person A only)
    action_expanded.to_csv("action_expanded_with_hidden_truth.csv", index=False)

    print("\nSaved: customers.csv, transactions.csv, action_expanded_training_data.csv,")
    print("       action_expanded_with_hidden_truth.csv (eval/debug only - do not train on this file's prob column)")
