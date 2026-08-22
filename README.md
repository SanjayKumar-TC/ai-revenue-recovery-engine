# AI Revenue Recovery Decision Engine

**Razorpay Buildathon — Solo Developer**

A transparent AI decision layer for revenue/payment recovery. For every
revenue-at-risk event, the system determines: *"What is the safest and
economically best permitted action?"*

---

## Milestone 1 — Synthetic Data Generator

### Architecture

```
Revenue-at-risk event
        ↓
Customer + transaction context
        ↓
Action eligibility (keyed on failure_type)
        ↓
Latent score → sigmoid → sampled outcome (per eligible action)
        ↓
Action-expanded dataset (one row per transaction × eligible action)
```

### Data Generator (`generate_data.py`)

| Component | Description |
|---|---|
| **Customers** | 3,500 synthetic customers with segment, age, risk score, payment history |
| **Transactions** | 10,000 failed transactions with failure_type, amount, payment method |
| **Action-expanded outcomes** | One row per (transaction, eligible_action) with hidden P(recovery) |
| **Seed** | `42` — deterministic, reproducible |

### Failure Types

| failure_type | Weight | Eligible Actions |
|---|---|---|
| `temporary_bank_decline` | 35% | retry, payment_link, reminder, discount, wait, close, escalate |
| `network_timeout` | 20% | retry, payment_link, reminder, wait, close, escalate |
| `customer_abandoned` | 15% | payment_link, reminder, discount, wait, close, escalate |
| `card_expired` | 10% | payment_link, reminder, discount, wait, close, escalate |
| `risk_block` | 8% | wait, close, escalate |
| `subscription_mandate_fail` | 7% | payment_link, reminder, discount, wait, close, escalate |
| `insufficient_funds` | 5% | retry, reminder, payment_link, wait, close, escalate |

### Event Type Classification

`event_type` is a **derived labeling field** computed deterministically from
`failure_type + attempt_number`. It exists purely for downstream
policy/dashboard grouping.

| event_type | Source failure_type(s) | Condition |
|---|---|---|
| `temporary_payment_failure` | temporary_bank_decline, network_timeout, insufficient_funds | attempt_number = 1 |
| `temporary_payment_failure` | card_expired, risk_block | any attempt_number |
| `repeated_payment_failure` | temporary_bank_decline, network_timeout, insufficient_funds | attempt_number ≥ 2 |
| `checkout_abandonment` | customer_abandoned | any |
| `subscription_mandate_failure` | subscription_mandate_fail | any |

### ⚠️ Note on `risk_block` Classification

> **`risk_block` is grouped under the `temporary_payment_failure` event_type
> for reporting purposes, but its action eligibility remains `{wait, close}`
> only — it never receives automated retry/payment_link/discount treatment
> regardless of event_type grouping.**
>
> This is intentional: `risk_block` represents a case judged unsafe for
> automated recovery independent of whether the underlying issue is transient.
> The `event_type` label describes typical business framing, not
> automated-recovery eligibility.

### Key Design Decisions

1. **Action eligibility is keyed on `failure_type`, NOT `event_type`.**
   `event_type` is a reporting/labeling layer added purely for downstream
   policy/dashboard grouping — it has zero effect on which actions get scored.

2. **`close` = natural/no-intervention recovery** (NOT near-zero, NOT punitive).
   `wait` = natural recovery + small deferral bonus (option value of later action).
   `wait ≠ close` — they are distinct states.

3. **Latent-score → sigmoid → sample mechanism** produces hidden outcomes.
   The model never sees `latent_score` or `true_prob_HIDDEN`.

4. **Customer-level train/val/test split** (70/15/15) prevents entity leakage.

5. **Explicit interaction features** (`failure_type × action`, `segment × action`)
   constructed as real columns for the downstream logistic regression.

### Data Leakage Rules

The following MUST NEVER become model features:
- `latent_score`
- `true_prob_HIDDEN`
- Outcome-generation noise
- Future outcomes / future transaction information

### Output Files

| File | Purpose | Model-safe? |
|---|---|---|
| `customers.csv` | Customer profiles | N/A |
| `transactions.csv` | Failed transactions with event_type | N/A |
| `action_expanded_training_data.csv` | Training data (no hidden truth) | ✅ Yes |
| `action_expanded_with_hidden_truth.csv` | Eval/debug only (contains true_prob) | ❌ Never train on this |

### Running

```bash
python generate_data.py
```

Requires: `numpy`, `pandas`, `scikit-learn` (for sanity check AUC only)

---

## Milestone Roadmap

| M# | Description | Status |
|---|---|---|
| M1 | Synthetic Data Generator | ✅ Complete |
| M2 | Action-Conditional Logistic Regression | ⏳ Pending |
| M3 | Deterministic Policy Engine | ⏳ Pending |
| M4 | Expected Net Value + Decision Engine | ⏳ Pending |
| M5 | Fixed Baseline + Experiment | ⏳ Pending |
| M6 | Bounded LLM | ⏳ Pending |
| M7 | Audit Trail | ⏳ Pending |
| M8 | FastAPI Backend | ⏳ Pending |
| M9 | React Dashboard | ⏳ Pending |
| M10 | Stress Testing + Hardening | ⏳ Pending |
| M11 | Demo + Documentation | ⏳ Pending |
"# ai-revenue-recovery-engine" 
