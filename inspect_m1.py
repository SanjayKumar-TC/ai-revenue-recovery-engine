"""Quick M1 output inspection for M2 kickoff."""
import pandas as pd
import numpy as np

df = pd.read_csv("action_expanded_training_data.csv")
print("=" * 70)
print("M1 OUTPUT INSPECTION")
print("=" * 70)
print(f"\nShape: {df.shape}")
print(f"Columns: {list(df.columns)}")
print(f"\nSplit distribution (unique transactions):")
print(df.groupby("split")["transaction_id"].nunique())
print(f"\nSplit distribution (rows):")
print(df["split"].value_counts())
print(f"\nTotal unique transactions: {df['transaction_id'].nunique()}")
print(f"Total unique customers: {df['customer_id'].nunique()}")

# Customer overlap check
train_custs = set(df[df["split"]=="train"]["customer_id"].unique())
val_custs = set(df[df["split"]=="val"]["customer_id"].unique())
test_custs = set(df[df["split"]=="test"]["customer_id"].unique())
print(f"\nCustomer overlap train∩val: {len(train_custs & val_custs)}")
print(f"Customer overlap train∩test: {len(train_custs & test_custs)}")
print(f"Customer overlap val∩test: {len(val_custs & test_custs)}")

print(f"\nUnique customers per split:")
print(f"  train: {len(train_custs)}")
print(f"  val: {len(val_custs)}")
print(f"  test: {len(test_custs)}")

print(f"\nFailure types: {sorted(df['failure_type'].unique())}")
print(f"Actions: {sorted(df['action'].unique())}")
print(f"Segments: {sorted(df['segment'].unique())}")
print(f"Payment methods: {sorted(df['payment_method'].unique())}")

print(f"\nOutcome distribution:")
print(df["outcome"].value_counts())
print(f"Recovery rate: {df['outcome'].mean():.4f}")

print(f"\nSample dtypes:")
print(df.dtypes)

# Check for columns that should NOT be here
bad_cols = ["latent_score", "true_prob_HIDDEN", "avg_transaction_value", "preferred_channel"]
for c in bad_cols:
    if c in df.columns:
        print(f"WARNING: {c} found in training data!")
    else:
        print(f"OK: {c} not in training data")

print(f"\nFirst 3 rows:")
print(df.head(3).to_string())
print("\n" + "=" * 70)
