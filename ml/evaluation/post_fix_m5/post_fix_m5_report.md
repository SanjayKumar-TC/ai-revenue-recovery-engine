# M5 Post-Fix Re-Evaluation Report — Controlled Sensitivity Run

> **STATUS:** COMPLETED (CONTROLLED SENSITIVITY RUN ONLY)  
> **CLASSIFICATION:** POST-FIX SENSITIVITY / RE-EVALUATION ONLY  
> **IMPORTANT NOTICE:** This is a post-fix sensitivity/re-evaluation and does not replace the original frozen M5 experiment. Original M5 results remain frozen and unchanged.

---

## 1. Objective & Background

### Context
During post-M5 analysis (specifically M5.2 Phase 2/3 and M4 closeout), a defect in the M4 Expected Value engine was identified and corrected:
- **Pre-Fix Defect (`ml/decision/ev_engine.py`):** The EV for the `close` action was hardcoded to `0.0`, regardless of predicted natural recovery probability $P(\text{close})$.
- **Corrected Behavior:** Standardized EV calculation:
  $$\text{EV}(\text{close}) = P(\text{recovery} \mid \text{close}) \times \text{amount} - \text{ACTION\_COSTS}[\text{"close"}] = P(\text{close}) \times \text{amount} - 0.0$$

### Motivation
While M5.2 Phase 2 task A1 demonstrated zero decision flips on the **validation split** ($N=1,435$), this controlled post-fix evaluation measures the exact before-vs-after effect on the **held-out test set** ($N=1,577$).

### Run Design & Preservation
- **Model:** Pre-trained M2 Logistic Regression model weights (`recovery_model.joblib`) were loaded directly without retraining.
- **Population:** Exact 1,577 test transactions from `action_expanded_with_hidden_truth.csv`.
- **Logic:** Evaluated with the corrected M4 decision engine (`ml/decision/ev_engine.py`) against all 7 baselines (B0–B6).
- **Integrity:** Zero modifications to original M5 reports, M5/M5.2 artifacts, model weights, or upstream milestone code. All outputs written strictly to `ml/evaluation/post_fix_m5/`.

---

## 2. Executive Summary & Headline Result

```
========================================================================================
M5 TEST SET POST-FIX SENSITIVITY SUMMARY (N = 1,577)
========================================================================================
Policy A Net Recovered (Pre-Fix):             ₹1,299,952.45
Policy A Net Recovered (Post-Fix):            ₹1,299,952.45
Delta in Policy A Net Recovered:                      ₹0.00  (EXACT ZERO)

B0 Waterfall Net Recovered (Pre-Fix):         ₹1,497,969.37
B0 Waterfall Net Recovered (Post-Fix):        ₹1,497,969.37
Net Uplift vs B0 (Pre-Fix):                    -₹198,016.92  (-13.22%)
Net Uplift vs B0 (Post-Fix):                   -₹198,016.92  (-13.22%)
Delta in Net Uplift:                                  ₹0.00  (EXACT ZERO)

Total Decisions Changed:                                  0  (0 / 1,577)
Effect Classification:                                 ZERO
========================================================================================
```

---

## 3. Before-vs-After Comparison Table

| Metric | Original M5 (Pre-Fix) | Post-Fix M5 (Corrected Close EV) | Delta (Post − Pre) |
|---|---|---|---|
| **Policy A Net Recovered (₹)** | ₹1,299,952.45 | ₹1,299,952.45 | ₹0.00 |
| **B0 Waterfall Net Recovered (₹)** | ₹1,497,969.37 | ₹1,497,969.37 | ₹0.00 |
| **Net Recovery Uplift (Policy A − B0) (₹)** | **-₹198,016.92** | **-₹198,016.92** | **₹0.00** |
| **Percentage Uplift vs B0** | -13.22% | -13.22% | 0.00% |
| **Paired Bootstrap 95% CI** | [-₹776,313.86, +₹332,562.45] | [-₹776,313.86, +₹332,562.45] | [₹0.00, ₹0.00] |
| **CI Excludes Zero** | No | No | — |
| **Policy A Recovery Count** | 361 / 1,577 | 361 / 1,577 | 0 |
| **Policy A Recovery Rate** | 22.89% | 22.89% | 0.00% |
| **B0 Waterfall Recovery Count** | 312 / 1,577 | 312 / 1,577 | 0 |
| **B0 Waterfall Recovery Rate** | 19.78% | 19.78% | 0.00% |
| **Oracle (B6) Net Recovered (₹)** | ₹3,359,011.12 | ₹3,359,011.12 | ₹0.00 |
| **Headroom Captured (B0 → B6)** | -10.64% | -10.64% | 0.00% |

---

## 4. Full Policy Benchmark Comparison

| Policy | Recovered Count | Recovery Rate (%) | Gross Recovered (₹) | Total Cost (₹) | Net Recovered (₹) | Most Frequent Action | Share (%) |
|---|---|---|---|---|---|---|---|
| `b6_oracle` | 818 | 51.87% | ₹3,360,246.12 | ₹1,235.00 | ₹3,359,011.12 | `wait` | 62.4% |
| `b0_waterfall` | 312 | 19.78% | ₹1,501,443.37 | ₹3,474.00 | ₹1,497,969.37 | `reminder` | 46.2% |
| `b1_random` | 266 | 16.87% | ₹1,363,512.35 | ₹2,427.00 | ₹1,361,085.35 | `wait` | 23.7% |
| **`policy_a`** | **361** | **22.89%** | **₹1,302,749.45** | **₹2,797.00** | **₹1,299,952.45** | **`discount`** | **39.8%** |
| `b5_always_discount` | 348 | 22.07% | ₹985,800.21 | ₹534.00 | ₹985,266.21 | `discount` | 62.5% |
| `b2_always_retry` | 275 | 17.44% | ₹805,325.22 | ₹1,290.00 | ₹804,035.22 | `wait` | 54.5% |
| `b3_always_payment_link` | 303 | 19.21% | ₹800,429.78 | ₹6,865.00 | ₹793,564.78 | `payment_link` | 87.1% |
| `b4_always_reminder` | 250 | 15.85% | ₹617,356.60 | ₹4,119.00 | ₹613,237.60 | `reminder` | 87.1% |

---

## 5. Decision-Level Attribution & Action Distribution Analysis

### 5.1 Test-Set Predicted Probability Census ($N=1,577$)
Comparing predicted natural recovery probability $P(\text{close})$ against $P(\text{wait})$ across all test transactions:
- **$P(\text{close}) > P(\text{wait})$:** 96 transactions (6.09%)
- **$P(\text{wait}) > P(\text{close})$:** 1,481 transactions (93.91%)
- **$P(\text{close}) == P(\text{wait})$:** 0 transactions (0.00%)

### 5.2 Decision Flips by Transition Category
Every single test transaction was audited for decision changes between pre-fix and post-fix M4:

| Transition Category | Flips Count | Description |
|---|---|---|
| `wait` $\rightarrow$ `close` | **0** | No wait decisions flipped to close |
| `close` $\rightarrow$ `wait` | **0** | No close decisions flipped to wait |
| `other` $\rightarrow$ `close` | **0** | No active interventions flipped to close |
| `close` $\rightarrow$ `other` | **0** | No close decisions flipped to active interventions |
| `other` $\rightarrow$ `other` | **0** | No other action substitutions occurred |
| **Total Changed** | **0** | **100.0% Decision Concordance Across All 1,577 Transactions** |

### 5.3 Policy A Action Distribution

| Action | Pre-Fix Count | Post-Fix Count | Delta | Pre-Fix Share | Post-Fix Share |
|---|---|---|---|---|---|
| `discount` | 628 | 628 | 0 | 39.82% | 39.82% |
| `payment_link` | 426 | 426 | 0 | 27.01% | 27.01% |
| `retry` | 319 | 319 | 0 | 20.23% | 20.23% |
| `wait` | 204 | 204 | 0 | 12.94% | 12.94% |
| `close` | 0 | 0 | 0 | 0.00% | 0.00% |
| `no_action_required` | 0 | 0 | 0 | 0.00% | 0.00% |
| `escalate` | 0 | 0 | 0 | 0.00% | 0.00% |
| **Total** | **1,577** | **1,577** | **0** | **100.0%** | **100.0%** |

---

## 6. Technical Explanation of the Zero-Effect Finding

Why did the close-EV fix produce zero decision flips and ₹0.00 net value change on the test set?

1. **Dominance of Active Interventions on Non-Passive Transactions:**
   - On transactions where active interventions (`discount`, `payment_link`, `retry`) were allowed by M3 policy, model predictions for active recovery were significantly higher than passive recovery probabilities ($P(\text{close})$ and $P(\text{wait})$). 
   - Even with non-zero close EV ($\text{EV}(\text{close}) = P(\text{close}) \times \text{amount}$), active actions yielded higher net EV, maintaining Policy A's selection of active interventions.
2. **`wait` Dominance over `close` on Passive Transactions:**
   - On the 204 transactions where Policy A chose `wait` (and where B0 waterfall chose `close`), $P(\text{wait})$ was strictly greater than $P(\text{close})$ for the vast majority of cases ($1,481 / 1,577 = 93.91\%$).
   - For the 96 transactions where $P(\text{close}) > P(\text{wait})$, active interventions (`discount`, `payment_link`, or `retry`) were permitted and possessed higher expected net recovery than $\text{EV}(\text{close})$, so `close` never won the EV optimization step.
3. **Priority Tie-Break Protection:**
   - In `ACTION_PRIORITY_ORDER` (`["retry", "wait", "reminder", "payment_link", "discount", "close"]`), `wait` sits at index 1 while `close` sits at index 5. In any potential equal-EV scenario within tolerance $\epsilon = 10^{-6}$, `wait` wins the tiebreak.
4. **Summary:**
   - The close-EV correction is mathematically and logically sound, fixing a real architectural defect, but its empirical effect on the test set is **identically zero**.

---

## 7. Integrity Verification & Audit Record

All pre-run and post-run integrity gates were verified:

| File / Artifact | Classification | Verification Status | Details |
|---|---|---|---|
| `ml/experiment/results/comparison_table.csv` | Original M5 Benchmark | **PRESERVED** | Byte-identical, untouched |
| `ml/experiment/results/per_transaction_decisions.csv` | Original M5 Per-Txn Decisions | **PRESERVED** | Byte-identical, untouched |
| `ml/evaluation/m5_report.md` | Original M5 Report | **PRESERVED** | Byte-identical, untouched |
| `ml/evaluation/m5_2_phase2_diagnostic.md` | M5.2 Phase 2/3 Diagnostic | **PRESERVED** | Byte-identical, untouched |
| `ml/evaluation/phase2_artifacts/*` | M5.2 Phase 2/3 Artifacts (31 files) | **PRESERVED** | Byte-identical, untouched |
| `ml/models/recovery_model.joblib` | M2 Model Weights | **PRESERVED** | Zero retraining performed |
| `ml/evaluation/post_fix_m5/*` | Post-Fix Evaluation Directory | **NEW OUTPUTS ONLY** | Created cleanly in dedicated folder |

---

## 8. Conclusion

This controlled sensitivity run proves that the completed M4 close-EV fix:
- Has **zero effect** on test-set policy decisions (0 / 1,577 flips).
- Has **₹0.00 net value impact** on Policy A's performance.
- Preserves the original M5 headline finding and -₹198,016.92 gap vs B0 Waterfall.
- Confirms the findings of M5.2 Phase 2 Task A1 with direct test-set empirical proof.

*Original M5 experiment results remain fully preserved and authoritative.*
