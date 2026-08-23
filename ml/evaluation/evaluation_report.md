# M2 Evaluation Report — Action-Conditional Logistic Regression

**Status: PASS**

---

## Model Configuration

| Parameter | Value |
|---|---|
| Model | `sklearn.linear_model.LogisticRegression` |
| Variant | Action-conditional (action is a feature, not a separate model) |
| Regularization | L2 |
| Solver | lbfgs |
| max_iter | 2000 |
| random_state | 42 |
| **Selected C** | **10.0** |
| **Selected class_weight** | **None** |
| Selection metric | Validation Brier Score |
| Convergence | All 8 configurations converged |

### Why C=10.0, class_weight=None?

| C | class_weight | Val Brier | Val LogLoss | Converged |
|---|---|---|---|---|
| 0.01 | None | 0.127899 | 0.403750 | ✅ |
| 0.01 | balanced | 0.202140 | 0.581439 | ✅ |
| 0.1 | None | 0.127852 | 0.402625 | ✅ |
| 0.1 | balanced | 0.203331 | 0.580591 | ✅ |
| 1.0 | None | 0.127852 | 0.402647 | ✅ |
| 1.0 | balanced | 0.203601 | 0.580602 | ✅ |
| **10.0** | **None** | **0.127841** | **0.402683** | ✅ |
| 10.0 | balanced | 0.203670 | 0.580704 | ✅ |

- `class_weight=None` consistently dominates `balanced` by a wide margin (~0.128 vs ~0.203 Brier).
  This is expected: `balanced` upweights the minority class (recovery=18.2%), which inflates predicted
  probabilities and worsens calibration. Since calibrated probabilities matter more than classification
  accuracy for the downstream EV engine, `None` is the correct choice.
- All `None` configurations are nearly identical (Brier range 0.127841–0.127899). C=10.0 wins by a
  razor-thin margin, suggesting the model is not over-regularized even at C=0.01. The effective
  feature space is well-conditioned.

---

## Data Summary

| Split | Rows | Transactions | Customers | Recovery Rate |
|---|---|---|---|---|
| Train | 35,645 | 6,988 | 2,325 | 18.25% |
| Val | 7,279 | 1,435 | 481 | 17.79% |
| Test | 8,042 | 1,577 | 494 | 18.48% |
| **Total** | **50,966** | **10,000** | **3,300** | **18.22%** |

Customer overlap: train∩val=0, train∩test=0, val∩test=0 — **PASS**

---

## Features

### Categorical (OneHotEncoder)
- `failure_type` — 7 unique values
- `action` — 6 unique values (escalate excluded by M1 generator)
- `segment` — 3 unique values
- `payment_method` — 4 unique values
- `failure_action` — explicit interaction (failure_type × action)
- `segment_action` — explicit interaction (segment × action)

### Numeric (log1p → StandardScaler)
- `risk_score`
- `attempt_number`
- `contact_fatigue_score`
- `log1p(amount)`
- `log1p(lifetime_successful_txns)`
- `log1p(lifetime_failed_txns)`

### Excluded
`transaction_id`, `customer_id`, `timestamp`, `split`, `event_type`,
`avg_transaction_value`, `preferred_channel`, `latent_score`, `true_prob_HIDDEN`

---

## Test Set Metrics

| Metric | Value |
|---|---|
| **ROC-AUC** | **0.7607** |
| **PR-AUC** | **0.3981** |
| **Log Loss** | **0.4106** |
| **Brier Score** | **0.1308** |
| Accuracy (secondary) | 0.8186 |

---

## Calibration Table (Deciles)

| Bucket | Count | Mean Predicted | Actual Rate | Gap |
|---|---|---|---|---|
| (0, 0.022] | 805 | 0.0114 | 0.0161 | +0.0047 |
| (0.022, 0.042] | 804 | 0.0322 | 0.0386 | +0.0064 |
| (0.042, 0.073] | 804 | 0.0563 | 0.0597 | +0.0034 |
| (0.073, 0.120] | 804 | 0.0951 | 0.0846 | −0.0105 |
| (0.120, 0.167] | 804 | 0.1440 | 0.1480 | +0.0040 |
| (0.167, 0.213] | 804 | 0.1900 | 0.1803 | −0.0097 |
| (0.213, 0.259] | 804 | 0.2358 | 0.2226 | −0.0132 |
| (0.259, 0.311] | 804 | 0.2840 | 0.3072 | +0.0232 |
| (0.311, 0.390] | 804 | 0.3476 | 0.3259 | −0.0217 |
| (0.390, 0.732] | 805 | 0.4684 | 0.4646 | −0.0038 |

**Mean absolute calibration gap: 0.0101**

**Assessment: WELL CALIBRATED.** Predicted ~0.28 corresponds to actual ~0.31.
Predicted ~0.47 corresponds to actual ~0.46. The largest gap is 0.023 (bucket 8),
which is small. The model's probability estimates are trustworthy for the
downstream EV engine.

---

## Coefficient Sanity Checks

### Top 20 Coefficients

| Feature | Coefficient |
|---|---|
| failure_type_risk_block | −1.7282 |
| failure_type_network_timeout | +1.4206 |
| failure_type_temporary_bank_decline | +0.9813 |
| failure_action_risk_block__close | −0.8711 |
| failure_action_risk_block__wait | −0.8570 |
| action_close | −0.8415 |
| failure_type_card_expired | −0.7610 |
| segment_action_b2b__close | −0.5598 |
| action_wait | −0.5054 |
| segment_b2b | −0.4836 |
| failure_type_subscription_mandate_fail | −0.4796 |
| failure_action_card_expired__payment_link | +0.4460 |
| segment_b2c_returning | −0.4315 |
| failure_action_card_expired__close | −0.4311 |
| failure_type_customer_abandoned | −0.4278 |
| failure_action_network_timeout__wait | +0.4244 |
| segment_b2c_new | −0.4060 |
| failure_action_network_timeout__close | +0.4009 |
| failure_action_subscription_mandate_fail__wait | −0.3960 |
| failure_action_temporary_bank_decline__wait | +0.3857 |

### Required Checks

| # | Check | Value | Expected | Result |
|---|---|---|---|---|
| 1 | card_expired__payment_link | +0.4460 | Positive | **PASS** ✅ |
| 2 | subscription_mandate_fail__payment_link | +0.2944 | Positive | **PASS** ✅ |
| 3 | risk_score | −0.1412 | Negative | **PASS** ✅ |
| 4 | b2c_new__discount (+0.2709) > b2b__discount (−0.2494) | — | b2c > b2b | **PASS** ✅ |

All four checks reflect the data-generating process's known structure:
- `payment_link` is the right fix for expired cards and mandate failures (interaction bonuses in simulator)
- Higher risk → lower recovery
- New B2C customers respond better to discounts than B2B

These are associations learned by the model, not causal claims.

---

## Action-Conditional Proof

### Card Expired (Txn 2839)
| Action | P(recovery) |
|---|---|
| payment_link | **0.0793** |
| discount | 0.0404 |
| reminder | 0.0227 |
| wait | 0.0169 |
| close | 0.0122 |

→ `payment_link` is clearly the best action. Consistent with the simulator's
+1.0 interaction bonus for (card_expired, payment_link).

### Subscription Mandate Fail (Txn 6978)
| Action | P(recovery) |
|---|---|
| payment_link | **0.1249** |
| discount | 0.0732 |
| reminder | 0.0503 |
| close | 0.0327 |
| wait | 0.0305 |

→ `payment_link` dominates. Consistent with +0.9 simulator interaction.

### Temporary Bank Decline (Txn 6084)
| Action | P(recovery) |
|---|---|
| discount | **0.3150** |
| retry | 0.2842 |
| payment_link | 0.2506 |
| reminder | 0.2238 |
| wait | 0.2093 |
| close | 0.1529 |

→ `discount` slightly edges `retry`. Multiple actions are viable — this is a
case where the EV engine (M4) will matter because action costs differ.

### Network Timeout (Txn 9536)
| Action | P(recovery) |
|---|---|
| retry | **0.4887** |
| payment_link | 0.4417 |
| reminder | 0.3853 |
| wait | 0.3505 |
| close | 0.2921 |

→ `retry` is best. Network timeouts are often transient — retrying makes sense.

### Customer Abandoned (Txn 6667)
| Action | P(recovery) |
|---|---|
| discount | **0.1310** |
| payment_link | 0.0787 |
| reminder | 0.0526 |
| wait | 0.0507 |
| close | 0.0340 |

→ `discount` wins for abandonment. Overall probabilities are low — these are
hard-to-recover cases.

### Risk Block (Txn 9748)
| Action | P(recovery) |
|---|---|
| wait | 0.0033 |
| close | 0.0025 |

→ Only 2 actions eligible (by M1 eligibility matrix). Probabilities are near-zero.
This is correct: risk_block cases are fundamentally unsafe for automated recovery.

---

## Breakdown by Action

| Action | Count | AUC | Brier | Recovery Rate |
|---|---|---|---|---|
| retry | 978 | 0.6549 | 0.1982 | 30.27% |
| discount | 1,036 | 0.7606 | 0.1477 | 22.30% |
| payment_link | 1,437 | 0.7453 | 0.1460 | 21.29% |
| reminder | 1,437 | 0.7424 | 0.1288 | 17.61% |
| wait | 1,577 | 0.7646 | 0.1085 | 14.27% |
| close | 1,577 | 0.7732 | 0.0884 | 11.10% |

## Breakdown by Failure Type

| Failure Type | Count | AUC | Brier | Recovery Rate |
|---|---|---|---|---|
| network_timeout | 1,580 | 0.6454 | 0.2060 | 32.28% |
| temporary_bank_decline | 3,462 | 0.6685 | 0.1691 | 23.77% |
| insufficient_funds | 425 | 0.5882 | 0.0612 | 6.59% |
| card_expired | 795 | 0.7273 | 0.0524 | 5.79% |
| subscription_mandate_fail | 485 | 0.6666 | 0.0477 | 5.15% |
| customer_abandoned | 1,015 | 0.6416 | 0.0478 | 5.12% |
| risk_block | 280 | 0.5216 | 0.0071 | 0.71% |

---

## Leakage Checks (10 required)

| # | Check | Result |
|---|---|---|
| 1 | latent_score absent | **PASS** ✅ |
| 2 | hidden probability absent | **PASS** ✅ |
| 3 | noise absent | **PASS** ✅ |
| 4 | post-outcome info absent | **PASS** ✅ |
| 5 | outcome not an input feature | **PASS** ✅ |
| 6 | customer IDs no cross-split overlap | **PASS** ✅ |
| 7 | preprocessing fitted only on train | **PASS** ✅ (Pipeline enforced) |
| 8 | test data not used during selection | **PASS** ✅ (code structure) |
| 9 | no future information | **PASS** ✅ |
| 10 | excluded fields not in features | **PASS** ✅ |

---

## Reproducibility

| Item | Value |
|---|---|
| random_state | 42 |
| Data source | action_expanded_training_data.csv |
| Split method | Existing `split` column (customer-level) |
| Pipeline | ColumnTransformer → LogisticRegression |
| Converged | Yes (all configurations) |
| Result | Re-running with same config + data reproduces identical results |

**Reproducibility: PASS** ✅

---

## Business Boundary

> [!IMPORTANT]
> M2 does **not** prove the system beats a baseline — that is M5.
> M2 only establishes that the model produces useful, action-conditional,
> calibrated recovery probabilities. No causal claims. No "X% more revenue."

---

## Warnings

1. **`insufficient_funds` AUC = 0.5882** — near random. Small sample (425 rows in test)
   and low recovery rate (6.59%) make discrimination difficult. The model can still
   provide useful probability estimates but has limited ranking power for this failure type.

2. **`risk_block` AUC = 0.5216** — effectively random, but this is expected: only 280 test
   rows, only 2 eligible actions (wait/close), recovery rate 0.71%. There is almost no
   signal to discriminate. The policy engine (M3) will handle risk_block via hard rules,
   not ML predictions.

3. **`retry` AUC = 0.6549** — lower than other actions. Retry is available only for 3
   failure types (temporary_bank_decline, network_timeout, insufficient_funds), limiting
   the context diversity available for discrimination.
