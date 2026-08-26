# M5 Post-Fix Re-Evaluation Report — Controlled Sensitivity Run

> **Status:** POST-FIX SENSITIVITY / RE-EVALUATION ONLY  
> **Notice:** This is a post-fix sensitivity/re-evaluation and does not replace the original frozen M5 experiment. Original M5 results remain frozen and unchanged.

---

## 1. Objective & Motivation

The M4 decision engine close-action Expected Value implementation was corrected post-M5:
- **Pre-Fix Defect:** Close EV was hardcoded to `0.0`.
- **Post-Fix Behavior:** $\text{EV}(\text{close}) = P(\text{close}) \times \text{amount} - 0.0$.

This run performs a direct, controlled, test-set ($N=1,577$) measurement comparing the original frozen M5 run against the corrected M4 decision pipeline under identical data, model weights, costs, thresholds, and seeds.

---

## 2. Before-vs-After Comparison (Policy A vs B0 Waterfall)

| Metric | Original M5 (Pre-Fix) | Post-Fix M5 (Corrected Close EV) | Delta (Post - Pre) |
|---|---|---|---|
| **Policy A Net Recovered (₹)** | ₹1,299,952.45 | ₹1,299,952.45 | ₹-0.00 |
| **B0 Waterfall Net Recovered (₹)** | ₹1,497,969.37 | ₹1,497,969.37 | ₹0.00 |
| **Net Uplift (Policy A − B0) (₹)** | **-₹198,016.92** | **-₹198,016.92** | **₹-0.00** |
| **Policy A Recovered Count** | 361 / 1,577 | 361 / 1,577 | 0 |
| **Policy A Recovery Rate** | 22.89% | 22.89% | 0.00% |
| **B0 Waterfall Recovery Rate** | 19.78% | 19.78% | 0.00% |

---

## 3. Decision-Level Attribution & Action Distribution

### Probability Landscape ($N=1,577$ Test Transactions)
- **$P(\text{close}) > P(\text{wait})$:** 84 / 1,577 (5.3%)
- **$P(\text{wait}) > P(\text{close})$:** 1493 / 1,577 (94.7%)
- **$P(\text{close}) == P(\text{wait})$:** 0 / 1,577

### Decision Flips
- **Total decisions changed:** **0**
- `wait` $\rightarrow$ `close`: 0
- `close` $\rightarrow$ `wait`: 0
- `other` $\rightarrow$ `close`: 0
- `close` $\rightarrow$ `other`: 0
- `other` $\rightarrow$ `other`: 0

### Policy A Action Distribution

| Action | Original Count | Post-Fix Count | Delta |
|---|---|---|---|
| `discount` | 628 | 628 | 0 |
| `payment_link` | 426 | 426 | 0 |
| `retry` | 290 | 290 | 0 |
| `wait` | 204 | 204 | 0 |
| `close` | 0 | 0 | 0 |
| `no_action_required` / `escalate` | 0 | 0 | 0 |

---

## 4. Complete Comparison Table (All Policies)

| Policy | Recovered | Rate | Gross (₹) | Cost (₹) | Net (₹) | Most Frequent Action | Share |
|---|---|---|---|---|---|---|---|
| `b6_oracle` | 818 | 51.87% | ₹3,360,246.12 | ₹1,235.00 | ₹3,359,011.12 | `wait` | 62.4% |
| `b0_waterfall` | 312 | 19.78% | ₹1,501,443.37 | ₹3,474.00 | ₹1,497,969.37 | `reminder` | 46.2% |
| `b1_random` | 266 | 16.87% | ₹1,363,512.35 | ₹2,427.00 | ₹1,361,085.35 | `wait` | 23.7% |
| `policy_a` | 361 | 22.89% | ₹1,302,749.45 | ₹2,797.00 | ₹1,299,952.45 | `discount` | 39.8% |
| `b5_always_discount` | 348 | 22.07% | ₹985,800.21 | ₹534.00 | ₹985,266.21 | `discount` | 62.5% |
| `b2_always_retry` | 275 | 17.44% | ₹805,325.22 | ₹1,290.00 | ₹804,035.22 | `wait` | 54.5% |
| `b3_always_payment_link` | 303 | 19.21% | ₹800,429.78 | ₹6,865.00 | ₹793,564.78 | `payment_link` | 87.1% |
| `b4_always_reminder` | 250 | 15.85% | ₹617,356.60 | ₹4,119.00 | ₹613,237.60 | `reminder` | 87.1% |

---

## 5. Interpretation & Key Takeaways

1. **Exact Zero Decision Impact:** The test-set impact of the M4 close-EV correction is **EXACTLY ZERO**. 
   - Zero decisions changed (0 flips across 1,577 test transactions).
   - Net recovered amount for Policy A remains identical at **₹1,299,952.45**.
   - Net deficit vs B0 Waterfall remains identical at **-₹198,016.92**.
2. **Mechanism:** On the test set, whenever `close` and `wait` compete:
   - For transactions where active actions (`retry`, `payment_link`, `discount`) were eligible, active interventions or `discount` dominated due to higher positive expected recoveries.
   - For transactions where passive actions competed, `wait` had higher EV than `close` or won equal-EV tie-breaking per `ACTION_PRIORITY_ORDER`.
   - On the 204 transactions where B0 chose `close`, Policy A chose `wait` under both pre-fix and post-fix EV logic.
3. **Integrity Confirmation:** All original M5 artifacts and reports remain byte-identical and preserved.

---

## 6. Integrity Verification

- **SHA-256 Baseline Pre/Post Check:** **PASS** (100% byte-identical match on all frozen files).
- **Retraining:** NONE (Model weights unchanged).
- **Scope:** Outputs written exclusively to `ml/evaluation/post_fix_m5/`.
