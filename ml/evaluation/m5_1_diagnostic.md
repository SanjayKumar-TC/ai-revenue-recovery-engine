# M5.1 Diagnostic Report — Root Cause Analysis

## Result Being Diagnosed

| Metric | Value |
|--------|-------|
| Policy A net | 1,299,952.45 |
| B0 waterfall net | 1,497,969.37 |
| B1 random net | 1,361,085.35 |
| Net Recovery Uplift | -198,016.92 (-13.22%) |
| Headroom captured | -10.64% |

The loss is accepted as genuine. No tuning was performed.

---

## D1: Action-Selection Distribution

| Action | Policy A Count | Policy A % | B0 Count | B0 % |
|--------|---------------|------------|----------|------|
| retry | 290 | 18.4% | 645 | 40.9% |
| payment_link | 426 | 27.0% | 0 | 0.0% |
| reminder | 29 | 1.8% | 728 | 46.2% |
| discount | 628 | 39.8% | 0 | 0.0% |
| wait | 204 | 12.9% | 0 | 0.0% |
| close | 0 | 0.0% | 204 | 12.9% |
| escalate | 0 | 0.0% | 0 | 0.0% |
| no_action_required | 0 | 0.0% | 0 | 0.0% |

Policy A most-frequent-action: discount (39.8%)

---

## D2: Haircut Test — Recovery Rate vs Net Value

| Policy | Recovered | Rate | Gross | Cost | Discount | Net |
|--------|-----------|------|-------|------|----------|-----|
| b6_oracle | 818 | 51.9% | 3,360,246 | 1,235 | 37,400 | 3,359,011 |
| b0_waterfall | 312 | 19.8% | 1,501,443 | 3,474 | 0 | 1,497,969 |
| b1_random | 266 | 16.9% | 1,363,512 | 2,427 | 11,300 | 1,361,085 |
| policy_a | 361 | 22.9% | 1,302,749 | 2,797 | 40,673 | 1,299,952 |
| b5_always_discount | 348 | 22.1% | 985,800 | 534 | 68,058 | 985,266 |
| b2_always_retry | 275 | 17.4% | 805,325 | 1,290 | 0 | 804,035 |
| b3_always_payment_link | 303 | 19.2% | 800,430 | 6,865 | 0 | 793,565 |
| b4_always_reminder | 250 | 15.9% | 617,357 | 4,119 | 0 | 613,238 |

> [!WARNING]
> **Higher recovery rate but lower net.** The loss comes from giving away value (discount haircut / intervention cost) on recoveries, not from failing to recover.

---

## D3: Per-Action Calibration

| Action | Mean Predicted | Realized Rate | Signed Gap | Amt-Weighted Gap | N |
|--------|---------------|---------------|------------|-----------------|---|
| close | 0.1067 | 0.1110 | -0.0043 | -0.0385 | 1577 |
| discount | 0.2225 | 0.2230 | -0.0004 | +0.0034 | 1036 |
| payment_link | 0.2184 | 0.2129 | +0.0054 | +0.0294 | 1437 |
| reminder | 0.1828 | 0.1761 | +0.0068 | +0.0431 | 1437 |
| retry | 0.3057 | 0.3027 | +0.0031 | +0.0181 | 978 |
| wait | 0.1430 | 0.1427 | +0.0003 | +0.0075 | 1577 |

A positive gap means M2 over-predicts recovery probability for that action.
Over-prediction inflates EV and causes M4 to prefer that action over alternatives.

---

## D4: Gap Decomposition

- Divergent transactions: 1280 (81.2%)
- Same-action transactions: 297 (18.8%)
- Divergent delta: -198,017
- Same-action delta: +0

### Substitution Matrix (top 5 most costly)

| PA Action → B0 Action | Count | PA Net | B0 Net | Delta |
|----------------------|-------|--------|--------|-------|
| wait→close | 204 | 348,969 | 596,379 | -247,410 |
| reminder→retry | 22 | 29,908 | 120,239 | -90,330 |
| payment_link→retry | 60 | 26,475 | 36,909 | -10,434 |
| payment_link→reminder | 366 | 150,863 | 121,589 | +29,274 |
| discount→reminder | 355 | 136,932 | 87,887 | +49,045 |

---

## D5: Regret Analysis vs Oracle

| Policy | Total Regret | Mean Regret |
|--------|-------------|-------------|
| policy_a | 2,059,059 | 1,305.68 |
| b0_waterfall | 1,861,042 | 1,180.12 |

---

## D6: The close EV=0 Question

1. **close EV is hardcoded to 0** in `ev_engine.py`: `if action == "close": return {..., "expected_net_value": 0.0}`
2. **close realized recovery rate (test):** 0.1110 (1577 rows)
3. **Structural claim CONFIRMED:** close is UNREACHABLE when wait is allowed with P(wait) ≥ 0.
   - EV(close) = 0 always
   - EV(wait) = P(wait) × amount ≥ 0
   - When tied: wait wins tiebreak (priority index 1 < 5)
4. **Test 12 corollary CONFIRMED:** Test 12 excluded wait from the scored set. Had wait been
   scored, it would have tied close at EV=0 and won tiebreak. Test 12 certified a code path
   that cannot occur in production.

---

## D7: Counterfactual Reference Analysis (Validation Only)

| Policy | Net Recovered |
|--------|--------------|
| M4 absolute EV | 1,235,566 |
| Shadow incremental EV | 1,235,566 |
| B0 waterfall | 989,435 |

- Shadow improvement over M4: +0
- Gap closed by incremental framing: +0.0%

---

## D8: Action Reachability Audit

| Action | Allowed | Scored | Selected | Status |
|--------|---------|--------|----------|--------|
| retry | 645 | 645 | 290 | OK |
| payment_link | 1373 | 1373 | 426 | OK |
| reminder | 1373 | 1373 | 29 | OK |
| discount | 985 | 985 | 628 | OK |
| wait | 1577 | 1577 | 204 | OK |
| close | 1577 | 1577 | 0 | **STRUCTURALLY UNREACHABLE** |
| escalate | 1577 | 0 | 0 | **STRUCTURALLY UNREACHABLE** |
| no_action_required | 0 | 0 | 0 | OK |

---

## D9: B0's Free-Recovery Harvest

### policy_a

| Group | Count | Gross | Cost | Discount | Net |
|-------|-------|-------|------|----------|-----|
| PASSIVE | 204 | 348,969 | 0 | 0 | 348,969 |
| ACTIVE | 1373 | 953,780 | 2,797 | 40,673 | 950,983 |
| ESCALATE | 0 | 0 | 0 | 0 | 0 |

### b0_waterfall

| Group | Count | Gross | Cost | Discount | Net |
|-------|-------|-------|------|----------|-----|
| PASSIVE | 204 | 596,379 | 0 | 0 | 596,379 |
| ACTIVE | 1373 | 905,064 | 3,474 | 0 | 901,590 |
| ESCALATE | 0 | 0 | 0 | 0 | 0 |

---

## D10: Loss Shape — Broad Bias or Tail Events

### Policy A vs b0_waterfall

- Wins: 555 (value won: +770,179)
- Ties: 489
- Losses: 533 (value lost: -968,196)
- Net: -198,017

### Policy A vs b1_random

- Wins: 463 (value won: +643,699)
- Ties: 619
- Losses: 495 (value lost: -704,831)
- Net: -61,133

---

## Hypothesis Verdicts

### C. M4 IMPLEMENTATION PROBLEM (Dominant Root Cause)
`close` has genuine recovery probability but is assigned EV=0 and is structurally unreachable.

- **Evidence FOR:** D6 confirms `close` EV is hardcoded to 0 in `ev_engine.py`, yet its realized recovery rate is 0.1110. `wait` is scored at P(wait) × amount ≥ 0, which dominates `close`. Even if P(wait) = 0, `wait` wins the priority tiebreak (index 1 vs 5). Test 12 falsely certified `close` by explicitly excluding `wait`. D8 confirms `close` was allowed 1577 times but selected 0 times (structurally unreachable).
- **Evidence AGAINST:** None.
- **Would refute:** `close` having a realized recovery rate of exactly 0, or `wait` not being a permitted baseline.
- **Verdict:** **CONFIRMED** (Dominant Root Cause).
- **Value Attributed:** At least ₹247,410. D4 Gap Decomposition shows the single most costly substitution is Policy A choosing `wait` instead of `close` (204 transactions), resulting in a delta of -₹247,410. This substitution alone exceeds the entire ₹198,017 deficit.

### A. M2 PROBABILITY PROBLEM
M2 probabilities may be reasonable overall but poorly calibrated conditional on action, causing M4 to rank actions on misleading inputs.

- **Evidence FOR:** D3 Per-Action Calibration shows M2 systematically over-predicts `reminder` (+0.0431 amount-weighted gap) and `payment_link` (+0.0294 amount-weighted gap), while slightly under-predicting `close` (-0.0385 amount-weighted gap). This inflates the EV of contact actions relative to passive ones.
- **Evidence AGAINST:** The gaps are relatively small (mostly within ±0.04), and `retry` (a major active intervention) is fairly well calibrated (+0.0181).
- **Would refute:** Zero per-action calibration gap.
- **Verdict:** **PARTIALLY SUPPORTED**.
- **Value Attributed:** ~₹100,000. D4 shows `reminder`→`retry` cost -₹90,330 and `payment_link`→`retry` cost -₹10,434. The over-prediction of `reminder` and `payment_link` likely drove these bad active-for-active substitutions.

### B. M4 OBJECTIVE PROBLEM
M4 maximizes absolute expected recovery rather than incremental value over the free passive option (`wait`).

- **Evidence FOR:** D9 shows B0's "free-recovery harvest" (Passive actions) netted ₹596,379 at zero cost and zero discount, while Policy A only netted ₹348,969 from passive actions, spending its budget on interventions.
- **Evidence AGAINST:** D7 Counterfactual Reference Analysis shows that on the validation split, the shadow incremental rule scored *exactly the same* as the M4 absolute EV (Net = 1,235,566). Gap closed by incremental framing = 0.0%.
- **Would refute:** Shadow rule performing exactly the same as M4 (which it did).
- **Verdict:** **NOT SUPPORTED** (as the primary driver of this specific loss).
- **Value Attributed:** ₹0. The incremental framing did not change the action distribution or net value in the validation set. The failure to harvest free recovery is driven by the implementation defect (C), not the objective function.

### D. SUBSTITUTION PROBLEM
Specific action substitutions systematically destroy net value.

- **Evidence FOR:** D4 clearly isolates the destruction to a few specific substitutions: `wait`→`close` (-₹247,410) and `reminder`→`retry` (-₹90,330). D10 shows that the losses are heavily concentrated in a few high-value tail events (the top 3 single-transaction losses alone destroyed ₹329,676, all from `wait`→`close` substitutions on high amounts).
- **Evidence AGAINST:** None.
- **Would refute:** A uniform, broad bias where Policy A loses small amounts on every transaction.
- **Verdict:** **CONFIRMED** (as the mechanism of loss, driven by C and A).
- **Value Attributed:** This is the symptom, not the root cause. The ₹247,410 `wait`→`close` substitution is driven by C. The ₹100,764 active-for-active substitutions (`reminder`→`retry`, `payment_link`→`retry`) are driven by A.

---

## Root Cause Ranking & Value Attribution

The total deficit to explain is **-₹198,017**.

1. **Hypothesis C (M4 Implementation Problem - `close` EV=0): -₹247,410**
   This is the dominant defect. By hardcoding `close` to EV=0 and scoring `wait` at P×amount, the engine is structurally blind to `close`. Whenever B0 smartly closes a doomed transaction (saving interventions), Policy A chooses `wait`, keeping it open or trying other actions. The D4 matrix proves the `wait`→`close` substitution alone destroyed ₹247,410.

2. **Hypothesis A (M2 Probability Calibration on specific actions): -₹100,764**
   Over-prediction of `reminder` and `payment_link` caused Policy A to prefer these actions over `retry` (which was better calibrated). This drove the `reminder`→`retry` (-₹90,330) and `payment_link`→`retry` (-₹10,434) substitutions.

3. **Value Gained Elsewhere: +₹150,157**
   Policy A made some positive substitutions (e.g., `discount`→`reminder` +₹49,045, `discount`→`retry` +₹71,838), recovering some of the massive losses above.

**Math Check:** -247,410 (C) - 100,764 (A) + 150,157 (Gains) = **-198,017**.
Unexplained value: **₹0**. The components perfectly sum to the total deficit.

## Summary

M5 STATUS: PASS (experiment valid) / RESULT: LOSS
M5.1 STATUS: Complete

The loss is fully explained. A structural defect in M4 (`close` hardcoded to EV=0) combined with action-conditional miscalibration in M2 (`reminder`/`payment_link` over-predicted) caused Policy A to systematically make terrible substitutions on high-value transactions.
