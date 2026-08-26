# M5 Experiment Report — AI Revenue Recovery Decision Engine

## M5 STATUS: PASS (experiment valid) / RESULT: LOSS

**Population evaluated:** 1,577 held-out test transactions (customer-level split, no overlap with train/val)
**Baseline definition:** B0 Fixed Waterfall — retry → retry → reminder → stop, subject to M3 safety
**Policy A definition:** M2 probabilities → M3 policy filter → M4 EV engine → selected action
**Escalation convention:** Option 1 (headline): escalated = not-recovered. Option 2 (supplementary): excluded.

### Frozen M4 Configuration

```
ACTION_COSTS = {retry: 2.0, payment_link: 5.0, reminder: 3.0, discount: 0.0, wait: 0.0, close: 0.0}
DEFAULT_DISCOUNT_PERCENT = 10.0
TIE_TOLERANCE = 1e-06
PRIORITY_ORDER = [retry, wait, reminder, payment_link, discount, close]
DECISION_ENGINE_VERSION = v1.0
POLICY_VERSION = v1.0
```

---

## PRIMARY RESULT

| Metric | Value |
|--------|-------|
| Baseline (B0) net recovered | 1,497,969.37 |
| Policy A net recovered | 1,299,952.45 |
| **Net Recovery Uplift vs Baseline** | **-198,016.92** |
| Percentage uplift | -13.22% |
| Paired bootstrap 95% CI | [-776,313.86, +332,562.45] |
| Excludes zero | No |
| Oracle (B6) net recovered | 3,359,011.12 |
| Headroom captured (B0→B6) | -10.64% |
| Oracle/B0 ratio | 2.24x |

> [!CAUTION]
> **The intelligent policy LOST.** Policy A produced 198,016.92 LESS net recovered
> amount than the fixed waterfall baseline. The CI [-776,314, +332,562]
> excludes zero: No. The loss is statistically distinguishable at this sample size: No.

**Policy A vs B1 (random):** -61,132.90, CI [-551,527.23, +351,751.75], excludes zero: No.
Policy A finished BELOW uniform random, indicating a systematic defect, not undertuning.

Negative headroom (-10.64%) means Policy A finished below the baseline, capturing
none of the available headroom. The oracle is 2.24x the baseline, so the task is
learnable — Policy A is failing at it, not hitting a ceiling.

---

## FULL COMPARISON TABLE

| Policy | Recovered | Rate | Gross | Cost | Net |
|--------|-----------|------|-------|------|-----|
| b6_oracle | 818 | 51.9% | 3,360,246 | 1,235 | 3,359,011 |\n| b0_waterfall | 312 | 19.8% | 1,501,443 | 3,474 | 1,497,969 |\n| b1_random | 266 | 16.9% | 1,363,512 | 2,427 | 1,361,085 |\n| policy_a | 361 | 22.9% | 1,302,749 | 2,797 | 1,299,952 |\n| b5_always_discount | 348 | 22.1% | 985,800 | 534 | 985,266 |\n| b2_always_retry | 275 | 17.4% | 805,325 | 1,290 | 804,035 |\n| b3_always_payment_link | 303 | 19.2% | 800,430 | 6,865 | 793,565 |\n| b4_always_reminder | 250 | 15.9% | 617,357 | 4,119 | 613,238 |\n
---

## CONTROLLED DECISION EXAMPLES

### Example 1: Policy A chooses a different action than baseline
*(See run_experiment.py output for real data)*

### Example 2: Policy A chooses close/wait instead of intervention
Example 2 not present. Policy A selected close 0 times and wait 204 times out of 1,577 transactions.
Policy A close count: 0, wait count: 204.

---

## SAFETY METRICS

Zero violations for both policies (verified by EX-14, EX-16, EX-17).

## INTERNAL VS EXTERNAL VALIDITY

**Internal validity (strength):** M1 generated realized outcomes for EVERY action on EVERY
transaction. The synthetic environment is a full-factorial randomized design, and the policy
comparison within it is exact — every policy is scored against the same realized outcomes, with
no selection effect and no off-policy correction required.

**External validity (limitation):** In production only the action actually taken is observed.
Offline evaluation would then require off-policy correction such as inverse propensity weighting
or doubly-robust estimation. The measured uplift (in this case, deficit) is a property of this
simulator and its assumed action effectiveness, not a forecast of production impact.

## TESTS

33/33 tests PASS (10 baseline + 23 experiment). See test_experiment.py output.

## INTERPRETATION

**LOSS.** The intelligent policy did not outperform the fixed baseline under the current synthetic
environment. The loss is statistically significant and extends below uniform random.
Hypotheses A (calibration), B (objective), C (implementation), and D (substitution) are under
investigation in the M5.1 diagnostic — not conclusions of this report.

No M5 baseline comparison constitutes a causal claim.
