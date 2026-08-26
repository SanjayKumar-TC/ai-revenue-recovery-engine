# M5.2 Phase 3 Diagnostic Report — Authoritative Phase 3

> **Phase 3 Note:** All numbers in the generated body are substituted from the FIGURES registry (artifacts).
> Class R REFERENCE figures are explicitly labeled.
>
> **Report-only integrity repair.** This document has since received a report-only integrity repair:
> narrative wording, methodology notes, and restored explanatory sections were edited by hand so that the
> prose accurately describes what the authoritative run computed. Every numeric value in a repaired passage
> is transcribed from a named authoritative artifact, and each such passage cites that artifact. NO
> computation, source file, test, threshold, seed, split, model, cost, or frozen artifact was changed, and
> the authoritative script was NOT rerun. Because the body is emitted from literal strings inside
> `generate_report()` in `m5_2_phase2_authoritative_run.py`, and that file is out of scope for this repair,
> a future rerun of the authoritative script will regenerate the body and revert these narrative edits.

<!-- LIT1_EXEMPT_START: artifact=figures_registry.csv -->
FIGURES registry size: 203 entries (one row per entry in `figures_registry.csv`).
<!-- LIT1_EXEMPT_END -->

## 1. Executive Summary

This Phase 3 investigation establishes the empirical and structural causes of M5 results using validation-split counterfactuals (OP-V), frozen test artifacts (OP-F), and cross-split stability. No test decisions were re-evaluated, no production code modified.

### Key Conclusions:
1. **EV(close)=0 hardcoding is a defect, but NOT the root cause of the M5 test-set gap (H4 FALSE).**
   - P(close) > P(wait): **87 txns (6.06%)**. Corrected EV changed **0 decisions** and **Rs.0.00 net delta**.
   - Mechanism: on those 87 rows the corrected EV(close) does overtake wait, but at least one allowed active action still held strictly higher EV than the corrected close, so the argmax never moved. Derivation in the A1 section below.
2. **M2 carries real cross-action ranking signal. [Class R REFERENCE — Phase 2 draft 2]**
   - Pairwise concordance: **0.6223** (95% CI [0.6071, 0.6376], z=15.68, p<1e-15). [Class R REFERENCE]
   - Value-weighted concordance: **0.6468**. [Class R REFERENCE]
   - Oracle agreement: **23.1% (Policy A)** vs 12.1% (B0) overall. [Class R REFERENCE]
   - Oracle agreement, top amount decile: **44.4% (Policy A)** vs 8.3% (B0). [Class R REFERENCE]
3. **Shrinkage sweep (P3, OP-V): net value is monotone increasing with lambda.**
   - Gain from lambda=0.0 to lambda=1.0: **+Rs.156,669.07 (+14.5%)**.
   - Floor check: at lambda=0.0 the shrunk policy nets **Rs.1,078,896.67**, above the B0 waterfall validation net of **Rs.989,434.95**, so even the fully shrunk policy stays above the B0 baseline on validation.
4. **The wait->close test gap reflects heavy-tailed sampling variance (OP-F).**
   - 204 divergent txns. Top-3 close-only outliers = **Rs.329,675.72** = **133.3% of the Rs.247,409.56 wait->close subset gap** and **166.5% of the Rs.198,016.92 total test deficit**.
5. **Cross-split stability: Policy A net/txn stable (-4.3%); B0 volatile (+37.8%).**

---

## 2. A0 — Feature Construction and Ordering Census (OP-V) [GATE]

- **Feature Count:** 12 columns (6 categorical + 6 numeric/log-transformed).
- **Feature Names (as constructed, in order):** `failure_type`, `action`, `segment`, `payment_method`, `failure_action`, `segment_action`, `risk_score`, `attempt_number`, `contact_fatigue_score`, `log1p_amount`, `log1p_lifetime_successful_txns`, `log1p_lifetime_failed_txns`.
- **Metadata Cross-Check:** the persisted model metadata records a feature count of 12 and a model class of `LogisticRegression`, both matching the constructed matrix. No arity or ordering mismatch was found between metadata and the live feature build.
- **Validation Amount Range:** Rs.97.03 to Rs.279,558.65 across 1,435 transactions.
- **Distinct Full Orderings:** **13** across 1,435 validation transactions.
- **Top 5 Orderings:**
  1. discount>retry>payment_link>reminder>wait>close: 554 txns (38.6%)
  2. retry>discount>payment_link>reminder>wait>close: 153 txns (10.7%)
  3. retry>payment_link>discount>reminder>wait>close: 126 txns (8.8%)
  4. payment_link>retry>discount>reminder>wait>close: 117 txns (8.2%)
  5. payment_link>discount>retry>reminder>wait>close: 116 txns (8.1%)

### Key Action-Pair Orderings:
- `close vs wait`: wait>close in **1,348 (93.9%)**, close>wait in **87 (6.1%)** (Ties: 0). Min diff=0.0004, Med=0.0356, Max=0.1441.
- `retry vs discount`: discount>retry in **885 (61.7%)**, retry>discount in **550 (38.3%)**.
- `payment_link vs reminder`: pl>rem in **1,365 (95.1%)**, rem>pl in **70 (4.9%)**.

### Policy-Allowed vs M4-Selected Action Counts (Validation, OP-V)
| Action | Allowed | Selected by M4 |
| --- | --- | --- |
| `retry` | 567 | 260 |
| `payment_link` | 1,261 | 411 |
| `reminder` | 1,261 | 35 |
| `discount` | 918 | 555 |
| `wait` | 1,435 | 174 |
| `close` | 1,435 | 0 |

`close` is allowed on every validation transaction and selected on none of them. That is the structural fact sitting behind the H4 finding: an EV defect on `close` cannot move a decision that `close` never wins.

**A0 VERDICT: INTERACTIONS PRESENT**

---

## 3. A1 — Recomputed P(close) > P(wait) (OP-V)

| Ordering | Count | Fraction |
| --- | --- | --- |
| P(close) > P(wait) | **87** | 6.06% |
| P(wait) > P(close) | **1348** | 93.94% |
| P(close) == P(wait) | **0** | 0.00% |

- Corrected EV(close) simulation: **0 decision flips**, net delta = **Rs.0.00**.
- **H4 VERDICT: CLOSED AS FALSE.**

**Mechanism — why a real ordering defect moved nothing.** The defect is real: on 87 of 1,435 validation transactions the recomputed P(close) is above P(wait), and with EV(close) pinned at zero the engine could never rank `close` on merit. But correcting it still changed no decision, and the reason is the argmax, not the pairwise comparison. On each of those 87 rows the corrected EV(close) does overtake `wait` — yet `wait` was not the winning action there either. At least one allowed active action (`retry`, `payment_link`, `reminder`, or `discount`) held strictly higher EV than the corrected `close`, so the top of the ranking did not change and the selected action stayed the same. This is the same fact the A0 census reports from the other side: `close` is allowed on all 1,435 validation transactions and selected on 0 of them. The defect is therefore a structural-correctness issue with zero measured value impact on this split, which is exactly what **0 flips** and **Rs.0.00** record.

---

## 4. A2 — Accounting Convention (C1) and Policy Rows

Convention C1 confirmed via AST inspection of `ml/experiment/experiment_metrics.py`: gross is POST-haircut (recovered = amount - discount), net = gross - cost. Discount column is reporting-only.

| Split | Data Op | Policy | Txns | Recovered | Rate (%) | Gross (Rs.) | Cost (Rs.) | Discount [rpt] (Rs.) | Net (Rs.) | Net/Txn (Rs.) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Validation | OP-V | Policy A | 1,435 | 326 | 22.72% | Rs.1,238,245.74 | Rs.2,680.00 | Rs.38,468.39 | **Rs.1,235,565.74** | **Rs.861.02** |
| Validation | OP-V | B0 Waterfall | 1,435 | 272 | 18.95% | Rs.992,650.95 | Rs.3,216.00 | Rs.0.00 | **Rs.989,434.95** | **Rs.689.50** |
| Test | OP-F | Policy A | 1,577 | 361 | 22.89% | Rs.1,302,749.45 | Rs.2,797.00 | Rs.40,673.29 | **Rs.1,299,952.45** | **Rs.824.32** |
| Test | OP-F | B0 Waterfall | 1,577 | 312 | 19.78% | Rs.1,501,443.37 | Rs.3,474.00 | Rs.0.00 | **Rs.1,497,969.37** | **Rs.949.89** |
| Test | OP-F | B1 Random | 1,577 | 266 | 16.87% | Rs.1,363,512.35 | Rs.2,427.00 | Rs.11,300.31 | **Rs.1,361,085.35** | **Rs.863.09** |
| Test | OP-F | B6 Oracle | 1,577 | 818 | 51.87% | Rs.3,360,246.12 | Rs.1,235.00 | Rs.37,399.62 | **Rs.3,359,011.12** | **Rs.2130.00** |

---

## 5. A3 — P3 Shrinkage Sweep (OP-V)

Pbar denominators (allowed-only): retry=0.3329 (N=567), payment_link=0.2173 (N=1,261), reminder=0.1794 (N=1,261), discount=0.2197 (N=918), wait=0.1381 (N=1,435), close=0.1029 (N=1,435).

| Lambda | Net (Rs.) | Prior (Rs.) | Delta (Rs.) | Count | Rate (%) |
| --- | --- | --- | --- | --- | --- |
| 0.00 | Rs.1,078,896.67 | Rs.1,058,557.21 | +20,339.46 | 288 | 20.07 |
| 0.25 | Rs.1,090,067.85 | Rs.1,139,204.48 | -49,136.63 | 290 | 20.21 |
| 0.50 | Rs.1,103,310.75 | Rs.1,182,206.78 | -78,896.03 | 294 | 20.49 |
| 0.75 | Rs.1,196,671.25 | Rs.1,183,920.74 | +12,750.51 | 319 | 22.23 |
| 1.00 | Rs.1,235,565.74 | Rs.1,235,565.73 | +0.00 | 326 | 22.72 |

Net monotonically increases from lambda=0.0 to lambda=1.0: +Rs.156,669.07 (+14.5%).

At the lambda=0.0 floor the shrunk policy still nets Rs.1,078,896.67, which is above the B0 waterfall validation net of Rs.989,434.95. The sweep therefore never drops below the B0 baseline on validation; shrinkage moves the policy along a range whose lower end is already above B0.

### Per-Lambda Action Distribution (Validation, OP-V)
| Lambda | Selected-Action Counts |
| --- | --- |
<!-- LIT1_EXEMPT_START: artifact=a3_lambda_sweep.csv -->
| 0.00 | payment_link 691, retry 567, wait 174, discount 3 |
| 0.25 | payment_link 573, retry 567, wait 174, discount 121 |
| 0.50 | retry 567, payment_link 429, discount 265, wait 174 |
| 0.75 | discount 480, retry 385, payment_link 380, wait 174, reminder 16 |
| 1.00 | discount 555, payment_link 411, retry 260, wait 174, reminder 35 |
<!-- LIT1_EXEMPT_END -->

The mix rotates from `payment_link`-dominant at lambda=0.0 to `discount`-dominant at lambda=1.0. Across every lambda, `wait` holds a constant 174 selections and `close` is selected 0 times, so the sweep never redistributes value into or out of the passive actions. The lambda=1.0 row reproduces the live M4 baseline distribution, which is the condition assertion P3-1 checks.

---

## 6. A4 — Partition of 204 Test Transactions (OP-F)

| Category | Count | Total Amount (Rs.) |
| --- | --- | --- |
| CLOSE_ONLY | **7** | **Rs.529,259.10** |
| WAIT_ONLY | **5** | **Rs.281,849.54** |
| BOTH | **1** | **Rs.67,119.95** |
| NEITHER | **191** | **Rs.6,044,992.33** |
| Total B0 close recoveries | **8 (3.9%)** | **Rs.596,379.05** |
| Total PA wait recoveries | **6 (2.9%)** | **Rs.348,969.49** |
| **Net difference (PA wait minus B0 close)** | **-2** | **-Rs.247,409.56** |

The net-difference row is the derived quantity the partition exists to account for: PA recovers Rs.348,969.49 on this subset against B0's Rs.596,379.05, a shortfall of Rs.247,409.56 on a count difference of only 2 transactions. That contrast — a two-transaction count gap carrying a Rs.247,409.56 value gap — is the heavy-tail signature the next paragraph quantifies.

Top-3 close-only txns: Txn 1998 (Rs.139,904.76), Txn 7703 (Rs.114,085.35), Txn 196 (Rs.75,685.61).
Failure types of those three outliers: Txn 1998 is `network_timeout`; Txn 7703 and Txn 196 are both `temporary_bank_decline`. The single BOTH transaction is Txn 4518 (Rs.67,119.95, `temporary_bank_decline`), recovered under `wait` and under `close` alike, so it contributes no delta.
Sum = **Rs.329,675.72**, which is **133.3%** of the Rs.247,409.56 wait->close subset gap and **166.5%** of the Rs.198,016.92 total test deficit. Both shares exceed 100% because the top-3 outliers are larger than the net gap they sit inside; the two denominators answer different questions and are verified separately (XREF-1 X4a and X4b).

---

## 7. A5 — Full Substitution Attribution (OP-F)

Total gap (derived): **Rs.198,016.92** (1,280 divergent txns, 6 cells).

| PA Action | B0 Action | Count | PA Net (Rs.) | B0 Net (Rs.) | Delta (Rs.) | % |
| --- | --- | --- | --- | --- | --- | --- |
<!-- LIT1_EXEMPT_START: artifact=a5_substitution_matrix.csv -->
| `wait` | `close` | 204 | Rs.  348,969.49 | Rs.  596,379.05 | **Rs. -247,409.56** | -124.9% |
| `reminder` | `retry` | 22 | Rs.   29,908.41 | Rs.  120,238.67 | **Rs.  -90,330.26** | -45.6% |
| `payment_link` | `retry` | 60 | Rs.   26,475.06 | Rs.   36,908.65 | **Rs.  -10,433.59** | -5.3% |
| `payment_link` | `reminder` | 366 | Rs.  150,862.97 | Rs.  121,589.10 | **Rs.  +29,273.87** | 14.8% |
| `discount` | `reminder` | 355 | Rs.  136,931.73 | Rs.   87,887.01 | **Rs.  +49,044.72** | 24.8% |
| `discount` | `retry` | 273 | Rs.  229,127.90 | Rs.  157,290.01 | **Rs.  +71,837.89** | 36.3% |
<!-- LIT1_EXEMPT_END -->

<!-- LIT1_EXEMPT_START: artifact=a5_substitution_matrix.csv -->
ATTR-1: residual = **Rs.0.0000** (PASS). Matrix is exhaustive.
<!-- LIT1_EXEMPT_END -->

### Relationship to the Phase 2 Attribution

The Phase 2 draft of this section carried a large **UNEXPLAINED RESIDUAL** line alongside the substitution matrix. That line is not carried forward, and it is important to be precise about why. It was not deleted because it was inconvenient, and it is not still unattributed: Phase 3 computes the same quantity directly by grouping `per_transaction_decisions.csv` on the divergent (PA action, B0 action) pairs, and it resolves entirely into the measured active-for-active substitution lines already shown in the matrix above — the `payment_link`->`reminder`, `discount`->`reminder`, `discount`->`retry`, `reminder`->`retry` and `payment_link`->`retry` cells. In other words, what Phase 2 recorded as a residual is, on direct computation, the D4 substitution traffic between active actions.

Reconciliation against the Phase 2 hand-typed values (Test split, OP-F):

<!-- LIT1_EXEMPT_START: artifact=class_r_reconciliation.csv -->
| Phase 2 Item (Class R, hand-typed) | Phase 2 Value | Phase 3 Computed | Signed Difference |
| --- | --- | --- | --- |
| A5 UNEXPLAINED RESIDUAL | -100,764.00 | 49,392.64 — sum of the active-for-active cells | 150,156.64 |
| A5 active-gains component | 150,157.08 | 150,156.49 — sum of cells with delta > 0 | -0.59 |
<!-- LIT1_EXEMPT_END -->

Both rows are recorded item-by-item in `ml/evaluation/phase2_artifacts/class_r_reconciliation.csv`. The first row is a relabelling rather than a new measurement: Phase 2 classified active-for-active substitutions as unattributed, and Phase 3 attributes them by direct computation. The second row is agreement to well under a rupee, which is a rounding difference in the Phase 2 hand transcription. Because ATTR-1 above closes the matrix to a zero residual, the Phase 3 decomposition has no unattributed component left at all and the six cells are exhaustive by construction. The prior UNEXPLAINED figure is retained here only as a labelled historical comparison; it must NOT be cited as a currently open residual.

---

## 8. A6 — Calibration (OP-V)

| Action | N | Mean Pred | Realized | Gap | SE | 95% CI | Excl. 0 |
| --- | --- | --- | --- | --- | --- | --- | --- |
<!-- LIT1_EXEMPT_START: artifact=a6_calibration_actions.csv -->
| `retry` | 567 | 0.3329 | 0.3404 | -0.0075 | 0.0199 | [-0.0465, +0.0315] | NO |
| `payment_link` | 1,261 | 0.2173 | 0.2133 | +0.0040 | 0.0115 | [-0.0186, +0.0266] | NO |
| `reminder` | 1,261 | 0.1794 | 0.1594 | +0.0200 | 0.0103 | [-0.0002, +0.0402] | NO |
| `discount` | 918 | 0.2197 | 0.2211 | -0.0014 | 0.0137 | [-0.0283, +0.0254] | NO |
| `wait` | 1,435 | 0.1381 | 0.1352 | +0.0029 | 0.0090 | [-0.0148, +0.0206] | NO |
| `close` | 1,435 | 0.1029 | 0.1101 | -0.0073 | 0.0083 | [-0.0234, +0.0089] | NO |
<!-- LIT1_EXEMPT_END -->

**Gap orientation.** In both calibration tables the `Gap` column is **mean predicted minus realized**. A positive value means the predicted rate sits above the realized rate; a negative value means it sits below. This orientation differs from the preserved pre-Phase-3 snapshot, which is dealt with in the convention subsection at the end of this section. No row above has a 95% CI excluding zero.

### Reminder Calibration by Validation-Row Decile (N=1,261, OP-V)

These bins are index-based deciles of the validation rows, NOT amount deciles. Read the binning note below the table before reading the amount column.

| Decile | Observed Amount Range Within Bin (Rs.) | N | Mean Pred | Realized | Gap | SE | 95% CI | Excl. 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
<!-- LIT1_EXEMPT_START: artifact=a6_calibration_deciles.csv -->
| 0 | Rs.150–Rs.39,318 | 127 | 0.1795 | 0.1811 | -0.0016 | 0.0342 | [-0.0686, +0.0653] | NO |
| 1 | Rs.256–Rs.43,974 | 126 | 0.1983 | 0.1984 | -0.0002 | 0.0355 | [-0.0698, +0.0695] | NO |
| 2 | Rs.245–Rs.44,839 | 126 | 0.1701 | 0.1667 | +0.0034 | 0.0332 | [-0.0616, +0.0685] | NO |
| 3 | Rs.97–Rs.49,547 | 126 | 0.1814 | 0.2063 | -0.0250 | 0.0361 | [-0.0957, +0.0457] | NO |
| 4 | Rs.262–Rs.48,431 | 126 | 0.1585 | 0.1111 | +0.0474 | 0.0280 | [-0.0074, +0.1023] | NO |
| 5 | Rs.288–Rs.47,787 | 126 | 0.1940 | 0.1905 | +0.0036 | 0.0350 | [-0.0650, +0.0721] | NO |
| 6 | Rs.256–Rs.38,129 | 126 | 0.1752 | 0.1270 | +0.0483 | 0.0297 | [-0.0099, +0.1064] | NO |
| 7 | Rs.249–Rs.45,399 | 126 | 0.1919 | 0.1587 | +0.0332 | 0.0326 | [-0.0306, +0.0970] | NO |
| 8 | Rs.251–Rs.40,246 | 126 | 0.1591 | 0.1032 | +0.0559 | 0.0271 | [+0.0028, +0.1090] | **YES** |
| 9 | Rs.353–Rs.46,581 | 126 | 0.1860 | 0.1508 | +0.0352 | 0.0319 | [-0.0273, +0.0976] | NO |
<!-- LIT1_EXEMPT_END -->

*1 out of 10 validation-row deciles has a 95% CI excluding zero (decile 8)*.

**Binning methodology — read this before interpreting the table above.** The authoritative A6 decile computation bins on the validation row index:

```text
pd.qcut(reminder_sub.index, q=n_deciles, labels=False, duplicates="drop")
```

Each bin is therefore a contiguous block of validation rows, not a band of transaction amounts. Three consequences follow, and all three constrain how the table may be read:

- The **Observed Amount Range Within Bin** column reports the smallest and largest amount actually observed inside each bin. It is a descriptive statistic about the rows that happened to land in that bin. It is NOT a bin boundary, and it was not used to form the bin.
- The observed ranges **overlap heavily across bins**. That overlap is expected by construction under index binning; it is not a defect in the table or in the data.
- The bins are **NOT a monotone amount ordering**. Decile 9 is not a high-amount stratum and decile 0 is not a low-amount stratum. No row of this table may be read as evidence about model behaviour at high or low transaction amounts.

**How to read the count of 1 out of 10.** The count is retained exactly as computed and is NOT revised by this note: 1 out of 10. What this note corrects is the reading of it. Because the bins are index-based blocks of validation rows rather than amount strata, the flagged bin carries no information about transaction size, and its observed amount range overlaps the other nine bins. The Phase 2 caution therefore stands and is restored here: one flagged bin out of ten, at the 95% level, is within the range one would expect from multiple comparisons alone, and this report does not treat it as established evidence of miscalibration — at any amount band or overall. The CI, the SE and the underlying data behind that bin are unchanged by this note; only the interpretation is constrained.

### A6 Sign and SE Convention — Difference From the Preserved Snapshot (OP-V)

This subsection exists because the difference is real and is deliberately NOT normalized away.

**Sign orientation.** The authoritative artifact publishes the action-level gap as **mean predicted minus realized**. The preserved pre-Phase-3 snapshot published the same quantity with the opposite orientation, **realized minus mean predicted**. Every magnitude agrees between the two; every sign is inverted. This is a difference in how the column is oriented for display, not a difference in the measured data. Phase 3 keeps its own orientation and does NOT flip the signs to match the snapshot.

**Standard error.** The SE in the tables above is the single-proportion standard error on the realized rate, `sqrt(realized * (1 - realized) / n)`. Phase 3 tested a pre-registered alternative hypothesis that the snapshot had used a different SE formula. The acceptance rule was declared before the probe ran: a candidate formula had to reproduce all six of the snapshot SEs, agreeing to four decimal places, to be accepted as the historical formula. The verdict column below reads on that reconstruction question alone. REJECTED means the candidate does not reproduce the snapshot values; it does NOT mean the authoritative implementation is wrong. The formula in use is unchanged, and one of the rejected candidates is that same formula — rejected as a reconstruction of the snapshot, not as the published method.

Candidate SE formulas tested against the preserved snapshot (Validation, OP-V):

<!-- LIT1_EXEMPT_START: artifact=a6_se_convention_probe.csv -->
| Candidate SE Formula | Snapshot Actions Reproduced (of 6) | Verdict |
| --- | --- | --- |
| Poisson-binomial over per-row predicted probabilities | 1 of 6 (`wait` only) | REJECTED |
| Single proportion on the realized rate | 0 of 6 | REJECTED |
| Single proportion on the mean predicted rate | 0 of 6 | REJECTED |
<!-- LIT1_EXEMPT_END -->

No candidate met the pre-registered bar. The historical Phase 2 SE formula therefore remains unidentified, and nothing in the available evidence justifies a convention change. Phase 3 intentionally preserves the existing implementation and its orientation rather than retrofitting published values to match the snapshot: the signs were NOT flipped, the SE formula was NOT changed, the published A6 values were NOT edited, and the frozen A6 artifact was NOT modified. The per-action probe output — both gap orientations, all four candidate SEs, and the snapshot values side by side — is retained on disk at `ml/evaluation/phase2_artifacts/a6_se_convention_probe.csv`.

---

## 9. Cross-Split Stability

| Metric | Validation (OP-V) | Test (OP-F) | Cross-Split Shift |
| --- | --- | --- | --- |
| PA net/txn (Rs.) | **Rs.861.02** | **Rs.824.32** | **-4.3% (STABLE)** |
| B0 net/txn (Rs.) | **Rs.689.50** | **Rs.949.89** | **+37.8% (VOLATILE)** |
| PA minus B0 (Rs.) | +Rs.246,130.79 | -Rs.198,016.92 (95% CI [-Rs.776,313.86, +Rs.332,562.45], SPANS ZERO) | Rs.444,147.71 swing |
| Oracle net/txn (Rs.) | Rs.1937.51 | Rs.2130.00 | — |
| Max txn amount (Rs.) | Rs.279,558.65 | Rs.244,011.30 | — |
| Top-1% value share | 19.5% | 18.6% | — |

Gap swing Rs.444,147.71 is within bootstrap 95% CI width Rs.1,108,876.31 ([-Rs.776,313.86, +Rs.332,562.45]).

**Oracle net/txn reconciliation.** Both oracle figures in the table above are produced by the current authoritative A8 calculation: the validation figure Rs.1937.51 is the oracle validation net divided by the validation N, and the test figure Rs.2130.00 is `a2_b6_test_net` divided by `a2_pa_test_n`. The validation figure differs from the value carried in the preserved pre-Phase-3 snapshot. Two separate reconciliations are involved here and they must not be conflated:

- **Test side — permitted literal correction.** The snapshot's test oracle per-transaction value was a literal typed into `a8_carry_forward.json` during Phase 2, and no artifact reproduces it. It was corrected to Rs.2130.00 under the explicitly permitted test-oracle literal correction, and that correction is recorded as its own row in `class_r_reconciliation.csv`.
- **Validation side — derived, not corrected.** The validation oracle figure is NOT a literal correction and must not be described as one. It is the output of the current authoritative A8 calculation. The Phase 3 artifact establishes what the derived value is; it does NOT establish why the historical snapshot value differed. No reason for that difference is asserted here, and none should be inferred from the mere fact that a difference exists. Settling it would require re-deriving the Phase 2 oracle path, which Phase 3 did not do.

The comparison is retained rather than removed, so that the difference stays visible for a later reconciliation. Nothing in the cross-split table was adjusted toward the snapshot.

**Statistical status of the test-set gap.** The frozen test result is -Rs.198,016.92 with a bootstrap 95% CI of [-Rs.776,313.86, +Rs.332,562.45]. That interval contains zero, so the test-set gap is NOT statistically distinguishable from zero and this report does not claim Policy A was proven to lose value on the test set. The interval is also wider than the Rs.444,147.71 cross-split swing, which is why the swing — not the point estimate — is the finding. The point estimate is preserved verbatim and is not restated as significant anywhere in this document.

---

## 10. Class R Reconciliation and Historical Comparison

### Class R Reference vs Phase 3 Computed

Class R figures are prior, unverified reference values. They are never assertion targets. Where Phase 3 recomputed the same quantity, prior and computed are set side by side below. Where Phase 3 did not recompute it, the figure stays labelled Class R and is not treated as established.

Prior-vs-computed comparison, retained from `class_r_comparisons.csv` (Validation OP-V and Test OP-F):

<!-- LIT1_EXEMPT_START: artifact=class_r_comparisons.csv -->
| Item | Class R Prior | Phase 3 Computed | Status |
| --- | --- | --- | --- |
| P(close) > P(wait) on validation | 87 (draft 1) / 0 (draft 2) | 87 | AGREE (with draft 1) |
| Policy A validation recovered count | 326 (draft 1) / 329 (draft 2) | 326 | AGREE (with draft 1) |
| B0 validation net | 989,434.95 | 989,434.95 | AGREE |
| P5 wait recoveries count on 204 | 31 (draft 1 data error) | 6 | DISAGREE (prior was data error) |
| P5 close recoveries count on 204 | 8 | 8 | AGREE |
| Top-3 close-only sum | 329,676.00 / 323,945.00 | 329,675.72 | AGREE (with draft 1 reference) |
| P2 concordance rate | 0.52 (draft 1 text) / 0.6223 (draft 2) | 0.6223 | AGREE (with draft 2) |
| M4 validation net baseline | 1,235,565.73 | 1,235,565.73 | AGREE |
<!-- LIT1_EXEMPT_END -->

The corrected P5 wait-recoveries count is **6**, not the draft-1 figure shown in the table above: that draft-1 figure was a data error in the prior run, and the Phase 3 partition in the A4 section derives 6 wait recoveries out of the 204 divergent test transactions. The full item-by-item record — including the four A3 Pbar denominator corrections, the two-denominator top-3 finding, the oracle reconciliation, the A5 residual relabelling, and the six concordance rows that Phase 3 did NOT recompute — exists on disk as `ml/evaluation/phase2_artifacts/class_r_reconciliation.csv`.

### Historical Snapshot Values Not Reproducible From Phase 3 Artifacts

The figures below appear in the preserved pre-Phase-3 report but are NOT reproducible from any Phase 3 artifact. They are therefore retained here only as labelled historical/snapshot references, and they are NOT restored into the authoritative body of this report. They must not be cited as Phase 3 results.

- **Per-policy recovery-rate confidence intervals.** The snapshot displayed a plus/minus interval on each policy row's recovery rate. `a2_policy_rows.csv` carries no CI columns and the FIGURES registry carries no corresponding keys, so those intervals cannot be sourced. They are omitted rather than retyped from the snapshot. [Class R REFERENCE — pre-Phase-3 snapshot]
- **Oracle validation net and per-transaction values as printed in the snapshot.** Superseded by the current authoritative A8 derivation shown in the cross-split table, with the reconciliation note in that section. [Class R REFERENCE — pre-Phase-3 snapshot]
- **Oracle-agreement ratio multipliers.** The snapshot expressed oracle agreement as a Policy A to B0 ratio. Those multipliers were derived by hand from the Class R agreement percentages and no artifact reproduces them, so only the underlying Class R percentages appear in this report, in the Executive Summary. [Class R REFERENCE — pre-Phase-3 snapshot]

One further artifact is recorded for completeness rather than restored: `a6_relative_bias.csv` is computed by the authoritative run and is counted by assertion CAL-1, but its rows are displayed in neither the snapshot nor this report. Its contents are deliberately not summarised here, because doing so inside a report-only repair would introduce a substantive claim that neither report has previously made. It is flagged as an open item for a later decision.

The preserved snapshot itself is intact and unmodified at `ml/evaluation/_pre_phase3_snapshot/m5_2_phase2_diagnostic.PRE_PHASE3.md`. Nothing in this report was changed in order to match it.

---

## 11. Assertion Results (OP-V + OP-F)

These results are the record of the authoritative run, produced against the report body that run generated. They are reproduced verbatim and are NOT recomputed here. The report-only repair added narrative subsections and tables after that run, so the table, token, and Class R counts below describe the run's own generated body rather than the current state of this file. The added material was checked by hand against the same LIT-1, CAL-2 and SPLIT-1 rules, but only a rerun of the authoritative script can refresh the counts, and rerunning is out of scope for a report-only repair.

| ID | Classification | Description | Status | Details |
| --- | --- | --- | --- | --- |
<!-- LIT1_EXEMPT_START: artifact=assertions.csv -->
| **ACC-1** | MECHANICAL | Net=Gross-Cost for every policy row | **PASS** | 6 rows checked. Failures: None |
| **ACC-2** | MECHANICAL | Every FIGURES value matches its artifact on disk | **PASS** | Checked 58 values. Mismatches: 0 |
| **ORD-1** | MECHANICAL | Distinct orderings per pair is 1 or 2 | **PASS** | 15 pairs. Full orderings=13. |
| **ORD-2** | MECHANICAL | A0 verdict is INTERACTIONS PRESENT | **PASS** | Verdict: INTERACTIONS PRESENT |
| **P3-1** | MECHANICAL | lambda=1.0 reproduces live M4 baseline within 0.01 and 100% agreement | **PASS** | Net diff: Rs.0.0000, Agreement: 100.00% |
| **P3-2** | MECHANICAL | lambda=0 simulated distribution matches independent derivation | **PASS** | 100% per-transaction action match |
| **P3-3** | INFORMATIONAL | Every lambda row delta explained by Pbar denominator | **PASS** | Allowed-only Pbar denominator shift documented in a3_pbar.csv |
| **P5-1..5** | MECHANICAL | Five partition balance assertions on wait->close test txns | **PASS** | All 5 identities hold within tolerance 1.00 |
| **SAME-1** | MECHANICAL | Same-action delta is zero | **PASS** | same_delta<0.01; prerequisite for ATTR-1 |
| **ATTR-1** | MECHANICAL | Matrix residual < 0.01 | **PASS** | Residual=Rs.0.0000 |
| **CAL-1** | MECHANICAL | Every calibration row has non-null SE and 95% CI | **PASS** | Checked 6 action + 10 decile + 5 bias rows |
| **XREF-1** | MECHANICAL | All cross-section identity checks pass (with negative control) | **PASS** | 9/9 checks passed; failed=none; negative control detected injected perturbation (X1=False) |
| **FROZ-1** | MECHANICAL | Every recomputed sidecar matches its frozen original except where pre-declared | **PASS** | 6/6 frozen artifact(s) diffed against their sidecars; 0 pre-declared field divergence(s); 0 undeclared; failures=none |
| **CAL-2** | MECHANICAL | No significance claim attaches to CI-spanning-zero calibration row | **PASS** | Violations: None |
| **SPLIT-1** | MECHANICAL | Every markdown table declares split/data-op | **PASS** | 9/9 labelled. Violations: None |
| **LIT-1** | MECHANICAL | New report has zero unsourced numeric tokens (detector proven to fire on the preserved original) | **PASS** | 0 unsourced; 7 Class R; fail-first gate on preserved original: PASS (3 required token(s) flagged unsourced); injection control fired; per-token classifications in lit1_pre_phase3_scan.csv |
<!-- LIT1_EXEMPT_END -->

---

## 12. Status Attestations

- **M1-M5 Code:** UNCHANGED
- **M1-M5 Frozen Results:** PRESERVED. No frozen M5 result was recomputed, overwritten, or restated. The frozen test outcome is carried forward verbatim, with its bootstrap interval attached at every display site.
- **ev_engine.py:** UNCHANGED
- **Tests:** UNCHANGED
- **Model Weights / Costs / Thresholds / Seeds / Splits / Baselines:** UNCHANGED
- **Test-Set Decisions:** NOT RE-EVALUATED
- **Production Fixes Implemented:** NONE. Every roadmap entry below is a recommendation only; no production fix was applied as part of this diagnostic.
- **M2 Retrained:** NO
- **Test Set Re-Decided:** NO
- **M6:** NOT RUN
- **Commits:** NONE
- **Report-Only Repair:** APPLIED to narrative wording, methodology notes, and restored explanatory sections only. No computation, artifact, or source file was touched, and the authoritative script was NOT rerun.

### Recommended Engineering Roadmap:
1. `close` EV=0 fix: structural correctness; zero value impact (Rs.0.00 delta from corrected simulation). Recommendation only — not implemented.
2. M4 Test 12: Rewrite to test a reachable path. Recommendation only — not implemented.
3. M5 Reporting: Reframe with cross-split variance finding.
4. Concordance Recomputation: Phase 4 candidate (current figures are Class R REFERENCE).
5. Reminder calibration follow-up: the validation-row decile table shows one bin out of ten with a CI excluding zero. That warrants re-examining the calibration slice under amount-stratified bins, and under a multiple-comparison correction, before any conclusion is drawn from it. It does NOT establish that retraining or recalibration is warranted, and no retraining is recommended on this evidence.
6. Future evaluation design: report both splits side by side, or state the power limitation explicitly. The single frozen test split carries a bootstrap interval wide enough to contain zero, so a one-split readout cannot settle the policy comparison in either direction. Reporting validation and test together, or stating the power limitation outright, is the minimum fix.
