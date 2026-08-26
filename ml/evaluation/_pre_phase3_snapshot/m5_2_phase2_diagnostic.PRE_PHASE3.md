# M5.2 Phase 2 Diagnostic Report — Validation-Only Root-Cause Quantification (Authoritative rev 2)

## 1. Executive Summary

This authoritative Phase 2 investigation establishes the empirical and structural causes of the M5 experiment results using **validation-split counterfactuals (OP-V)**, **read-only inspection of frozen test artifacts (OP-F)**, and **cross-split stability analysis**. No test-set decisions were re-evaluated, and no production code or milestone configurations were modified.

### Key Conclusions:
1. **The `close` EV=0 hardcoding is an implementation defect, but it is NOT the root cause of the M5 loss (H4 is CLOSED AS FALSE).**
   - On validation (OP-V), while P(close) > P(wait) in 87 transactions (6.06%), corrected EV(close) = P(close) * A - 0.0 changed exactly **0 decisions** out of 1,435 and yielded **₹0.00** net value delta.
   - This is because on all 87 transactions where close beat wait, other active interventions (e.g. discount, payment_link, retry) had strictly higher EV than close.
2. **M2 carries real, statistically unambiguous within-transaction cross-action ranking signal (Case i confirmed).**
   - Pairwise cross-action concordance on validation (OP-V) is **0.6223** (95% CI [0.6071, 0.6376], N = 3,879 discordant-outcome pairs), which is **15.68 standard errors above the 0.50 null (p < 1e-15)**.
   - Value-weighted concordance is **0.6468**, proving that ranking quality does not degrade on high-value transactions.
   - Decision agreement with the Oracle (B6) is **23.1% for Policy A vs 12.1% for B0** overall (1.91x), expanding to **44.4% for Policy A vs 8.3% for B0** on the top amount decile (5.35x).
3. **The decision engine extracts signal; it does not amplify noise.**
   - Shrinkage sweep (P3, OP-V) with allowed-only P_bar targets shows net value is **monotone increasing with lambda** (+₹156,669.06 / +14.5% from lambda=0.0 to lambda=1.0).
   - Even at lambda=0.0 (relying purely on marginal action averages without per-transaction features), Policy A achieves **₹1,078,896.67**, outperforming B0's validation net of **₹989,434.95**.
4. **The -₹247,410 `wait -> close` substitution in M5 reflects heavy-tailed sampling variance on a structurally hard subset (OP-F).**
   - On the 204 test transactions where Policy A chose `wait` and B0 chose `close`, `close` recovered **8 transactions (3.9%)** for ₹596,379.05, while `wait` recovered **6 transactions (2.9%)** for ₹348,969.49.
   - Just **3 close-only recoveries** (Txn 1998, Txn 7703, Txn 196) account for **₹329,675.72 (133.2%)** of the -₹247,410 gap.
5. **Cross-Split Stability Headline:**
   - Policy A's per-transaction net recovery is remarkably stable: **₹861.02 on validation vs ₹824.32 on test (-4.3%)**.
   - B0's per-transaction net jumps **+37.8%** (from ₹689.50 on validation to ₹949.89 on test), driven by the 3 outlier recoveries.
   - The cross-split gap swing of **₹444,147.70** is well within the test bootstrap 95% CI width (₹1,108,876.31).

---

## 2. A0 — M2 Feature Construction and Ordering Census (OP-V) [GATE]

### A0.1 Source Audit
- **Code Quote from `train_model.py`:**
```python
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
```
- **Total Features:** 12 feature matrix columns passed to `ColumnTransformer` (6 categorical, 6 numeric with log1p transforms).
- **Action Representation:** Action appears as an indicator column (`action`) **AND** in interaction terms (`failure_action = failure_type__action`, `segment_action = segment__action`).
- **Metadata Check:** `ml/models/model_metadata.json` confirms model type `LogisticRegression` with the exact 12 feature columns.

### A0.2 Ordering Census
Across all 1,435 validation transactions:
- **Distinct Full Orderings Observed:** **13** distinct action permutations.
- **Top 5 Full Orderings:**
  1. `discount > retry > payment_link > reminder > wait > close`: 554 txns (38.6%)
  2. `retry > discount > payment_link > reminder > wait > close`: 153 txns (10.7%)
  3. `retry > payment_link > discount > reminder > wait > close`: 126 txns (8.8%)
  4. `payment_link > retry > discount > reminder > wait > close`: 117 txns (8.2%)
  5. `payment_link > discount > retry > reminder > wait > close`: 116 txns (8.1%)

### Key Action-Pair Orderings:
- **`close` vs `wait`:** `wait > close` in **1,348 txns (93.9%)**, `close > wait` in **87 txns (6.1%)** (Ties: 0). Min diff = 0.0001, Median diff = 0.0347, Max diff = 0.0841.
- **`retry` vs `discount`:** `discount > retry` in **885 txns (61.7%)**, `retry > discount` in **550 txns (38.3%)**.
- **`payment_link` vs `reminder`:** `payment_link > reminder` in **1,365 txns (95.1%)**, `reminder > payment_link` in **70 txns (4.9%)**.

### A0.3 Consistency Test against Selection Distribution
- Validation Amount Range: [**₹97.03**, **₹279,558.65**]
- Action Policy-Allowed vs M4 Actual Selections:
  - `retry`: Allowed = 567, Selected = 260
  - `payment_link`: Allowed = 1,261, Selected = 411
  - `reminder`: Allowed = 1,261, Selected = 35
  - `discount`: Allowed = 918, Selected = 555
  - `wait`: Allowed = 1,435, Selected = 174
  - `close`: Allowed = 1,435, Selected = 0

### A0.4 Gate Verdict
**A0 VERDICT: INTERACTIONS PRESENT**
Interaction terms (`failure_action` and `segment_action`) cause action rankings to vary meaningfully across customer segments and failure types, producing 13 distinct action orderings.

---

## 3. A1 — Recomputed P(close) > P(wait) on Validation (OP-V)

- **`P(close) > P(wait)`:** **87 txns (6.06%)**
- **`P(wait) > P(close)`:** **1,348 txns (93.94%)**
- **`P(close) == P(wait)`:** **0 txns (0.00%)**

### Counterfactual Simulation:
- Corrected EV(close) = P(close) * A - 0.0 resulted in **0 decision flips** and **₹0.00 net value change**.
- **Verdict on H4:** **CLOSED AS FALSE** (accounts for ₹0.00 of the performance gap).

---

## 4. A2 — Accounting Convention and Rebuilt Policy Rows

### A2.1 Determined Convention
From [`ml/experiment/experiment_metrics.py`](file:///c:/Users/ADMIN/Desktop/recovery/ml/experiment/experiment_metrics.py#L43-L53):
**The code implements Convention C1 (gross is POST-haircut).**
- For `discount`, `recovered_amount = amount * (1 - discount_percent/100)`.
- `net_recovered_amount = recovered_amount - intervention_cost`.
- `discount_amount` is a reporting-only column and is never subtracted a second time.

### A2.2 Policy Comparison Table
| Split | Data Op | Policy | Txns | Recovered | Rate (95% CI) | Gross Amount (₹) | Cost (₹) | Discount [rpt] (₹) | Net Amount (₹) | Net / Txn (₹) |
|---|---|---|---|---|---|---|---|---|---|---|
| **Validation** | OP-V | **Policy A** | 1,435 | 326 | 22.72% [±2.17%] | ₹1,238,245.73 | ₹2,680.00 | ₹38,468.39 | **₹1,235,565.73** | **₹861.02** |
| **Validation** | OP-V | **B0 Waterfall** | 1,435 | 272 | 18.95% [±2.04%] | ₹992,650.95 | ₹3,216.00 | ₹0.00 | **₹989,434.95** | **₹689.50** |
| **Test** | OP-F | **Policy A** | 1,577 | 361 | 22.89% [±2.07%] | ₹1,302,749.45 | ₹2,797.00 | ₹40,673.29 | **₹1,299,952.45** | **₹824.32** |
| **Test** | OP-F | **B0 Waterfall** | 1,577 | 312 | 19.78% [±1.97%] | ₹1,501,443.37 | ₹3,474.00 | ₹0.00 | **₹1,497,969.37** | **₹949.89** |
| **Test** | OP-F | **B1 Random** | 1,577 | 266 | 16.87% [±1.85%] | ₹1,363,512.35 | ₹2,427.00 | ₹11,300.31 | **₹1,361,085.35** | **₹863.09** |
| **Test** | OP-F | **B6 Oracle** | 1,577 | 818 | 51.87% [±2.46%] | ₹3,360,246.12 | ₹1,235.00 | ₹37,399.62 | **₹3,359,011.12** | **₹2,129.37** |

*Accounting Identity Check (ACC-1):* Net = Gross - Cost holds exactly on all 6 rows (tolerance 0.01).

---

## 5. A3 — P3 Shrinkage Sweep (OP-V)

Shrinkage targets computed over **policy-allowed populations**:
- `retry`: P_bar = 0.3329 (N = 567)
- `payment_link`: P_bar = 0.2173 (N = 1,261)
- `reminder`: P_bar = 0.1794 (N = 1,261)
- `discount`: P_bar = 0.2197 (N = 918)
- `wait`: P_bar = 0.1381 (N = 1,435)
- `close`: P_bar = 0.1029 (N = 1,435)

### Sweep Results:
| $\lambda$ | Description | Net Amount (₹) | Prior Sweep (₹) | Delta (₹) | Rec Count | Rec Rate | Action Distribution |
|---|---|---|---|---|---|---|---|
| **0.00** | Marginal Means Only | **₹1,078,896.67** | ₹1,058,557.21 | +₹20,339.46 | 288 | 20.07% | `{'payment_link': 691, 'retry': 567, 'wait': 174, 'discount': 3}` |
| **0.25** | Shrunk 75% | **₹1,090,067.85** | ₹1,139,204.48 | -₹49,136.63 | 290 | 20.21% | `{'payment_link': 573, 'retry': 567, 'wait': 174, 'discount': 121}` |
| **0.50** | Shrunk 50% | **₹1,103,310.75** | ₹1,182,206.78 | -₹78,896.03 | 294 | 20.49% | `{'retry': 567, 'payment_link': 429, 'discount': 265, 'wait': 174}` |
| **0.75** | Shrunk 25% | **₹1,196,671.25** | ₹1,183,920.74 | +₹12,750.51 | 319 | 22.23% | `{'discount': 480, 'retry': 385, 'payment_link': 380, 'wait': 174, 'reminder': 16}` |
| **1.00** | Current M4 (Full Signal) | **₹1,235,565.73** | ₹1,235,565.73 | ₹0.00 | 326 | 22.72% | `{'discount': 555, 'payment_link': 411, 'retry': 260, 'wait': 174, 'reminder': 35}` |

*Harness Assertion (P3-1):* $\lambda = 1.0$ matches Live Class H M4 validation baseline within ₹0.00 and achieves **100.0% decision agreement**.
*Interpretation:* Net value increases monotonically (+14.5%) from lambda=0.0 to lambda=1.0, demonstrating genuine signal extraction.

---

## 6. A4 — P5 Partition on the 204 Test Transactions (OP-F)

Derived directly from raw frozen test artifacts (`per_transaction_decisions.csv` joined with realized outcomes):

### Exact 4-Way Partition Table
| Partition Category | Count ($N$) | Total Amount (₹) | Description |
|---|---|---|---|
| **CLOSE_ONLY** | **7** | **₹529,259.10** | Recovered by B0 `close`, failed under Policy A `wait` |
| **WAIT_ONLY** | **5** | **₹281,849.54** | Recovered by Policy A `wait`, failed under B0 `close` |
| **BOTH** | **1** | **₹67,119.95** | Recovered under both policies (Txn 4518) |
| **NEITHER** | **191** | **₹6,044,992.33** | Failed under both policies |
| **Total B0 `close` Recoveries** | **8 (3.92%)** | **₹596,379.05** | Sum of CLOSE_ONLY + BOTH |
| **Total Policy A `wait` Recoveries** | **6 (2.94%)** | **₹348,969.49** | Sum of WAIT_ONLY + BOTH |
| **Net Difference (`wait - close`)** | **-2** | **-₹247,409.56** | Exact match with D4 line item |

### Top 3 Close-Only Recoveries:
1. **Txn 1998**: Amount = **₹139,904.76** (`network_timeout`)
2. **Txn 7703**: Amount = **₹114,085.35** (`temporary_bank_decline`)
3. **Txn 196**: Amount = **₹75,685.61** (`temporary_bank_decline`)
- **Sum of Top 3 Close-Only Outliers:** **₹329,675.72** (**133.2%** of the -₹247,410 gap; **166.5%** of the -₹198,017 test deficit).

---

## 7. A5 — Attribution with an Explicit Unexplained Residual

| Component Name | Value (₹) | % of Test Gap | Citation | Split | Data Op |
|---|---|---|---|---|---|
| **Passive tail outcome sampling variance (`wait` vs `close` on 204 txns)** | -₹247,410.00 | 124.9% | Section A4 / `a4_partition_summary.json` | Test | OP-F |
| **Active intervention value gains (`discount` / `payment_link`)** | +₹150,157.08 | -75.8% | Frozen M5 D4 substitution matrix | Test | OP-F |
| **UNEXPLAINED RESIDUAL (Cross-split sampling variance)** | **-₹100,764.00** | **50.9%** | Arithmetic difference: `Total - Sum(Components)` | Test | OP-F |
| **Total Test Split Deficit** | **-₹198,016.92** | **100.0%** | Frozen M5 Result Block | Test | OP-F |

*Attribution Assertion (ATTR-1):* Sum(Components) + Unexplained = -₹198,016.92 (Exact match, tolerance 0.01).

---

## 8. A6 — Calibration with Standard Errors and 95% CIs (OP-V)

### Per-Action Calibration on Policy-Allowed Validation Population
| Action | $N$ (Allowed) | Mean Predicted | Realized Rate | Signed Gap | SE | 95% CI | CI Excludes 0 |
|---|---|---|---|---|---|---|---|
| `retry` | 567 | 0.3329 | 0.3404 | +0.0075 | 0.0188 | [-0.0294, +0.0444] | NO |
| `payment_link` | 1,261 | 0.2173 | 0.2133 | -0.0040 | 0.0109 | [-0.0255, +0.0174] | NO |
| `reminder` | 1,261 | 0.1794 | 0.1594 | -0.0200 | 0.0099 | [-0.0393, -0.0007] | **YES** |
| `discount` | 918 | 0.2197 | 0.2211 | +0.0014 | 0.0130 | [-0.0240, +0.0268] | NO |
| `wait` | 1,435 | 0.1381 | 0.1352 | -0.0029 | 0.0085 | [-0.0195, +0.0137] | NO |
| `close` | 1,435 | 0.1029 | 0.1101 | +0.0073 | 0.0078 | [-0.0080, +0.0225] | NO |

### Reminder Calibration by Amount Decile ($N = 1,261$)
| Decile | Amount Range (₹) | $N$ | Mean Predicted | Realized Rate | Signed Gap | SE | 95% CI | CI Excludes 0 |
|---|---|---|---|---|---|---|---|---|
| 0 | ₹97 – ₹677 | 132 | 0.2391 | 0.1970 | -0.0422 | 0.0320 | [-0.1049, +0.0206] | NO |
| 1 | ₹679 – ₹975 | 135 | 0.2006 | 0.2296 | +0.0290 | 0.0341 | [-0.0377, +0.0957] | NO |
| 2 | ₹975 – ₹1,278 | 128 | 0.2145 | 0.1641 | -0.0504 | 0.0321 | [-0.1134, +0.0125] | NO |
| 3 | ₹1,283 – ₹1,574 | 132 | 0.1894 | 0.1818 | -0.0075 | 0.0314 | [-0.0692, +0.0541] | NO |
| 4 | ₹1,576 – ₹1,942 | 130 | 0.1772 | 0.1231 | -0.0541 | 0.0291 | [-0.1112, +0.0030] | NO |
| 5 | ₹1,945 – ₹2,495 | 125 | 0.1707 | 0.1520 | -0.0187 | 0.0311 | [-0.0796, +0.0422] | NO |
| 6 | ₹2,497 – ₹3,080 | 127 | 0.1632 | 0.1811 | +0.0179 | 0.0335 | [-0.0477, +0.0835] | NO |
| 7 | ₹3,115 – ₹4,491 | 133 | 0.1517 | 0.1128 | -0.0389 | 0.0269 | [-0.0916, +0.0138] | NO |
| 8 | ₹4,536 – ₹10,786 | 131 | 0.1443 | 0.1298 | -0.0146 | 0.0281 | [-0.0697, +0.0406] | NO |
| 9 | ₹11,085 – ₹49,547 | 88 | 0.1242 | 0.1023 | -0.0219 | 0.0314 | [-0.0835, +0.0397] | NO |

*Statistical Finding:* **0 out of 10 deciles** have 95% confidence intervals excluding zero. The apparent widening on high amounts is not statistically distinguishable from sampling noise at this sample size.

---

## 9. Cross-Split Stability (Headline Finding)

| Metric | Validation Split (OP-V) | Test Split (OP-F) | Cross-Split Shift |
|---|---|---|---|
| **Transactions ($N$)** | 1,435 | 1,577 | +9.9% |
| **Policy A Net Total** | ₹1,235,565.73 | ₹1,299,952.45 | +5.2% |
| **Policy A Net Per Txn** | **₹861.02** | **₹824.32** | **-4.3% (STABLE)** |
| **B0 Waterfall Net Total** | ₹989,434.95 | ₹1,497,969.37 | +51.4% |
| **B0 Net Per Txn** | **₹689.50** | **₹949.89** | **+37.8% (VOLATILE)** |
| **Policy A minus B0 Net** | **+₹246,130.78 (+24.9%)** | **-₹198,016.92 (-13.22%)** | **₹444,147.70 SWING** |
| **Oracle (B6) Net Total** | ₹2,987,838.35 | ₹3,359,011.12 | +12.4% |
| **Oracle Net Per Txn** | ₹2,082.12 | ₹2,129.37 | +2.3% |
| **Max Transaction Amount** | ₹279,558.65 | ₹139,904.76 | — |
| **Top 1% Value Share** | 15.2% | 16.1% | — |

The total gap swing of **₹444,147.70** is well inside the test bootstrap 95% CI width of **₹1,108,876.31** ([-₹776,314, +₹332,562]).

---

## 10. Assertion Results & Class R Comparisons

### Assertion Harness Results
| ID | Target Class | Description | Status | Details |
|---|---|---|---|---|
| **ACC-1** | raw-derived | Accounting identity holds for every policy row under C1 | **PASS** | Net = Gross - Cost verified on all 6 rows |
| **ACC-2** | raw-derived | Every count in prose equals artifact count | **PASS** | Automated mechanical substitution |
| **ORD-1** | raw-derived | Distinct orderings per pair is 1 or 2 | **PASS** | 15 pairs verified; 13 full orderings |
| **ORD-2** | raw-derived | A0.4 verdict consistent with feature interactions | **PASS** | Verdict: INTERACTIONS PRESENT |
| **P3-1** | Class H | $\lambda=1.0$ reproduces LIVE frozen M4 validation baseline | **PASS** | Net diff = ₹0.00, Agreement = 100.0% |
| **P3-2** | raw-derived | $\lambda=0$ matches independent derivation | **PASS** | 100% per-transaction distribution match |
| **P3-3** | raw-derived | Sweep deltas versus prior sweep explained | **PASS** | Allowed-only Pbar denominator verified |
| **P5-1..5** | raw-derived | Five partition assertions pass exactly | **PASS** | All 5 balance identities hold (residual = ₹0.00) |
| **ATTR-1** | raw-derived | Components + Unexplained == Total | **PASS** | Sum = -₹198,016.92 |
| **ATTR-2** | raw-derived | Every component has non-empty citation | **PASS** | All citations verified |
| **CAL-1** | raw-derived | Every calibration row has SE, CI low, CI high | **PASS** | Checked all action, decile, and bias rows |
| **CAL-2** | raw-derived | No CI-spanning-zero figure described in finding language | **PASS** | Verified across all tables and prose |
| **SPLIT-1** | raw-derived | Every table declares split and data op | **PASS** | OP-V / OP-F declared without mixing splits |

### Class R Comparisons
| Item | Class R Prior Value | Computed Value | Status |
|---|---|---|---|
| P(close) > P(wait) on validation | 87 (draft 1) / 0 (draft 2) | **87** | AGREE (with draft 1) |
| Policy A validation recovered count | 326 (draft 1) / 329 (draft 2) | **326** | AGREE (with draft 1) |
| B0 validation net | ₹989,434.95 | **₹989,434.95** | AGREE |
| P5 `wait` recoveries on 204 | 31 (draft 1 data error) | **6** | DISAGREE (prior was data error) |
| P5 `close` recoveries on 204 | 8 | **8** | AGREE |
| Top 3 close-only sum | ₹329,676.00 / ₹323,945.00 | **₹329,675.72** | AGREE (with draft 1 reference) |
| P2 Concordance rate | 0.52 (draft 1 text) / 0.6223 (draft 2) | **0.6223** | AGREE (with draft 2) |
| M4 validation net baseline | ₹1,235,565.73 | **₹1,235,565.73** | AGREE |

---

## 11. RECOMMENDATION — NO CODE CHANGES MADE

### Status Attestations:
- **M1–M5 Code:** UNCHANGED
- **Tests:** UNCHANGED
- **`ev_engine.py`:** UNCHANGED
- **M2 Retrained:** NO
- **Test Set Re-Decided:** NO
- **Frozen M5 Results:** PRESERVED
- **M6:** NOT RUN
- **Commits:** NONE
- **Fixes Implemented:** NONE

### Recommended Engineering Roadmap (for subsequent milestones):
1. **`close` EV=0 Hardcode:** A correctness defect with **zero measured value impact** (0 decisions changed, ₹0.00 net on validation, analytic upper bound of 0 flips). Fix for structural reachability and integrity of the reachability audit, documenting that it recovers no value. *(Requires narrow lock-lift, not yet approved)*.
2. **M4 Test 12:** Rewrite Test 12 to test a reachable path, and add a new test asserting that `wait` wins over `close` on an EV tie via `ACTION_PRIORITY_ORDER`.
3. **M5 Reporting:** Reframe M5 reporting to reflect the cross-split variance finding (Policy A +24.9% on validation vs -13.2% on test, with Policy A stable to -4.3% while B0 shifts +37.8%), retaining the frozen original test numbers and bootstrap CI verbatim alongside.
4. **`reminder` Calibration:** Measure and report the validation gap. No model retraining is authorized by present evidence.
5. **Future Evaluation Reporting:** Any future measurement of net recovered value on this heavy-tailed amount distribution must report **both splits** or state the statistical power limitations explicitly.
