"""
M5.2 Phase 3 — Authoritative Execution Script
=================================================
Phase 3 report-integrity additions (all new tasks):
  Task 0:  FIGURES registry — every report number flows from an artifact
  Task 1:  XREF-1 — 7 real cross-section identity checks (with negative control)
  Task 2:  LIT-1 — literal token detector (negative control + zero-flag verification)
  Task 3:  run_a5 rebuilt from full substitution matrix (no typed literals)
  Task 4:  Convention determined by AST inspection (not pre-declared)
  Task 5:  ACC-2 converted to real disk-vs-FIGURES check
  Task 6:  CAL-2 converted to real significance-claim scan
  Task 7:  SPLIT-1 converted to real table-label scan
  Task 8:  Class R reconciliation table
  Task 9:  Report regenerated from FIGURES (render() everywhere)
  Task 10: Honest assertion classification (MECHANICAL / INFORMATIONAL)
  Task 11: SHA-256 manifest comparison (frozen artifacts must be byte-identical)
  Task 12: M4 defect remains open
  Task 13: No git

FROZEN ARTIFACTS (must be byte-identical between Phase 2 and Phase 3 runs):
  a0_feature_audit.json, a0_pair_orderings.csv,
  a1_close_wait.json,
  a2_policy_rows.csv,
  a3_harness_baseline.json, a3_lambda_sweep.csv, a3_pbar.csv,
  a4_partition_rows.csv, a4_partition_summary.json, a4_population.json,
  a6_calibration_actions.csv, a6_calibration_deciles.csv, a6_relative_bias.csv

FIELD-GOVERNED (not byte-frozen, but only whitelisted fields may change):
  a8_carry_forward.json — run_a8 must rewrite it to replace the Phase 2 typed oracle
  per-transaction literal (2129.37) with the derived value (oracle_net_test / test_N =
  2130.00). Only the paths in A8_FIELD_RULE may change; any other altered or removed
  field is FATAL. Added fields are permitted and reported.

PRE-REGISTERED CHANGE SET (EXPECTED_CHANGES — declared before the run):
  a2_convention.json (AST derivation fields added),
  a5_attribution.csv (rebuilt from full matrix),
  a5_substitution_matrix.csv (new),
  figures_registry.csv (new),
  class_r_reconciliation.csv (new),
  lit1_pre_phase3_scan.csv (new — persisted LIT-1 fail-first evidence),
  assertions.csv, run_log.txt, a8_carry_forward.json
  Anything that changes outside FROZEN_ARTIFACTS and EXPECTED_CHANGES is FATAL.

REPORT AND SNAPSHOT:
  ml/evaluation/m5_2_phase2_diagnostic.md is regenerated. Its pre-Phase-3 state is
  preserved once, immutably, at ml/evaluation/_pre_phase3_snapshot/. The snapshot is
  never overwritten on a later run and is never included in any manifest comparison.

RESIDUAL RISK (stated because it cannot be eliminated):
  No textual baseline of the Phase 2 runner exists — it was overwritten before Phase 3
  and was never committed to git. Frozen-artifact equality therefore proves identical
  behaviour ON THIS DATA ONLY; it does not prove identical logic, because a modified
  branch that this dataset never exercises would leave every hash unchanged.

EXIT CODES: 0 only on full success. Any gate failure, MECHANICAL assertion failure,
  frozen-artifact change, undeclared artifact change, or unpermitted A8 field change
  exits 1. Every exit path passes through finalize(), which always reports the SHA-256
  comparison, so an aborted run still says exactly what it wrote. An UNANTICIPATED
  crash is caught by _entry(), which prints the exact traceback and then routes through
  finalize() as well, so no failure mode can exit 0 or exit silently.
"""

import ast as _ast
import hashlib
import json
import os
import re
import sys
import traceback
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ml.decision.decision_config import (
    ACTION_COSTS, DEFAULT_DISCOUNT_PERCENT, ACTION_PRIORITY_ORDER, EV_TIE_TOLERANCE,
    DECISION_ENGINE_VERSION
)
from ml.decision.decision_engine import load_model, predict_probability, select_best_action, make_decision
from ml.decision.ev_engine import calculate_ev
from ml.policy.policy_engine import evaluate_policy
from ml.policy.policy_config import POLICY_VERSION
from ml.experiment.baseline_policy import select_b0_waterfall, select_b1_random, select_b6_oracle
from ml.experiment.experiment_metrics import score_action

ARTIFACTS_DIR = os.path.join("ml", "evaluation", "phase2_artifacts")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

PER_TXN_PATH = os.path.join("ml", "experiment", "results", "per_transaction_decisions.csv")
EXPERIMENT_METRICS_PATH = os.path.join("ml", "experiment", "experiment_metrics.py")

# Report and immutable pre-Phase-3 snapshot
REPORT_PATH     = os.path.join("ml", "evaluation", "m5_2_phase2_diagnostic.md")
SNAPSHOT_DIR    = os.path.join("ml", "evaluation", "_pre_phase3_snapshot")
SNAPSHOT_REPORT = os.path.join(SNAPSHOT_DIR, "m5_2_phase2_diagnostic.PRE_PHASE3.md")

# Frozen artifact list (filenames only, relative to ARTIFACTS_DIR).
# Any byte-level change to one of these is FATAL.
# NOTE: a8_carry_forward.json is deliberately NOT frozen — run_a8 must rewrite it to
# replace the Phase 2 typed oracle-per-transaction literal (2129.37) with the derived
# value (oracle_net_test / test_N). It is governed instead by A8_FIELD_RULE below, which
# permits ONLY that correction and treats every other field change as FATAL.
FROZEN_ARTIFACTS = [
    "a0_feature_audit.json", "a0_pair_orderings.csv",
    "a1_close_wait.json",
    "a2_policy_rows.csv",
    "a3_harness_baseline.json", "a3_lambda_sweep.csv", "a3_pbar.csv",
    "a4_partition_rows.csv", "a4_partition_summary.json", "a4_population.json",
    "a6_calibration_actions.csv", "a6_calibration_deciles.csv", "a6_relative_bias.csv",
]

# Pre-registered change set. Declared BEFORE the run so post-hoc justification is
# impossible. Any artifact that changes and is in neither FROZEN_ARTIFACTS nor this
# set is FATAL, even though it is not frozen.
EXPECTED_CHANGES = {
    "a2_convention.json",             # AST derivation fields added
    "a5_attribution.csv",             # rebuilt from full substitution matrix
    "a5_substitution_matrix.csv",     # new
    "figures_registry.csv",           # new
    "class_r_reconciliation.csv",     # new
    "assertions.csv",                 # XREF-1/LIT-1/CAL-2/SPLIT-1 rows added
    "run_log.txt",                    # rewritten every run
    "a8_carry_forward.json",          # oracle-per-txn typed-literal correction ONLY
    "lit1_pre_phase3_scan.csv",       # new: fail-first evidence, persisted
    # Phase 3 recomputation sidecars. These exist because a frozen artifact is now
    # READ-ONLY to this script (see frozen_guard_path): the recomputation still runs,
    # but it lands here instead of overwriting the Phase 2 original, and FROZ-1
    # diffs sidecar-vs-original field by field. Declared before the run.
    "a0_feature_audit.PHASE3.json",
    "a1_close_wait.PHASE3.json",
    "a4_partition_summary.PHASE3.json",
    "a6_calibration_actions.PHASE3.csv",
    "a6_calibration_deciles.PHASE3.csv",
    "a6_relative_bias.PHASE3.csv",
    "froz1_divergences.csv",          # new: field-level sidecar-vs-frozen diff, persisted
    "a6_se_convention_probe.csv",     # new: measurement only, changes no published value
}

# ==============================================================================
# FROZ-1 — PRE-DECLARED SIDECAR-VS-FROZEN DIVERGENCE SET
# ==============================================================================
# frozen_guard_path stops Phase 3 from overwriting a frozen artifact, but a write
# guard on its own only proves nothing was written; it says nothing about whether the
# recomputation AGREES with the frozen record. FROZ-1 supplies the missing half: it
# diffs each ".PHASE3" sidecar against its frozen original field by field and fails on
# any divergence that was not declared here, before the run.
#
# "scope": "none"       -> zero divergence permitted. Any differing field is FATAL.
# "scope": "whole_file" -> this file is EXPECTED to differ, for the stated reason. The
#                          per-cell diff is still computed and written to
#                          froz1_divergences.csv so the change is on the record.
#
# Declaring a divergence is NOT the same as excusing it. "authoritative" records which
# side this run believes is correct, and for the one whole_file entry the frozen side is
# named as the DEFECTIVE side, which is the opposite of a rubber stamp.
FROZ1_KEY_COLUMN = {
    "a6_calibration_actions.csv": "action",
    "a6_calibration_deciles.csv": "decile",
    "a6_relative_bias.csv":       "pair",
}

FROZ1_DECLARED_DIVERGENCES = {
    # ---- Expected to be field-identical. These three were reported as "changed" by the
    # 2026-08-26 manifest only at the byte level; every value that the preserved Phase 2
    # snapshot publishes for them matches exactly (feature_count 12, 13 distinct
    # orderings, the five top orderings and counts 554/153/126/117/116, amount range
    # 97.03-279558.65, all six allowed counts, all six selections, verdict; 87/1348/0
    # and 0 flips / Rs.0.00; the 7/5/1/191 partition, 8 and 6 recoveries, -247409.56).
    # So "no field may differ" is the correct assertion, and it is a real one: it fails
    # if any recomputed value drifts.
    "a0_feature_audit.json":       {"scope": "none",
                                    "reason": "recomputed OP-V census; all snapshot-visible values matched"},
    "a1_close_wait.json":          {"scope": "none",
                                    "reason": "recomputed OP-V counterfactual; all snapshot-visible values matched"},
    "a4_partition_summary.json":   {"scope": "none",
                                    "reason": "OP-F read-only partition; all snapshot-visible values matched"},

    # ---- Expected to be field-identical because this run does NOT change the code that
    # produces them. The sign-convention and standard-error questions these two files
    # raise against the PHASE 2 record are real and are measured separately by the a6 SE
    # convention probe, which changes no published value. Nothing here is being quietly
    # fixed, and nothing here is being quietly permitted either.
    "a6_calibration_actions.csv":  {"scope": "none",
                                    "reason": "SE formula and gap sign convention deliberately left untouched pending explicit approval"},
    "a6_relative_bias.csv":        {"scope": "none",
                                    "reason": "relative-bias code path unmodified by this run"},

    # ---- Strict, exactly like every other frozen artifact above. The authoritative
    # decile calculation is index-based (see run_a6), which is precisely what produced
    # the frozen file, so the sidecar must reproduce it field for field and ANY
    # divergence is a failure. There is no declared divergence for this file any more:
    # the earlier "whole_file" exemption was defensible only while an amount-based
    # recomputation was authoritative, and that alternative was rejected on 2026-08-26.
    "a6_calibration_deciles.csv":  {"scope": "none",
                                    "reason": "index-based binning is authoritative and is what produced the frozen file; no divergence permitted"},
}

# A8 field-level rule. Dotted paths permitted to change, and nothing else.
A8_FIELD_RULE = {
    "cross_split_stability.oracle_net_per_txn_test",
    "cross_split_stability.oracle_net_per_txn_val",
    # ------------------------------------------------------------------------------
    # PRE-DECLARED TYPED-LITERAL CORRECTIONS (added 2026-08-26, BEFORE the rerun).
    #
    # All four fields below are the SAME class of change as oracle_net_per_txn_test
    # (2129.37 -> 2130.000713379835): Phase 2 hand-typed a DISPLAY-ROUNDED literal
    # into a8_carry_forward.json, and Phase 3 evaluates the identical formula on the
    # live full-precision inputs. No formula, cost, threshold, seed, split or
    # baseline changed. Derivations, from figures that are themselves asserted
    # elsewhere in this run:
    #
    #   gap_val        246130.78  -> 246130.78500000015
    #                  = val Policy A net - val B0 net
    #                  = 1,235,565.735 - 989,434.950 = 246,130.785
    #                  Phase 2 typed the 2dp form (246130.78) of a value whose exact
    #                  half-paisa tail is .785. Delta = +0.005.
    #
    #   gap_swing      444147.7   -> 444147.7080000001
    #                  = gap_val - gap_test
    #                  = 246,130.785 - (-198,016.923) = 444,147.708
    #                  Phase 2 typed the 1dp form. Delta = +0.008.
    #
    #   pa_pct_change  -4.3       -> -4.2625583673565615
    #                  = (pa_test_net/test_N - pa_val_net/val_N) / (pa_val_net/val_N) * 100
    #                  = (1,299,952.45/1,577 - 1,235,565.735/1,435)
    #                    / (1,235,565.735/1,435) * 100
    #                  = (824.3197527 - 861.0214878) / 861.0214878 * 100 = -4.2625584%
    #                  Phase 2 typed the 1dp form. Delta = +0.037pp.
    #
    #   b0_pct_change  37.8       -> 37.76404752205476
    #                  = (b0_test_net/test_N - b0_val_net/val_N) / (b0_val_net/val_N) * 100
    #                  = (1,497,969.37/1,577 - 989,434.945/1,435)
    #                    / (989,434.945/1,435) * 100
    #                  = (949.8855231 - 689.5017038) / 689.5017038 * 100 = +37.7640475%
    #                  Phase 2 typed the 1dp form. Delta = -0.036pp.
    #
    # NOT WIN MANUFACTURING: the two percentage corrections move in OPPOSITE
    # narrative directions and both are under 0.04pp. Policy A reads 0.037pp more
    # stable; B0 reads 0.036pp LESS volatile, which weakens rather than strengthens
    # the "B0 is volatile" framing. The headline conclusion is unchanged and rests on
    # the swing being inside the bootstrap CI, not on these decimals.
    #
    # SCOPE: this list is exhaustive and enumerated by dotted path. Any OTHER A8
    # field change still fails the run. The gate is not weakened, only pre-declared.
    # ------------------------------------------------------------------------------
    "cross_split_stability.gap_val",
    "cross_split_stability.gap_swing",
    "cross_split_stability.pa_pct_change",
    "cross_split_stability.b0_pct_change",
}

# Allowlist for LIT-1: structural numbers never in FIGURES
LIT1_ALLOWLIST = {
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12",
    "0.00", "0.25", "0.50", "0.75", "1.00",
    "1.96",
    "0.01",
    "0",
    # --- Structural / statistical constants, NOT data claims. -------------------
    # LIT-1 exists to catch hand-typed *quantities* (e.g. 2,129.37) that assert a
    # measured fact with no artifact behind them. The tokens below assert nothing
    # about the data: they are the confidence level, the lambda grid endpoints as
    # written in prose, and zero-residual / percent-scale renderings. Allowing them
    # cannot mask a fabricated figure, and the negative control (314159.99) still
    # proves the detector fires.
    "95",        # "95% CI" — the confidence level; pairs with 1.96 above
    "0.0", "1.0",  # "lambda=0.0 to lambda=1.0" in the shrinkage prose
    "0.0000",    # ATTR-1 residual rendered at :.4f when the residual is zero
    "100",       # percent scale in prose
}

# LIT-1 fail-first probes, checked against the PRESERVED pre-Phase-3 report.
# A detector that has never been observed to fire has not been shown to work, so the
# run refuses to trust LIT-1 until it flags a token that is known to be unsourceable.
#   "2,129.37"   -> MUST be unsourced. No artifact yields it; oracle_net/1577 = 2130.00.
#   "247,410.00" -> reported for information. It is the rounded Class R reference for a
#                   value A4 derives as -247,409.56, so depending on whether a FIGURES
#                   entry renders the Class R reference it may legitimately classify as
#                   sourced or class_r. Not a gate.
#   "133.2"      -> reported for information. CORRECTED after the 2026-08-26 run: this
#                   comment previously predicted it would classify as SOURCED. The run
#                   observed it as UNSOURCED, and that observation is right, not the
#                   prediction. The preserved snapshot's "133.2" is a Phase 2 rendering
#                   of 133.251, whereas "{:.1f}" renders that value as "133.3", so the
#                   snapshot token has no matching FIGURES rendering. Both denominators
#                   remain legitimate (133.3% of the wait->close subset gap, 166.5% of
#                   the total test deficit) and both are now registered and asserted by
#                   X4a/X4b. Not a gate.
LIT1_REQUIRED_DETECT = {"2,129.37", "247,410.00", "133.2"}
LIT1_PROBE_TOKENS    = ["2,129.37", "247,410.00", "133.2"]

RUN_LOG = []

# Set by main() as soon as the pre-run state is captured, so that an UNANTICIPATED crash
# (not just a gate failure) can still route through finalize() and report the SHA-256
# comparison instead of dying with a bare traceback and no accounting of what it wrote.
_FINALIZE_STATE = None


def log(msg=""):
    print(msg)
    RUN_LOG.append(str(msg))


# ==============================================================================
# DATA LOADING
# ==============================================================================
def load_data():
    ht = pd.read_csv("action_expanded_with_hidden_truth.csv")
    val_ht = ht[ht["split"] == "val"].copy()
    test_ht = ht[ht["split"] == "test"].copy()

    val_outcome_lookup = {}
    for _, row in val_ht.iterrows():
        val_outcome_lookup[(int(row["transaction_id"]), row["action"])] = int(row["outcome"])

    test_outcome_lookup = {}
    for _, row in test_ht.iterrows():
        test_outcome_lookup[(int(row["transaction_id"]), row["action"])] = int(row["outcome"])

    ctx_cols = [
        "transaction_id", "failure_type", "amount", "risk_score",
        "attempt_number", "contact_fatigue_score", "segment",
        "payment_method", "lifetime_successful_txns", "lifetime_failed_txns"
    ]
    val_txns = val_ht.drop_duplicates("transaction_id")[ctx_cols].reset_index(drop=True)
    test_txns = test_ht.drop_duplicates("transaction_id")[ctx_cols].reset_index(drop=True)

    model, err = load_model()
    if model is None:
        raise RuntimeError(f"Could not load model: {err}")

    return val_ht, val_txns, val_outcome_lookup, test_ht, test_txns, test_outcome_lookup, model


def build_ctx(row, dp=DEFAULT_DISCOUNT_PERCENT):
    ctx = row.to_dict()
    ctx["transaction_id"] = int(ctx["transaction_id"])
    ctx["attempt_number"] = int(ctx["attempt_number"])
    ctx["lifetime_successful_txns"] = int(ctx["lifetime_successful_txns"])
    ctx["lifetime_failed_txns"] = int(ctx["lifetime_failed_txns"])
    ctx["hours_since_failure"] = 6.0
    ctx["already_recovered"] = False
    ctx["discount_percent"] = dp
    return ctx


# ==============================================================================
# TASK 11 — SHA-256 MANIFEST
# ==============================================================================
def compute_sha256_manifest(artifacts_dir):
    manifest = {}
    if not os.path.isdir(artifacts_dir):
        return manifest
    for fname in sorted(os.listdir(artifacts_dir)):
        fpath = os.path.join(artifacts_dir, fname)
        if os.path.isfile(fpath):
            h = hashlib.sha256()
            with open(fpath, "rb") as f:
                h.update(f.read())
            manifest[fname] = h.hexdigest()
    return manifest


def frozen_guard_path(fname):
    """Return the path Phase 3 is ALLOWED to write for `fname`, and whether the write
    was redirected away from a frozen artifact.

    ROOT CAUSE THIS FIXES. Phase 3 declared nine artifacts FROZEN and then
    recomputed and overwrote six of them anyway (a0_feature_audit.json,
    a1_close_wait.json, a4_partition_summary.json and the three a6_*.csv files).
    A "frozen" declaration that the same script then violates is not a control at
    all -- it only reports the damage afterwards, by which time the Phase 2 bytes
    are gone. They were gone in exactly that way on the 2026-08-26 run: overwritten
    in place, and never committed (.git/COMMIT_EDITMSG is still "Complete M4 EV
    decision engine"), so no pre-run copy exists on disk or in git.

    From here on a frozen artifact is READ-ONLY to this script. The recomputation
    still happens -- it is the evidence FROZ-1 needs -- but it lands in a
    ".PHASE3" sidecar, and FROZ-1 then compares the sidecar against the frozen
    original field by field. That turns an opaque post-hoc hash mismatch into a
    named, field-level assertion, and it makes byte-identity of the six files
    automatic on every future run rather than a matter of luck.
    """
    if fname in FROZEN_ARTIFACTS and os.path.exists(os.path.join(ARTIFACTS_DIR, fname)):
        stem, ext = os.path.splitext(fname)
        return os.path.join(ARTIFACTS_DIR, f"{stem}.PHASE3{ext}"), True
    return os.path.join(ARTIFACTS_DIR, fname), False


def compare_manifests(pre, post, frozen_list):
    changed_frozen = []
    changed_allowed = []
    for fname in set(list(pre.keys()) + list(post.keys())):
        pre_h = pre.get(fname, "ABSENT")
        post_h = post.get(fname, "ABSENT")
        if pre_h != post_h:
            if fname in frozen_list:
                changed_frozen.append((fname, pre_h, post_h))
            else:
                changed_allowed.append((fname, pre_h, post_h))
    return (len(changed_frozen) == 0), changed_frozen, changed_allowed


def _froz1_cells(path):
    """Flatten a JSON or CSV artifact into {field_path: value} for field-level diffing.
    Returns None if the file is absent or unreadable, which FROZ-1 treats as a failure
    rather than silently skipping."""
    if not os.path.isfile(path):
        return None
    try:
        if path.endswith(".json"):
            with open(path, encoding="utf-8") as f:
                return _flatten_json(json.load(f))
        df = pd.read_csv(path)
        base = os.path.basename(path).replace(".PHASE3", "")
        keycol = FROZ1_KEY_COLUMN.get(base)
        cells = {}
        for i, row in df.iterrows():
            rk = str(row[keycol]) if (keycol and keycol in df.columns) else f"row{i}"
            for col in df.columns:
                if col == keycol:
                    continue
                cells[f"{rk}.{col}"] = row[col]
        return cells
    except Exception as exc:
        log(f"  FROZ-1: could not read {path}: {exc}")
        return None


def run_froz1():
    """Diff every ".PHASE3" sidecar against its frozen original, field by field.

    Passes only when every divergence is accounted for by FROZ1_DECLARED_DIVERGENCES,
    which was written before the run. Three distinct ways to fail:
      - a file declared "scope": "none" has ANY differing field
      - a sidecar or its frozen original is missing / unreadable
      - a sidecar exists for a file that was never declared at all
    Returns (passed, rows, summary) where rows are persisted to froz1_divergences.csv."""
    rows = []
    failures = []
    checked = 0

    for fname, decl in sorted(FROZ1_DECLARED_DIVERGENCES.items()):
        stem, ext = os.path.splitext(fname)
        frozen_path  = os.path.join(ARTIFACTS_DIR, fname)
        sidecar_path = os.path.join(ARTIFACTS_DIR, f"{stem}.PHASE3{ext}")

        if not os.path.isfile(sidecar_path):
            failures.append(f"{fname}: no sidecar written (recomputation did not run?)")
            rows.append({"file": fname, "field": "<SIDECAR>", "frozen": "", "sidecar": "",
                         "status": "MISSING", "declared": decl["scope"]})
            continue

        frozen_cells  = _froz1_cells(frozen_path)
        sidecar_cells = _froz1_cells(sidecar_path)
        if frozen_cells is None or sidecar_cells is None:
            failures.append(f"{fname}: unreadable frozen original or sidecar")
            rows.append({"file": fname, "field": "<READ>", "frozen": "", "sidecar": "",
                         "status": "UNREADABLE", "declared": decl["scope"]})
            continue

        checked += 1
        diverged = []
        for field in sorted(set(frozen_cells) | set(sidecar_cells)):
            a = frozen_cells.get(field, "<ABSENT>")
            b = sidecar_cells.get(field, "<ABSENT>")
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
                    and not isinstance(a, bool) and not isinstance(b, bool):
                same = abs(float(a) - float(b)) < 1e-9
            else:
                same = (str(a) == str(b))
            if not same:
                diverged.append((field, a, b))

        if decl["scope"] == "none":
            for field, a, b in diverged:
                rows.append({"file": fname, "field": field, "frozen": a, "sidecar": b,
                             "status": "UNDECLARED", "declared": "none"})
            if diverged:
                failures.append(f"{fname}: {len(diverged)} undeclared field divergence(s) "
                                f"(first: {diverged[0][0]} {diverged[0][1]} -> {diverged[0][2]})")
                log(f"  FROZ-1 FAIL {fname}: {len(diverged)} field(s) differ, zero were declared.")
                for field, a, b in diverged[:10]:
                    log(f"      {field}: frozen={a} sidecar={b}")
            else:
                log(f"  FROZ-1 PASS {fname}: {len(frozen_cells)} field(s), 0 divergences "
                    f"(declared: none permitted).")
        else:
            for field, a, b in diverged:
                rows.append({"file": fname, "field": field, "frozen": a, "sidecar": b,
                             "status": "DECLARED", "declared": decl["scope"]})
            log(f"  FROZ-1 DECLARED {fname}: {len(diverged)} field(s) differ across "
                f"{len(frozen_cells)} field(s). Authoritative side: "
                f"{decl.get('authoritative', 'unstated')}.")
            log(f"      reason: {decl['reason']}")

    stray = []
    _listing = sorted(os.listdir(ARTIFACTS_DIR)) if os.path.isdir(ARTIFACTS_DIR) else []
    for f in _listing:
        if ".PHASE3" in f:
            origin = f.replace(".PHASE3", "")
            if origin not in FROZ1_DECLARED_DIVERGENCES:
                stray.append(f)
    if stray:
        failures.append(f"undeclared sidecar(s) present: {stray}")
        for f in stray:
            rows.append({"file": f, "field": "<UNDECLARED FILE>", "frozen": "", "sidecar": "",
                         "status": "UNDECLARED", "declared": ""})

    pd.DataFrame(rows, columns=["file", "field", "frozen", "sidecar", "status", "declared"]).to_csv(
        os.path.join(ARTIFACTS_DIR, "froz1_divergences.csv"), index=False)

    n_undeclared = sum(1 for r in rows if r["status"] == "UNDECLARED")
    n_declared   = sum(1 for r in rows if r["status"] == "DECLARED")
    summary = (f"{checked}/{len(FROZ1_DECLARED_DIVERGENCES)} frozen artifact(s) diffed against "
               f"their sidecars; {n_declared} pre-declared field divergence(s); "
               f"{n_undeclared} undeclared; failures={failures or 'none'}")
    log(f"  FROZ-1 summary: {summary}")
    return (len(failures) == 0), rows, summary


def sha256_file(path):
    if not os.path.isfile(path):
        return "ABSENT"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def preserve_pre_phase3_report():
    """Copy the pre-Phase-3 report into an immutable snapshot. Idempotent: if the
    snapshot already exists it is NEVER overwritten, because on a second run the live
    report is already a Phase 3 product and would destroy the original evidence.
    Returns (snapshot_text, snapshot_sha256, created_now)."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    created = False
    if os.path.exists(SNAPSHOT_REPORT):
        log(f"  Snapshot already exists — NOT overwriting: {SNAPSHOT_REPORT}")
    elif os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, encoding="utf-8") as f:
            text = f.read()
        with open(SNAPSHOT_REPORT, "w", encoding="utf-8") as f:
            f.write(text)
        created = True
        log(f"  Created snapshot: {SNAPSHOT_REPORT}")
    else:
        log(f"  WARNING: no report at {REPORT_PATH} to preserve.")
        return None, "ABSENT", False

    with open(SNAPSHOT_REPORT, encoding="utf-8") as f:
        snap_text = f.read()
    snap_hash = sha256_file(SNAPSHOT_REPORT)
    log(f"  Snapshot SHA-256 (immutable for the rest of this run): {snap_hash}")
    log(f"  Snapshot lines: {len(snap_text.splitlines())}")
    return snap_text, snap_hash, created


def _flatten_json(obj, prefix=""):
    flat = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            flat.update(_flatten_json(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            flat.update(_flatten_json(v, f"{prefix}[{i}]"))
    else:
        flat[prefix] = obj
    return flat


def check_a8_field_changes(pre_text, post_path):
    """A8 is not byte-frozen because the oracle-per-transaction typed literal must be
    corrected. Enforce that ONLY the permitted fields changed.
      changed existing value, not whitelisted -> FATAL
      removed key                             -> FATAL
      added key                               -> permitted, reported
    Returns (ok, violations, permitted, added, removed)."""
    if pre_text is None:
        return True, [], [], [], []
    try:
        pre_flat = _flatten_json(json.loads(pre_text))
    except Exception as exc:
        return False, [(f"<unparseable pre-run a8: {exc}>", "", "")], [], [], []
    with open(post_path, encoding="utf-8") as f:
        post_flat = _flatten_json(json.load(f))

    violations, permitted = [], []
    added   = sorted(set(post_flat) - set(pre_flat))
    removed = sorted(set(pre_flat) - set(post_flat))
    for path in sorted(set(pre_flat) & set(post_flat)):
        a, b = pre_flat[path], post_flat[path]
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
            same = abs(float(a) - float(b)) < 0.005
        else:
            same = (a == b)
        if not same:
            (permitted if path in A8_FIELD_RULE else violations).append((path, a, b))
    for path in removed:
        violations.append((path, pre_flat[path], "<REMOVED>"))
    return len(violations) == 0, violations, permitted, added, removed


def finalize(pre_manifest, report_pre_hash, a8_pre_text, code, reason):
    """SHA-256 comparison + pre-registered change-set enforcement. Runs on EVERY exit
    path, success or failure, so an aborted run still reports exactly what it wrote.
    Always terminates the process with an explicit exit code."""
    log("=" * 80)
    log(f"FINALIZE — {reason}")
    log("=" * 80)

    post_manifest = compute_sha256_manifest(ARTIFACTS_DIR)
    frozen_ok, changed_frozen, changed_allowed = compare_manifests(
        pre_manifest, post_manifest, FROZEN_ARTIFACTS)

    fatal = []

    if changed_frozen:
        log("FROZEN ARTIFACT VIOLATION:")
        for fname, p, q in changed_frozen:
            log(f"  {fname}: {p[:16]} -> {q[:16]}")
        fatal.append(f"{len(changed_frozen)} frozen artifact(s) changed")
    else:
        log(f"Frozen artifacts: 0 of {len(FROZEN_ARTIFACTS)} changed. PASS.")

    changed_names = {fname for fname, _, _ in changed_allowed}
    unexpected = changed_names - EXPECTED_CHANGES
    declared_no_change = EXPECTED_CHANGES - changed_names
    log(f"Non-frozen artifacts changed: {len(changed_names)}")
    for fname, p, q in sorted(changed_allowed):
        tag = "NEW" if p == "ABSENT" else f"{p[:12]}..."
        log(f"  {'EXPECTED ' if fname in EXPECTED_CHANGES else 'UNEXPECTED'} {fname}: {tag} -> {q[:12]}...")
    if unexpected:
        log("PRE-REGISTERED CHANGE-SET VIOLATION — these changed but were never declared:")
        for fname in sorted(unexpected):
            log(f"  {fname}")
        fatal.append(f"{len(unexpected)} undeclared artifact change(s)")
    if declared_no_change:
        log(f"Declared-but-unchanged (informational, not a failure): {sorted(declared_no_change)}")

    a8_post = os.path.join(ARTIFACTS_DIR, "a8_carry_forward.json")
    if os.path.isfile(a8_post):
        a8_ok, a8_viol, a8_perm, a8_add, a8_rem = check_a8_field_changes(a8_pre_text, a8_post)
        log("A8 field-level rule:")
        for path, a, b in a8_perm:
            log(f"  PERMITTED (typed-literal correction) {path}: {a} -> {b}")
        for path in a8_add:
            log(f"  ADDED (permitted, reported) {path}")
        for path, a, b in a8_viol:
            log(f"  VIOLATION {path}: {a} -> {b}")
        if not a8_ok:
            fatal.append(f"{len(a8_viol)} unpermitted A8 field change(s)")
        else:
            log(f"  A8: {len(a8_perm)} permitted change(s), {len(a8_add)} addition(s), 0 violations. PASS.")

    report_post_hash = sha256_file(REPORT_PATH)
    log("Report hash transition (tracked, not frozen):")
    log(f"  pre : {report_pre_hash}")
    log(f"  post: {report_post_hash}")
    log(f"  {'CHANGED' if report_pre_hash != report_post_hash else 'UNCHANGED'}")
    log(f"Immutable snapshot still present: {os.path.exists(SNAPSHOT_REPORT)} "
        f"(sha256={sha256_file(SNAPSHOT_REPORT)})")

    if fatal:
        code = 1
        log("FATAL: " + "; ".join(fatal))

    log("=" * 80)
    log(f"EXITING WITH CODE {code}")
    log("=" * 80)
    with open(os.path.join(ARTIFACTS_DIR, "run_log.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(RUN_LOG))
    sys.exit(code)


# ==============================================================================
# A0 — M2 FEATURE CONSTRUCTION AND ACTION-PAIR ORDERING [GATE]
# ==============================================================================
def run_a0(val_txns, model):
    log("=" * 80)
    log("A0 — M2 FEATURE CONSTRUCTION AND ACTION-PAIR ORDERING [GATE]")
    log("=" * 80)

    feature_names = [
        "failure_type", "action", "segment", "payment_method", "failure_action", "segment_action",
        "risk_score", "attempt_number", "contact_fatigue_score",
        "log1p_amount", "log1p_lifetime_successful_txns", "log1p_lifetime_failed_txns"
    ]
    feature_count = len(feature_names)

    with open("ml/models/model_metadata.json", "r") as f:
        meta = json.load(f)
    meta_features = meta["features"]["categorical"] + meta["features"]["numeric_raw"]
    meta_model_class = meta["model_type"]

    all_actions = ["retry", "payment_link", "reminder", "discount", "wait", "close"]
    n_val = len(val_txns)

    pred_matrix = []
    for _, row in val_txns.iterrows():
        ctx = build_ctx(row)
        tid = ctx["transaction_id"]
        row_probs = {}
        for a in all_actions:
            row_probs[a] = predict_probability(model, ctx, a)
        pred_matrix.append({"transaction_id": tid, "amount": ctx["amount"], **row_probs})

    pred_df = pd.DataFrame(pred_matrix)

    orderings = []
    for _, r in pred_df.iterrows():
        sorted_acts = tuple(sorted(all_actions, key=lambda a: -r[a]))
        orderings.append(sorted_acts)

    order_series = pd.Series(orderings)
    distinct_orderings_count = int(order_series.nunique())
    top5_orderings = order_series.value_counts().head(5)

    log(f"A0.1 Feature Count: {feature_count} columns.")
    log(f"A0.2 Ordering Census: {distinct_orderings_count} distinct full orderings across {n_val} validation transactions.")

    pair_orderings_data = []
    pairs_15 = []
    for i in range(len(all_actions)):
        for j in range(i + 1, len(all_actions)):
            a, b = all_actions[i], all_actions[j]
            pairs_15.append((a, b))
            a_gt_b = int((pred_df[a] > pred_df[b] + 1e-9).sum())
            b_gt_a = int((pred_df[b] > pred_df[a] + 1e-9).sum())
            ties = int((abs(pred_df[a] - pred_df[b]) <= 1e-9).sum())
            distinct_orders = (1 if a_gt_b > 0 else 0) + (1 if b_gt_a > 0 else 0)
            diffs = (pred_df[a] - pred_df[b]).abs()
            pair_orderings_data.append({
                "pair": f"{a}_vs_{b}", "a": a, "b": b,
                "a_gt_b_count": a_gt_b, "b_gt_a_count": b_gt_a, "tie_count": ties,
                "distinct_orderings": distinct_orders,
                "min_abs_diff": float(diffs.min()),
                "median_abs_diff": float(diffs.median()),
                "max_abs_diff": float(diffs.max()),
            })

    pair_ord_df = pd.DataFrame(pair_orderings_data)
    pair_ord_df.to_csv(os.path.join(ARTIFACTS_DIR, "a0_pair_orderings.csv"), index=False)

    p_close_wait = pair_ord_df[pair_ord_df["pair"] == "wait_vs_close"].iloc[0]

    val_min_amt = float(val_txns["amount"].min())
    val_max_amt = float(val_txns["amount"].max())

    allowed_counts = {a: 0 for a in all_actions}
    actual_selections = {a: 0 for a in all_actions}
    for _, row in val_txns.iterrows():
        ctx = build_ctx(row)
        pr = evaluate_policy(ctx)
        dec = make_decision(ctx, model_pipeline=model)
        for a in pr["allowed_actions"]:
            if a in allowed_counts:
                allowed_counts[a] += 1
        act = dec["decision"]
        if act in actual_selections:
            actual_selections[act] += 1

    if distinct_orderings_count > 1:
        a0_verdict = "INTERACTIONS PRESENT"
    else:
        a0_verdict = "NO INTERACTIONS"
    log(f"A0 VERDICT: {a0_verdict}")

    a0_audit_artifact = {
        "split": "val", "data_operation": "OP-V",
        "feature_count": feature_count, "feature_names": feature_names,
        "metadata_feature_count": len(meta_features), "metadata_model_class": meta_model_class,
        "distinct_full_orderings": distinct_orderings_count,
        "top_orderings": [{"order": ">".join(k), "count": int(v)} for k, v in top5_orderings.items()],
        "val_amount_min": val_min_amt, "val_amount_max": val_max_amt,
        "allowed_counts": allowed_counts, "actual_selections": actual_selections,
        "verdict": a0_verdict
    }
    _a0_path, _a0_redir = frozen_guard_path("a0_feature_audit.json")
    with open(_a0_path, "w") as f:
        json.dump(a0_audit_artifact, f, indent=2)

    return pred_df, a0_verdict, p_close_wait, allowed_counts, actual_selections, a0_audit_artifact


# ==============================================================================
# A1 — RECOMPUTE P(close) > P(wait)
# ==============================================================================
def run_a1(pred_df, val_txns, val_outcome_lookup, model):
    log("=" * 80)
    log("A1 — RECOMPUTE P(close) > P(wait) (OP-V)")
    log("=" * 80)

    n_val = len(pred_df)
    p_close_gt_wait = int((pred_df["close"] > pred_df["wait"] + 1e-9).sum())
    p_wait_gt_close = int((pred_df["wait"] > pred_df["close"] + 1e-9).sum())
    p_equal = int((abs(pred_df["close"] - pred_df["wait"]) <= 1e-9).sum())

    dp = DEFAULT_DISCOUNT_PERCENT
    std_decisions = []
    corr_decisions = []

    for _, row in val_txns.iterrows():
        ctx = build_ctx(row, dp)
        tid = ctx["transaction_id"]
        amt = ctx["amount"]
        pr = evaluate_policy(ctx)
        allowed = pr["allowed_actions"]
        esc = pr["escalation_required"]
        terminal = pr["terminal"]
        scoreable = [a for a in allowed if a != "escalate"]
        probs = {a: predict_probability(model, ctx, a) for a in scoreable}

        ev_std = {a: calculate_ev(a, probs[a], amt, dp) for a in scoreable}
        if terminal and len(allowed) == 0:
            std_act = "no_action_required"
        elif terminal and len(allowed) == 1:
            std_act = allowed[0]
        elif len(ev_std) == 0:
            std_act = "escalate" if esc and "escalate" in allowed else "no_action_required"
        else:
            std_act, _, _ = select_best_action(ev_std)
        std_out = val_outcome_lookup.get((tid, std_act), 0) if std_act not in ("escalate", "no_action_required") else 0
        std_decisions.append({"transaction_id": tid, "action": std_act, **score_action(std_act, std_out, amt, dp)})

        ev_corr = {}
        for a in scoreable:
            if a == "close":
                ev_corr["close"] = {
                    "action": "close", "predicted_probability": probs["close"],
                    "recoverable_amount": amt, "gross_expected_recovery": probs["close"] * amt,
                    "intervention_cost": 0.0, "discount_amount": 0.0,
                    "expected_net_value": probs["close"] * amt,
                }
            else:
                ev_corr[a] = calculate_ev(a, probs[a], amt, dp)

        if terminal and len(allowed) == 0:
            corr_act = "no_action_required"
        elif terminal and len(allowed) == 1:
            corr_act = allowed[0]
        elif len(ev_corr) == 0:
            corr_act = "escalate" if esc and "escalate" in allowed else "no_action_required"
        else:
            corr_act, _, _ = select_best_action(ev_corr)
        corr_out = val_outcome_lookup.get((tid, corr_act), 0) if corr_act not in ("escalate", "no_action_required") else 0
        corr_decisions.append({"transaction_id": tid, "action": corr_act, **score_action(corr_act, corr_out, amt, dp)})

    std_df = pd.DataFrame(std_decisions)
    corr_df = pd.DataFrame(corr_decisions)

    flips = int((std_df["action"] != corr_df["action"]).sum())
    std_net = float(std_df["net_recovered_amount"].sum())
    corr_net = float(corr_df["net_recovered_amount"].sum())
    delta_net = float(corr_net - std_net)

    log(f"P(close) > P(wait): {p_close_gt_wait}, Flips on corrected EV: {flips}, Delta: Rs.{delta_net:,.2f}")

    a1_artifact = {
        "split": "val", "data_operation": "OP-V", "n_validation": n_val,
        "p_close_gt_wait_count": p_close_gt_wait, "p_wait_gt_close_count": p_wait_gt_close,
        "p_equal_count": p_equal, "flips_count": flips,
        "standard_net": std_net, "corrected_net": corr_net, "delta_net": delta_net,
        "h4_status": "CLOSED AS FALSE (0 flips, Rs. 0.00 value impact on validation)"
    }
    _a1_path, _a1_redir = frozen_guard_path("a1_close_wait.json")
    with open(_a1_path, "w") as f:
        json.dump(a1_artifact, f, indent=2)

    return std_df, a1_artifact


# ==============================================================================
# TASK 4 — DETERMINE CONVENTION VIA AST INSPECTION
# ==============================================================================
def determine_convention_ast(source_path):
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    tree = _ast.parse(source)
    lines = source.splitlines()
    detail = {
        "source_file": source_path,
        "p1_pass": False, "p1_lines": [],
        "p2_pass": False, "p2_lines": [],
        "p3_pass": True, "p3_lines": [],
    }

    score_action_func = None
    for node in _ast.walk(tree):
        if isinstance(node, _ast.FunctionDef) and node.name == "score_action":
            score_action_func = node
            break
    if score_action_func is None:
        raise RuntimeError("score_action() not found in experiment_metrics.py")

    assignments = []
    for node in _ast.walk(score_action_func):
        if isinstance(node, _ast.Assign):
            for target in node.targets:
                if isinstance(target, _ast.Name):
                    assignments.append({"target": target.id, "value_node": node.value, "lineno": node.lineno})

    def _name_of(node):
        return node.id if isinstance(node, _ast.Name) else None

    def _is_sub(node, left_name, right_name):
        return (isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Sub)
                and _name_of(node.left) == left_name and _name_of(node.right) == right_name)

    def _subtrahends(node):
        result = []
        while isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Sub):
            if isinstance(node.right, _ast.Name):
                result.append(node.right.id)
            node = node.left
        return result

    for asgn in assignments:
        if asgn["target"] == "recovered_amount" and _is_sub(asgn["value_node"], "amount", "discount_amount"):
            detail["p1_lines"].append(asgn["lineno"])
        if asgn["target"] == "net_recovered_amount":
            if _is_sub(asgn["value_node"], "recovered_amount", "intervention_cost"):
                detail["p2_lines"].append(asgn["lineno"])
            if "discount_amount" in _subtrahends(asgn["value_node"]):
                detail["p3_pass"] = False
                detail["p3_lines"].append(asgn["lineno"])

    detail["p1_pass"] = len(detail["p1_lines"]) > 0
    detail["p2_pass"] = len(detail["p2_lines"]) > 0

    if detail["p1_pass"] and detail["p2_pass"] and detail["p3_pass"]:
        return "C1", detail
    failures = []
    if not detail["p1_pass"]: failures.append("P1")
    if not detail["p2_pass"]: failures.append("P2")
    if not detail["p3_pass"]: failures.append(f"P3 (violations at lines {detail['p3_lines']})")
    raise RuntimeError(f"Convention determination failed: {'; '.join(failures)}")


# ==============================================================================
# A2 — ACCOUNTING CONVENTION AND POLICY ROWS
# ==============================================================================
def run_a2(val_txns, val_outcome_lookup, model):
    log("=" * 80)
    log("A2 — ACCOUNTING CONVENTION (AST) AND POLICY ROWS")
    log("=" * 80)

    convention, conv_detail = determine_convention_ast(EXPERIMENT_METRICS_PATH)
    log(f"Convention determined via AST: {convention} (P1 lines={conv_detail['p1_lines']}, P2 lines={conv_detail['p2_lines']})")

    with open(os.path.join(ARTIFACTS_DIR, "a2_convention.json"), "w") as f:
        json.dump({
            "convention": convention,
            "description": "gross is POST-haircut; net = gross - intervention_cost; discount_amount is reporting-only",
            "source_file": "ml/experiment/experiment_metrics.py",
            "p1_pass": conv_detail["p1_pass"], "p1_source_lines": conv_detail["p1_lines"],
            "p2_pass": conv_detail["p2_pass"], "p2_source_lines": conv_detail["p2_lines"],
            "p3_pass": conv_detail["p3_pass"], "p3_violation_lines": conv_detail["p3_lines"],
        }, f, indent=2)

    dp = DEFAULT_DISCOUNT_PERCENT
    pa_val_decisions = []
    b0_val_decisions = []

    for _, row in val_txns.iterrows():
        ctx = build_ctx(row, dp)
        tid = ctx["transaction_id"]
        amt = ctx["amount"]
        pr = evaluate_policy(ctx)
        allowed = pr["allowed_actions"]
        esc = pr["escalation_required"]
        terminal = pr["terminal"]

        dec = make_decision(ctx, model_pipeline=model)
        pa_act = dec["decision"]
        pa_out = val_outcome_lookup.get((tid, pa_act), 0) if pa_act not in ("escalate", "no_action_required") else 0
        pa_val_decisions.append({"transaction_id": tid, "action": pa_act, **score_action(pa_act, pa_out, amt, dp)})

        b0_act, _, _ = select_b0_waterfall(allowed, esc, terminal, ctx["attempt_number"])
        b0_out = val_outcome_lookup.get((tid, b0_act), 0) if b0_act not in ("escalate", "no_action_required") else 0
        b0_val_decisions.append({"transaction_id": tid, "action": b0_act, **score_action(b0_act, b0_out, amt, dp)})

    pa_val_df = pd.DataFrame(pa_val_decisions)
    b0_val_df = pd.DataFrame(b0_val_decisions)

    per_txn = pd.read_csv(PER_TXN_PATH)
    pa_test_df = per_txn[per_txn["policy"] == "policy_a"].copy()
    b0_test_df = per_txn[per_txn["policy"] == "b0_waterfall"].copy()
    b1_test_df = per_txn[per_txn["policy"] == "b1_random"].copy()
    b6_test_df = per_txn[per_txn["policy"] == "b6_oracle"].copy()

    def _policy_row(split, data_op, policy, df):
        return {
            "split": split, "data_op": data_op, "policy": policy,
            "n_transactions": len(df),
            "recovered_count": int(df["recovered"].sum()),
            "recovery_rate": float(df["recovered"].mean() * 100),
            "gross_amount": float(df["recovered_amount"].sum()),
            "intervention_cost": float(df["intervention_cost"].sum()),
            "discount_haircut": float(df["discount_amount"].sum()),
            "net_amount": float(df["net_recovered_amount"].sum()),
            "net_per_txn": float(df["net_recovered_amount"].sum() / len(df)),
        }

    policy_rows = [
        _policy_row("val",  "OP-V", "policy_a",    pa_val_df),
        _policy_row("val",  "OP-V", "b0_waterfall", b0_val_df),
        _policy_row("test", "OP-F", "policy_a",    pa_test_df),
        _policy_row("test", "OP-F", "b0_waterfall", b0_test_df),
        _policy_row("test", "OP-F", "b1_random",   b1_test_df),
        _policy_row("test", "OP-F", "b6_oracle",   b6_test_df),
    ]

    policy_rows_df = pd.DataFrame(policy_rows)
    policy_rows_df.to_csv(os.path.join(ARTIFACTS_DIR, "a2_policy_rows.csv"), index=False)

    for _, r in policy_rows_df.iterrows():
        log(f"  [{r['split'].upper()} {r['data_op']}] {r['policy']:<15s}: "
            f"Rec={r['recovered_count']:>3d} ({r['recovery_rate']:>5.2f}%), "
            f"Net=Rs.{r['net_amount']:>12,.2f}")

    return policy_rows_df, pa_val_df, b0_val_df, convention


# ==============================================================================
# A3 — P3 SHRINKAGE SWEEP
# ==============================================================================
def run_a3(val_txns, val_outcome_lookup, model):
    log("=" * 80)
    log("A3 — P3 SHRINKAGE SWEEP (OP-V)")
    log("=" * 80)

    all_actions = ["retry", "payment_link", "reminder", "discount", "wait", "close"]
    dp = DEFAULT_DISCOUNT_PERCENT

    live_pa_decisions = []
    for _, row in val_txns.iterrows():
        ctx = build_ctx(row, dp)
        tid = ctx["transaction_id"]
        amt = ctx["amount"]
        dec = make_decision(ctx, model_pipeline=model)
        act = dec["decision"]
        out = val_outcome_lookup.get((tid, act), 0) if act not in ("escalate", "no_action_required") else 0
        live_pa_decisions.append({"transaction_id": tid, "action": act, **score_action(act, out, amt, dp)})

    live_pa_df = pd.DataFrame(live_pa_decisions)
    live_pa_net = float(live_pa_df["net_recovered_amount"].sum())
    log(f"Live M4 Validation Net Baseline: Rs. {live_pa_net:,.2f}")

    with open(os.path.join(ARTIFACTS_DIR, "a3_harness_baseline.json"), "w") as f:
        json.dump({
            "split": "val", "data_operation": "OP-V",
            "live_class_h_validation_net": live_pa_net,
            "class_r_reference_value": 1235565.73,
            "agree": bool(abs(live_pa_net - 1235565.73) < 0.01)
        }, f, indent=2)

    allowed_preds = {a: [] for a in all_actions}
    all_preds = {a: [] for a in all_actions}
    val_cache = {}

    for _, row in val_txns.iterrows():
        ctx = build_ctx(row, dp)
        tid = ctx["transaction_id"]
        pr = evaluate_policy(ctx)
        allowed = pr["allowed_actions"]
        probs = {}
        for a in all_actions:
            p = predict_probability(model, ctx, a)
            probs[a] = p
            all_preds[a].append(p)
            if a in allowed:
                allowed_preds[a].append(p)
        val_cache[tid] = {
            "ctx": ctx, "allowed": allowed,
            "esc": pr["escalation_required"], "terminal": pr["terminal"], "probs": probs
        }

    pbar_data = []
    for a in all_actions:
        pbar_data.append({
            "action": a,
            "pbar_allowed": float(np.mean(allowed_preds[a])),
            "n_allowed": len(allowed_preds[a]),
            "pbar_all_txns": float(np.mean(all_preds[a])),
            "n_all_txns": len(all_preds[a]),
        })
    pbar_df = pd.DataFrame(pbar_data)
    pbar_df.to_csv(os.path.join(ARTIFACTS_DIR, "a3_pbar.csv"), index=False)
    pbar_allowed_dict = dict(zip(pbar_df["action"], pbar_df["pbar_allowed"]))

    lambdas = [0.0, 0.25, 0.5, 0.75, 1.0]
    sweep_results = []
    simulated_decisions_by_lam = {}
    prior_class_r_sweep = {0.00: 1058557.21, 0.25: 1139204.48, 0.50: 1182206.78, 0.75: 1183920.74, 1.00: 1235565.73}

    for lam in lambdas:
        decisions = []
        for tid, data in val_cache.items():
            ctx = data["ctx"]
            amt = ctx["amount"]
            allowed = data["allowed"]
            esc = data["esc"]
            terminal = data["terminal"]
            probs = data["probs"]
            scoreable = [a for a in allowed if a != "escalate"]
            shrunk_ev = {}
            for a in scoreable:
                p_shrunk = lam * probs[a] + (1.0 - lam) * pbar_allowed_dict[a]
                shrunk_ev[a] = calculate_ev(a, p_shrunk, amt, dp)
            if terminal and len(allowed) == 0:
                act = "no_action_required"
            elif terminal and len(allowed) == 1:
                act = allowed[0]
            elif len(shrunk_ev) == 0:
                act = "escalate" if esc and "escalate" in allowed else "no_action_required"
            else:
                act, _, _ = select_best_action(shrunk_ev)
            out = val_outcome_lookup.get((tid, act), 0) if act not in ("escalate", "no_action_required") else 0
            decisions.append({"transaction_id": tid, "action": act, **score_action(act, out, amt, dp)})

        df = pd.DataFrame(decisions)
        simulated_decisions_by_lam[lam] = df
        net_val = float(df["net_recovered_amount"].sum())
        rec_cnt = int(df["recovered"].sum())
        rec_rt = float(df["recovered"].mean() * 100)
        dist = df["action"].value_counts().to_dict()
        prior_val = prior_class_r_sweep[lam]
        delta_prior = net_val - prior_val
        sweep_results.append({
            "split": "val", "data_op": "OP-V", "lambda": lam,
            "net_recovered_amount": net_val, "prior_class_r_net": prior_val,
            "delta_from_prior": delta_prior, "recovered_count": rec_cnt,
            "recovery_rate": rec_rt, "action_distribution": str(dist),
        })

    sweep_df = pd.DataFrame(sweep_results)
    sweep_df.to_csv(os.path.join(ARTIFACTS_DIR, "a3_lambda_sweep.csv"), index=False)

    lam1_df = simulated_decisions_by_lam[1.0]
    net_diff_p3_1 = abs(lam1_df["net_recovered_amount"].sum() - live_pa_net)
    agree_rate_p3_1 = (lam1_df["action"] == live_pa_df["action"]).mean() * 100
    log(f"P3-1: Net diff={net_diff_p3_1:.4f}, Agreement={agree_rate_p3_1:.2f}%")

    derived_lam0_actions = []
    for tid, data in val_cache.items():
        ctx = data["ctx"]
        amt = ctx["amount"]
        allowed = data["allowed"]
        esc = data["esc"]
        terminal = data["terminal"]
        scoreable = [a for a in allowed if a != "escalate"]
        shrunk_ev = {a: calculate_ev(a, pbar_allowed_dict[a], amt, dp) for a in scoreable}
        if terminal and len(allowed) == 0:
            act = "no_action_required"
        elif terminal and len(allowed) == 1:
            act = allowed[0]
        elif len(shrunk_ev) == 0:
            act = "escalate" if esc and "escalate" in allowed else "no_action_required"
        else:
            act, _, _ = select_best_action(shrunk_ev)
        derived_lam0_actions.append(act)

    lam0_sim_actions = list(simulated_decisions_by_lam[0.0]["action"])
    p3_2_match = (derived_lam0_actions == lam0_sim_actions)
    log(f"P3-2: lambda=0 match: {p3_2_match}")

    return sweep_df, net_diff_p3_1, agree_rate_p3_1, p3_2_match, val_cache


# ==============================================================================
# A4 — P5 PARTITION
# ==============================================================================
def run_a4():
    log("=" * 80)
    log("A4 — P5 PARTITION (OP-F)")
    log("=" * 80)

    per_txn = pd.read_csv(PER_TXN_PATH)
    pa_test = per_txn[per_txn["policy"] == "policy_a"].reset_index(drop=True)
    b0_test = per_txn[per_txn["policy"] == "b0_waterfall"].reset_index(drop=True)
    merged = pa_test.merge(b0_test, on="transaction_id", suffixes=("_pa", "_b0"))
    the_204 = merged[(merged["action_pa"] == "wait") & (merged["action_b0"] == "close")].copy()

    derived_count = len(the_204)
    derived_net_diff = float(the_204["net_recovered_amount_pa"].sum() - the_204["net_recovered_amount_b0"].sum())
    log(f"Wait->close set: {derived_count} txns, Net diff=Rs.{derived_net_diff:,.2f}")

    with open(os.path.join(ARTIFACTS_DIR, "a4_population.json"), "w") as f:
        json.dump({
            "split": "test", "data_operation": "OP-F",
            "derived_count": derived_count, "derived_net_diff": derived_net_diff,
            "class_r_count": 204, "class_r_net_diff": -247410.0,
            "agree": bool(derived_count == 204 and abs(derived_net_diff - (-247410.0)) < 1.0)
        }, f, indent=2)

    the_204["wait_rec"] = the_204["recovered_pa"].astype(bool)
    the_204["close_rec"] = the_204["recovered_b0"].astype(bool)

    partition_rows = []
    for _, r in the_204.iterrows():
        tid = int(r["transaction_id"])
        amt = float(r["amount_pa"])
        ft = r["failure_type_pa"]
        w_rec = bool(r["wait_rec"])
        c_rec = bool(r["close_rec"])
        if c_rec and not w_rec:
            cat = "CLOSE_ONLY"
        elif w_rec and not c_rec:
            cat = "WAIT_ONLY"
        elif w_rec and c_rec:
            cat = "BOTH"
        else:
            cat = "NEITHER"
        partition_rows.append({
            "transaction_id": tid, "amount": amt, "failure_type": ft,
            "wait_recovered": w_rec, "close_recovered": c_rec, "category": cat
        })

    part_df = pd.DataFrame(partition_rows)
    part_df.to_csv(os.path.join(ARTIFACTS_DIR, "a4_partition_rows.csv"), index=False)

    close_only_df = part_df[part_df["category"] == "CLOSE_ONLY"]
    wait_only_df  = part_df[part_df["category"] == "WAIT_ONLY"]
    both_df       = part_df[part_df["category"] == "BOTH"]
    neither_df    = part_df[part_df["category"] == "NEITHER"]

    close_only_n     = len(close_only_df)
    close_only_total = float(close_only_df["amount"].sum())
    wait_only_n      = len(wait_only_df)
    wait_only_total  = float(wait_only_df["amount"].sum())
    both_n           = len(both_df)
    both_total       = float(both_df["amount"].sum())
    neither_n        = len(neither_df)
    neither_total    = float(neither_df["amount"].sum())

    close_rec_n     = close_only_n + both_n
    close_rec_total = close_only_total + both_total
    wait_rec_n      = wait_only_n + both_n
    wait_rec_total  = wait_only_total + both_total

    top3_close_only = close_only_df.sort_values("amount", ascending=False).head(3)
    top3_close_sum  = float(top3_close_only["amount"].sum())

    # ------------------------------------------------------------------
    # TWO DENOMINATORS, TWO FIGURES. Both are legitimate and they are NOT equal.
    #
    #   waitclose_subset_gap = -247,409.56  (the 204 wait->close txns only)
    #   total_test_gap       = -198,016.92  (Policy A net minus B0 net, whole test split)
    #
    #   329,675.72 / 247,409.56 * 100 = 133.251%  <- share of the SUBSET gap
    #   329,675.72 / 198,016.92 * 100 = 166.489%  <- share of the TOTAL test deficit
    #
    # The pre-Phase-3 report (snapshot line 163) correctly published BOTH:
    #   "Rs.329,675.72 (133.2% of the -Rs.247,410 gap; 166.5% of the -Rs.198,017
    #    test deficit)"
    # so neither figure is new and neither may be dropped or relabelled. The X4
    # failure was caused by only ONE of them being registered, under a name
    # ("top3_pct_of_test_gap") that says "test gap" but holds the SUBSET value.
    # The subset denominator is kept under its original key for byte-compatibility
    # with the frozen artifact; the two unambiguous keys are built in the FIGURES
    # registry below, where BOTH denominators are in scope (run_a4 does not see the
    # A2/A5 test nets, so computing the total-deficit share here would require
    # passing them in and would add keys to a frozen artifact).
    # ------------------------------------------------------------------
    waitclose_subset_gap = abs(derived_net_diff)
    top3_pct_of_waitclose_subset_gap = (
        top3_close_sum / waitclose_subset_gap * 100) if waitclose_subset_gap > 0 else 0.0

    p5_1_pass = abs((close_only_total + both_total) - close_rec_total) < 1.0
    p5_2_pass = abs((wait_only_total  + both_total) - wait_rec_total)  < 1.0
    p5_3_pass = (close_only_n + both_n == close_rec_n) and (wait_only_n + both_n == wait_rec_n)
    p5_4_pass = abs((wait_only_total - close_only_total) - derived_net_diff) < 1.0
    p5_5_pass = (close_only_n + wait_only_n + both_n + neither_n == derived_count)

    both_ids = [int(x) for x in both_df["transaction_id"]]
    summary_artifact = {
        "split": "test", "data_operation": "OP-F",
        "derived_count": derived_count, "derived_net_diff": derived_net_diff,
        "close_only_n": close_only_n, "close_only_total": close_only_total,
        "wait_only_n": wait_only_n,  "wait_only_total": wait_only_total,
        "both_n": both_n,             "both_total": both_total,
        "neither_n": neither_n,       "neither_total": neither_total,
        "close_recovered_n": close_rec_n, "close_recovered_total": close_rec_total,
        "wait_recovered_n": wait_rec_n,   "wait_recovered_total": wait_rec_total,
        "top3_close_only_ids": [int(x) for x in top3_close_only["transaction_id"]],
        "top3_close_only_sum": top3_close_sum,
        # LEGACY KEY NAME, DELIBERATELY UNCHANGED. This holds the share of the
        # wait->close SUBSET gap (133.251%), not the total test gap, despite its
        # name. Renaming it would alter a frozen artifact, so the name stays and
        # the FIGURES registry exposes both shares under unambiguous keys.
        "top3_pct_of_test_gap": top3_pct_of_waitclose_subset_gap,
        "both_transaction_ids": both_ids
    }
    _a4_path, _a4_redir = frozen_guard_path("a4_partition_summary.json")
    with open(_a4_path, "w") as f:
        json.dump(summary_artifact, f, indent=2)

    return summary_artifact, (p5_1_pass and p5_2_pass and p5_3_pass and p5_4_pass and p5_5_pass)


# ==============================================================================
# TASK 3 — A5 REBUILT FROM FULL SUBSTITUTION MATRIX
# ==============================================================================
def run_a5(per_txn_path):
    log("=" * 80)
    log("A5 — FULL SUBSTITUTION ATTRIBUTION (rebuilt from per_transaction_decisions.csv)")
    log("=" * 80)

    per_txn = pd.read_csv(per_txn_path)
    pa_test = per_txn[per_txn["policy"] == "policy_a"].reset_index(drop=True)
    b0_test = per_txn[per_txn["policy"] == "b0_waterfall"].reset_index(drop=True)
    merged  = pa_test.merge(b0_test, on="transaction_id", suffixes=("_pa", "_b0"))

    total_pa_net = float(merged["net_recovered_amount_pa"].sum())
    total_b0_net = float(merged["net_recovered_amount_b0"].sum())
    total_gap = total_pa_net - total_b0_net
    log(f"3.1  Total gap: Rs.{total_pa_net:,.2f} - Rs.{total_b0_net:,.2f} = Rs.{total_gap:,.2f}")

    same_action = merged[merged["action_pa"] == merged["action_b0"]].copy()
    divergent   = merged[merged["action_pa"] != merged["action_b0"]].copy()
    same_delta  = float((same_action["net_recovered_amount_pa"] - same_action["net_recovered_amount_b0"]).sum())
    same_1_pass = abs(same_delta) < 0.01
    log(f"3.2  SAME-1: |same_delta|={abs(same_delta):.4f} < 0.01 -> {'PASS' if same_1_pass else 'FAIL'}")
    if not same_1_pass:
        log("FATAL: SAME-1 failed — same-action rows do not net to zero, so the "
            "substitution matrix is NOT an exhaustive partition of the gap.")
        raise RuntimeError(f"SAME-1 failed: same_delta={same_delta:.4f}")

    matrix_rows = []
    for (pa_act, b0_act), grp in divergent.groupby(["action_pa", "action_b0"]):
        pa_net = float(grp["net_recovered_amount_pa"].sum())
        b0_net = float(grp["net_recovered_amount_b0"].sum())
        delta  = pa_net - b0_net
        matrix_rows.append({
            "action_pa": pa_act, "action_b0": b0_act, "count": len(grp),
            "pa_net": pa_net, "b0_net": b0_net, "delta": delta,
            "delta_pct": (delta / abs(total_gap) * 100) if abs(total_gap) > 0 else 0.0,
        })

    subst_matrix_df = pd.DataFrame(matrix_rows).sort_values("delta")
    subst_matrix_df.to_csv(os.path.join(ARTIFACTS_DIR, "a5_substitution_matrix.csv"), index=False)

    sum_cell_deltas = float(subst_matrix_df["delta"].sum())
    matrix_residual = total_gap - sum_cell_deltas
    attr_1_pass = abs(matrix_residual) < 0.01
    log(f"3.4  ATTR-1: residual={matrix_residual:.4f} -> {'PASS' if attr_1_pass else 'FAIL'}")

    wc_rows = subst_matrix_df[(subst_matrix_df["action_pa"] == "wait") & (subst_matrix_df["action_b0"] == "close")]
    wc_delta = float(wc_rows["delta"].sum()) if len(wc_rows) > 0 else 0.0
    class_r_wc_ref = -247410.0

    active_actions = {"retry", "payment_link", "reminder", "discount"}
    active_rows = subst_matrix_df[
        subst_matrix_df["action_pa"].isin(active_actions) & subst_matrix_df["action_b0"].isin(active_actions)
    ]
    active_sum = float(active_rows["delta"].sum())
    value_pos_rows = subst_matrix_df[subst_matrix_df["delta"] > 0]
    value_pos_sum  = float(value_pos_rows["delta"].sum())

    attr_rows = []
    for _, r in subst_matrix_df.iterrows():
        attr_rows.append({
            "pa_action": r["action_pa"], "b0_action": r["action_b0"],
            "count": r["count"], "pa_net": r["pa_net"], "b0_net": r["b0_net"],
            "delta": r["delta"], "delta_pct": r["delta_pct"],
            "citation": f"per_transaction_decisions.csv — {r['action_pa']}->{r['action_b0']} divergent set",
            "split": "test", "data_op": "OP-F",
        })
    if not attr_1_pass:
        attr_rows.append({
            "pa_action": "UNEXPLAINED", "b0_action": "RESIDUAL",
            "count": 0, "pa_net": 0.0, "b0_net": 0.0,
            "delta": matrix_residual,
            "delta_pct": (matrix_residual / abs(total_gap) * 100) if abs(total_gap) > 0 else 0.0,
            "citation": "Arithmetic residual: total_gap - sum(cell_deltas)",
            "split": "test", "data_op": "OP-F",
        })

    attr_df = pd.DataFrame(attr_rows)
    attr_df.to_csv(os.path.join(ARTIFACTS_DIR, "a5_attribution.csv"), index=False)

    class_r_dict = {
        "wc_delta_computed": wc_delta, "wc_delta_class_r": class_r_wc_ref,
        "active_sum_computed": active_sum, "active_sum_class_r": -100764.0,
        "value_pos_sum_computed": value_pos_sum, "value_pos_sum_class_r": 150157.08,
    }
    return subst_matrix_df, total_gap, same_1_pass, matrix_residual, attr_1_pass, class_r_dict


# ==============================================================================
# A6 — CALIBRATION
# ==============================================================================
def parse_snapshot_a6_tables():
    """Read the PUBLISHED Phase 2 calibration numbers back out of the preserved
    pre-Phase-3 snapshot.

    Why parse instead of typing them in: the snapshot is the only surviving record of
    the Phase 2 a6 values (the artifact bytes were overwritten in place and never
    committed), and hand-copying 6 standard errors into this file would put exactly the
    kind of unsourced literal into the harness that LIT-1 exists to forbid. Parsing
    keeps the comparison values sourced from a file whose SHA-256 is logged every run.

    Read-only. Never writes to the snapshot. Returns None on any shortfall, in which
    case the probe downgrades itself to NOT RUN rather than guessing.
    """
    if not os.path.isfile(SNAPSHOT_REPORT):
        return None
    try:
        with open(SNAPSHOT_REPORT, encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return None

    known = {"retry", "payment_link", "reminder", "discount", "wait", "close"}

    def num(s):
        return float(s.replace(",", "").replace("+", "").replace("*", "").strip())

    actions = {}
    deciles = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 8:
            continue
        name = cells[0].strip("`* ")
        if name in known:
            try:
                actions[name] = {"n": int(num(cells[1])), "mean_predicted": num(cells[2]),
                                 "realized_rate": num(cells[3]), "signed_gap": num(cells[4]),
                                 "se": num(cells[5]),
                                 "ci_excludes_zero": cells[7].strip("*").upper().startswith("YES")}
            except Exception:
                continue
        elif len(cells) >= 9 and cells[0].isdigit() and len(cells[0]) == 1:
            try:
                deciles.append({"decile": int(cells[0]), "n": int(num(cells[2])),
                                "mean_predicted": num(cells[3]), "se": num(cells[6])})
            except Exception:
                continue

    if len(actions) != 6 or len(deciles) != 10:
        return None
    return {"actions": actions, "deciles": sorted(deciles, key=lambda d: d["decile"])}


def run_a6(val_ht, val_txns, model, val_cache):
    log("=" * 80)
    log("A6 — CALIBRATION WITH UNCERTAINTY (OP-V)")
    log("=" * 80)

    all_actions = ["retry", "payment_link", "reminder", "discount", "wait", "close"]

    preds_data = []
    for _, row in val_ht.iterrows():
        tid = int(row["transaction_id"])
        act = row["action"]
        outcome = int(row["outcome"])
        prob = val_cache[tid]["probs"][act]
        amt = float(val_cache[tid]["ctx"]["amount"])
        is_allowed = (act in val_cache[tid]["allowed"])
        preds_data.append({
            "transaction_id": tid, "action": act, "predicted": prob,
            "realized": outcome, "amount": amt, "is_allowed": is_allowed
        })
    preds_df = pd.DataFrame(preds_data)
    allowed_preds_df = preds_df[preds_df["is_allowed"] == True].copy()

    cal_action_rows = []
    for a in all_actions:
        sub = allowed_preds_df[allowed_preds_df["action"] == a]
        n = len(sub)
        if n == 0:
            cal_action_rows.append({
                "action": a, "n_allowed": 0, "mean_predicted": float("nan"),
                "realized_rate": float("nan"), "signed_gap": float("nan"),
                "se": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"),
                "ci_excludes_zero": False
            })
            continue
        mean_pred = float(sub["predicted"].mean())
        realized  = float(sub["realized"].mean())
        gap = mean_pred - realized
        se  = float(np.sqrt(realized * (1 - realized) / n))
        ci_low  = gap - 1.96 * se
        ci_high = gap + 1.96 * se
        cal_action_rows.append({
            "action": a, "n_allowed": n, "mean_predicted": mean_pred,
            "realized_rate": realized, "signed_gap": gap,
            "se": se, "ci_low": ci_low, "ci_high": ci_high,
            "ci_excludes_zero": (ci_low > 0) or (ci_high < 0)
        })
    cal_action_df = pd.DataFrame(cal_action_rows)
    cal_action_df.to_csv(frozen_guard_path("a6_calibration_actions.csv")[0], index=False)

    # --------------------------------------------------------------------------
    # A6 STANDARD-ERROR CONVENTION PROBE — MEASUREMENT ONLY.
    #
    # This block changes NO published value. cal_action_df above is already written and
    # is not touched here. It exists because the a6 numbers currently on disk disagree
    # with the ones the Phase 2 snapshot published, in two ways that matter:
    #
    #   (1) SIGN. The snapshot reports retry +0.0075 and reminder -0.0200; the current
    #       file reports retry -0.00748 and reminder +0.01999. Same magnitudes, opposite
    #       signs, so one of the two runs computed realized-minus-predicted and the other
    #       predicted-minus-realized. The label "Signed Gap" alone does not say which.
    #   (2) MAGNITUDE OF SE. Snapshot retry SE 0.0188 vs current 0.019899; snapshot
    #       reminder 0.0099 vs current 0.010308. Every current SE is ~5-6% LARGER.
    #
    # Together those two differences flipped reminder's CI from [-0.0393, -0.0007]
    # (excludes zero: YES, the snapshot's only significant per-action calibration
    # finding) to [-0.00021, +0.04020] (NO). The margin is 0.0007 -- so the entire
    # finding turns on which standard error is correct, which is far too narrow a
    # margin to settle by assertion.
    #
    # So the run MEASURES it instead. Three candidate estimators are computed on the
    # same data and each is compared against the SE the snapshot published:
    #
    #   se_realized_single : sqrt(realized*(1-realized)/n)   <- what the current code uses
    #   se_pred_single     : sqrt(mean_pred*(1-mean_pred)/n)
    #   se_poisson_binom   : sqrt(sum_i p_i*(1-p_i))/n       <- Poisson-binomial under H0
    #
    # The third is the estimator that is actually correct for this quantity: the gap is
    # a mean of n independent Bernoulli draws with DIFFERENT success probabilities p_i,
    # so Var = (1/n^2) * sum_i p_i(1-p_i), which by Jensen is <= p_bar(1-p_bar)/n. That
    # inequality predicts the sign of the discrepancy above -- the current SEs should be
    # the larger ones -- but predicting a direction is not proving an identity. If
    # se_poisson_binom reproduces all six published SEs to within rounding, the Phase 2
    # formula is identified and the current one is a regression. If it does not, this
    # hypothesis is wrong and nothing should be changed on the strength of it.
    #
    # NO FORMULA IS SWITCHED HERE. The verdict lands in a6_se_convention_probe.csv for
    # an explicit decision, because changing it would move two published statistical
    # verdicts and that is not a repair this run is authorised to make.
    # --------------------------------------------------------------------------
    snap_a6 = parse_snapshot_a6_tables()
    probe_rows = []
    for _, r in cal_action_df.iterrows():
        a = r["action"]
        sub = allowed_preds_df[allowed_preds_df["action"] == a]
        n = len(sub)
        if n == 0:
            continue
        p = sub["predicted"].to_numpy(dtype=float)
        mean_pred = float(p.mean())
        realized  = float(sub["realized"].mean())
        se_realized_single = float(np.sqrt(realized * (1 - realized) / n))
        se_pred_single     = float(np.sqrt(mean_pred * (1 - mean_pred) / n))
        se_poisson_binom   = float(np.sqrt((p * (1 - p)).sum()) / n)
        snap = (snap_a6 or {}).get("actions", {}).get(a)
        row = {
            "action": a, "n": n,
            "gap_pred_minus_real": mean_pred - realized,
            "gap_real_minus_pred": realized - mean_pred,
            "se_used_in_artifact": float(r["se"]),
            "se_realized_single": se_realized_single,
            "se_pred_single": se_pred_single,
            "se_poisson_binom": se_poisson_binom,
            "snapshot_se": snap["se"] if snap else "",
            "snapshot_signed_gap": snap["signed_gap"] if snap else "",
            "snapshot_ci_excludes_zero": snap["ci_excludes_zero"] if snap else "",
        }
        # Which candidate reproduces the published SE at its printed precision (4dp)?
        if snap:
            tol = 0.00005
            row["matches_realized_single"] = abs(se_realized_single - snap["se"]) <= tol
            row["matches_pred_single"]     = abs(se_pred_single     - snap["se"]) <= tol
            row["matches_poisson_binom"]   = abs(se_poisson_binom   - snap["se"]) <= tol
            # Would the Poisson-binomial SE restore the snapshot's significance verdict?
            g = mean_pred - realized
            row["pb_ci_excludes_zero"] = ((g - 1.96 * se_poisson_binom) > 0) or \
                                         ((g + 1.96 * se_poisson_binom) < 0)
        probe_rows.append(row)

    pd.DataFrame(probe_rows).to_csv(
        os.path.join(ARTIFACTS_DIR, "a6_se_convention_probe.csv"), index=False)

    if snap_a6 is None:
        log("  A6 SE convention probe: NOT RUN (snapshot absent or its calibration "
            "tables did not parse to 6 action rows + 10 decile rows). Candidate SEs "
            "still written to a6_se_convention_probe.csv, without a comparison column.")
    else:
        n_pb = sum(1 for r_ in probe_rows if r_.get("matches_poisson_binom"))
        n_rs = sum(1 for r_ in probe_rows if r_.get("matches_realized_single"))
        n_ps = sum(1 for r_ in probe_rows if r_.get("matches_pred_single"))
        log(f"  A6 SE convention probe (measurement only, no value changed):")
        log(f"    Snapshot SEs reproduced to +/-0.00005 by: "
            f"poisson_binomial {n_pb}/6, realized_single {n_rs}/6, pred_single {n_ps}/6")
        for r_ in probe_rows:
            log(f"      {r_['action']:<13s} snapshot_se={r_['snapshot_se']} "
                f"used={r_['se_used_in_artifact']:.6f} pb={r_['se_poisson_binom']:.6f} "
                f"pb_match={r_.get('matches_poisson_binom')} "
                f"snap_excl0={r_['snapshot_ci_excludes_zero']} "
                f"pb_excl0={r_.get('pb_ci_excludes_zero')}")
        snap_dec_n = [d["n"] for d in snap_a6["deciles"]]
        log(f"    Snapshot decile Ns (reference only; authoritative binning is index-based): {snap_dec_n}")

    reminder_sub = allowed_preds_df[allowed_preds_df["action"] == "reminder"].copy()
    reminder_sub = reminder_sub.sort_values("amount")
    n_deciles = 10
    # AUTHORITATIVE METHODOLOGY: index-based, per explicit instruction 2026-08-26.
    # Deciles are cut on reminder_sub.index, not on the amount column. Because
    # sort_values does not renumber the index, these bins are not quantiles of amount:
    # their amount ranges overlap and each bin holds roughly 126-127 rows. That is the
    # approved methodology and it is what produced the frozen a6_calibration_deciles.csv,
    # so FROZ-1 now checks this file strictly. An amount-based alternative was explored
    # on 2026-08-26 and REJECTED as authoritative; it is implemented nowhere in this
    # file. The preserved snapshot's published decile Ns differ from what this produces;
    # that discrepancy is logged below rather than silently reconciled. Do not change
    # this line without explicit sign-off.
    reminder_sub["decile"] = pd.qcut(reminder_sub.index, q=n_deciles,
                                     labels=False, duplicates="drop")

    cal_decile_rows = []
    n_deciles_excluding_zero = 0
    for d in range(n_deciles):
        dsub = reminder_sub[reminder_sub["decile"] == d]
        if len(dsub) == 0:
            continue
        n = len(dsub)
        mean_pred = float(dsub["predicted"].mean())
        realized  = float(dsub["realized"].mean())
        gap = mean_pred - realized
        se  = float(np.sqrt(realized * (1 - realized) / n)) if 0 < realized < 1 else 0.0
        ci_low  = gap - 1.96 * se
        ci_high = gap + 1.96 * se
        ci_excl = (ci_low > 0) or (ci_high < 0)
        if ci_excl:
            n_deciles_excluding_zero += 1
        cal_decile_rows.append({
            "decile": d, "amount_min": float(dsub["amount"].min()), "amount_max": float(dsub["amount"].max()),
            "n": n, "mean_predicted": mean_pred, "realized_rate": realized,
            "signed_gap": gap, "se": se, "ci_low": ci_low, "ci_high": ci_high,
            "ci_excludes_zero": ci_excl
        })
    cal_decile_df = pd.DataFrame(cal_decile_rows)
    cal_decile_df.to_csv(frozen_guard_path("a6_calibration_deciles.csv")[0], index=False)

    # DECILE BINNING DIAGNOSTIC — descriptive only. It asserts nothing and gates nothing.
    # Under the authoritative index-based methodology the amount ranges are EXPECTED to
    # overlap, so a False below is normal and is not a defect. Both quantities are logged
    # so that the binning actually used is recoverable from run_log.txt, and so that the
    # difference against the preserved snapshot's published decile Ns stays visible
    # instead of being dropped.
    _mins = [r_["amount_min"] for r_ in cal_decile_rows]
    _maxs = [r_["amount_max"] for r_ in cal_decile_rows]
    decile_monotone = all(_mins[i + 1] >= _maxs[i] for i in range(len(cal_decile_rows) - 1))
    decile_n_list = [r_["n"] for r_ in cal_decile_rows]
    log(f"  A6 decile binning: bins ordered and non-overlapping = {decile_monotone}")
    log(f"    computed decile Ns: {decile_n_list}")
    if snap_a6 is not None:
        _snap_n = [d["n"] for d in snap_a6["deciles"]]
        log(f"    snapshot decile Ns: {_snap_n}  ->  "
            f"{'MATCH' if _snap_n == decile_n_list else 'DIFFER'}")

    reminder_rows = allowed_preds_df[allowed_preds_df["action"] == "reminder"]
    competitors = ["retry", "payment_link", "discount", "wait", "close"]
    rel_bias_rows = []
    for comp in competitors:
        comp_rows = allowed_preds_df[allowed_preds_df["action"] == comp]
        dual_tids = set(reminder_rows["transaction_id"]) & set(comp_rows["transaction_id"])
        if not dual_tids:
            continue
        n = len(dual_tids)
        rem_dual  = reminder_rows[reminder_rows["transaction_id"].isin(dual_tids)]
        comp_dual = comp_rows[comp_rows["transaction_id"].isin(dual_tids)]
        rem_avg  = float(rem_dual["predicted"].mean())
        comp_avg = float(comp_dual["predicted"].mean())
        relative_bias = rem_avg - comp_avg
        comp_preds = comp_dual.set_index("transaction_id")["predicted"]
        n_rem_win = int((rem_dual.set_index("transaction_id")["predicted"] > comp_preds + 1e-9).sum())
        se  = float(np.sqrt(abs(relative_bias) * (1 - abs(relative_bias)) / n)) if 0 < abs(relative_bias) < 1 else 0.01
        ci_low  = relative_bias - 1.96 * se
        ci_high = relative_bias + 1.96 * se
        rel_bias_rows.append({
            "pair": f"reminder_vs_{comp}",
            "reminder_avg_pred": rem_avg, "competitor_avg_pred": comp_avg,
            "relative_bias": relative_bias, "se": se, "ci_low": ci_low, "ci_high": ci_high,
            "ci_excludes_zero": (ci_low > 0) or (ci_high < 0),
            "dual_allowed_count": n, "vulnerable_count": n_rem_win,
            "vulnerable_share": n_rem_win / n * 100 if n > 0 else 0.0
        })
    rel_bias_df = pd.DataFrame(rel_bias_rows)
    rel_bias_df.to_csv(frozen_guard_path("a6_relative_bias.csv")[0], index=False)

    return cal_action_df, cal_decile_df, rel_bias_df, n_deciles_excluding_zero


# ==============================================================================
# A8 — CARRY-FORWARD FIGURES
# ==============================================================================
def run_a8(val_txns, test_txns, val_cache, val_outcome_lookup):
    log("=" * 80)
    log("A8 — CARRY-FORWARD FIGURES")
    log("=" * 80)

    dp = DEFAULT_DISCOUNT_PERCENT
    val_orc_decisions = []
    for tid, data in val_cache.items():
        ctx  = data["ctx"]
        amt  = ctx["amount"]
        allowed = data["allowed"]
        esc  = data["esc"]
        terminal = data["terminal"]
        orc_act, _, _ = select_b6_oracle(allowed, esc, terminal, tid, amt, val_outcome_lookup)
        orc_out = val_outcome_lookup.get((tid, orc_act), 0) if orc_act not in ("escalate", "no_action_required") else 0
        val_orc_decisions.append(score_action(orc_act, orc_out, amt, dp))
    val_orc_df  = pd.DataFrame(val_orc_decisions)
    val_orc_net = float(val_orc_df["net_recovered_amount"].sum())
    val_orc_per = val_orc_net / len(val_txns)

    val_max_amt  = float(val_txns["amount"].max())
    test_max_amt = float(test_txns["amount"].max())
    val_top1_cut  = float(val_txns["amount"].quantile(0.99))
    test_top1_cut = float(test_txns["amount"].quantile(0.99))
    val_top1_share  = float(val_txns[val_txns["amount"]  >= val_top1_cut]["amount"].sum()  / val_txns["amount"].sum()  * 100)
    test_top1_share = float(test_txns[test_txns["amount"] >= test_top1_cut]["amount"].sum() / test_txns["amount"].sum() * 100)

    pr_df = pd.read_csv(os.path.join(ARTIFACTS_DIR, "a2_policy_rows.csv"))

    def _get(policy, split, col):
        rows = pr_df[(pr_df["policy"] == policy) & (pr_df["split"] == split)]
        return float(rows[col].iloc[0]) if len(rows) > 0 else float("nan")

    pa_val_net   = _get("policy_a",   "val",  "net_amount")
    b0_val_net   = _get("b0_waterfall","val",  "net_amount")
    pa_test_net  = _get("policy_a",   "test", "net_amount")
    b0_test_net  = _get("b0_waterfall","test", "net_amount")
    b6_test_net  = _get("b6_oracle",  "test", "net_amount")
    pa_val_n     = int(_get("policy_a","val",  "n_transactions"))
    pa_test_n    = int(_get("policy_a","test", "n_transactions"))

    pa_npt_val   = pa_val_net  / pa_val_n  if pa_val_n  > 0 else float("nan")
    pa_npt_test  = pa_test_net / pa_test_n if pa_test_n > 0 else float("nan")
    b0_npt_val   = b0_val_net  / pa_val_n  if pa_val_n  > 0 else float("nan")
    b0_npt_test  = b0_test_net / pa_test_n if pa_test_n > 0 else float("nan")
    orc_npt_test = b6_test_net / pa_test_n if pa_test_n > 0 else float("nan")

    gap_val  = pa_val_net  - b0_val_net
    gap_test = pa_test_net - b0_test_net
    gap_swing = gap_val - gap_test

    pa_pct_change  = (pa_npt_test  - pa_npt_val)  / pa_npt_val  * 100
    b0_pct_change  = (b0_npt_test  - b0_npt_val)  / b0_npt_val  * 100

    a8_artifact = {
        "cross_split_stability": {
            "val_n": pa_val_n, "test_n": pa_test_n,
            "pa_net_per_txn_val": pa_npt_val, "pa_net_per_txn_test": pa_npt_test, "pa_pct_change": pa_pct_change,
            "b0_net_per_txn_val": b0_npt_val, "b0_net_per_txn_test": b0_npt_test, "b0_pct_change": b0_pct_change,
            "gap_val": gap_val, "gap_test": gap_test, "gap_swing": gap_swing,
            "test_bootstrap_ci_low":  -776313.86,
            "test_bootstrap_ci_high":  332562.45,
            "test_bootstrap_ci_width": 1108876.31,
            "oracle_net_val": val_orc_net, "oracle_net_per_txn_val": val_orc_per,
            "oracle_net_test": b6_test_net, "oracle_net_per_txn_test": orc_npt_test,
            "val_max_amount": val_max_amt, "test_max_amount": test_max_amt,
            "val_top1_value_share": val_top1_share, "test_top1_value_share": test_top1_share,
        },
        "cross_action_ranking": {
            "concordance": 0.6223, "ci_low": 0.6071, "ci_high": 0.6376, "se": 0.0078, "z_score": 15.68,
            "val_wt_concordance": 0.6468,
            "oracle_agreement_m4": 23.1, "oracle_agreement_b0": 12.1,
            "oracle_agreement_m4_top_decile": 44.4, "oracle_agreement_b0_top_decile": 8.3,
            "provenance": "Class R REFERENCE — computed in prior Phase 2 diagnostic run (draft 2); not recomputed in Phase 3."
        },
        "frozen_test_result": {
            "pa_net": pa_test_net, "b0_net": b0_test_net, "diff": gap_test,
            "ci": [-776313.86, 332562.45],
            "b1_random_net": _get("b1_random", "test", "net_amount"),
            "oracle_net": b6_test_net
        }
    }
    with open(os.path.join(ARTIFACTS_DIR, "a8_carry_forward.json"), "w") as f:
        json.dump(a8_artifact, f, indent=2)

    log(f"A8: oracle_val_net=Rs.{val_orc_net:,.2f}, oracle_test_net=Rs.{b6_test_net:,.2f}")
    return a8_artifact


# ==============================================================================
# TASK 0 — FIGURES REGISTRY
# ==============================================================================
def build_figures_registry(artifacts_dir):
    F = {}

    def entry(key, value, fmt, source_file, source_field, split="", data_op=""):
        F[key] = {"value": value, "fmt": fmt, "source_file": source_file,
                  "source_field": source_field, "split": split, "data_op": data_op}

    # A0
    a0 = json.load(open(os.path.join(artifacts_dir, "a0_feature_audit.json")))
    n_val = sum(a0["allowed_counts"].values()) // 6  # approximate; use actual txn count
    # Use distinct allowed_counts["wait"] as a proxy for val_n (all have same n)
    # Actually n_val is the number of val transactions; recover from a1 artifact
    a1_j = json.load(open(os.path.join(artifacts_dir, "a1_close_wait.json")))
    n_val = a1_j["n_validation"]

    entry("a0_feature_count",      a0["feature_count"],           "{:d}",    "a0_feature_audit.json", "feature_count", "val", "OP-V")
    entry("a0_distinct_orderings", a0["distinct_full_orderings"], "{:d}",    "a0_feature_audit.json", "distinct_full_orderings", "val", "OP-V")
    entry("a0_val_n",              n_val,                          "{:,d}",   "a1_close_wait.json", "n_validation", "val", "OP-V")
    entry("a0_val_amt_min",        a0["val_amount_min"],           "{:,.2f}", "a0_feature_audit.json", "val_amount_min", "val", "OP-V")
    entry("a0_val_amt_max",        a0["val_amount_max"],           "{:,.2f}", "a0_feature_audit.json", "val_amount_max", "val", "OP-V")

    for i, ord_entry in enumerate(a0["top_orderings"][:5]):
        cnt = ord_entry["count"]
        entry(f"a0_ord{i+1}_count", cnt, "{:d}",   "a0_feature_audit.json", f"top_orderings[{i}].count", "val", "OP-V")
        entry(f"a0_ord{i+1}_pct",   cnt / n_val * 100, "{:.1f}", "a0_feature_audit.json", f"top_orderings[{i}].count/n_val", "val", "OP-V")

    for act, cnt in a0["allowed_counts"].items():
        entry(f"a0_allowed_{act}",  cnt, "{:,d}", "a0_feature_audit.json", f"allowed_counts.{act}", "val", "OP-V")
    for act, cnt in a0["actual_selections"].items():
        entry(f"a0_selected_{act}", cnt, "{:,d}", "a0_feature_audit.json", f"actual_selections.{act}", "val", "OP-V")

    pair_ord = pd.read_csv(os.path.join(artifacts_dir, "a0_pair_orderings.csv"))
    def _pr(pair_name): return pair_ord[pair_ord["pair"] == pair_name].iloc[0]

    wc = _pr("wait_vs_close")
    entry("a0_wait_gt_close",      int(wc["a_gt_b_count"]),                  "{:,d}",  "a0_pair_orderings.csv", "wait_vs_close.a_gt_b_count", "val", "OP-V")
    entry("a0_close_gt_wait",      int(wc["b_gt_a_count"]),                  "{:,d}",  "a0_pair_orderings.csv", "wait_vs_close.b_gt_a_count", "val", "OP-V")
    entry("a0_wc_tie",             int(wc["tie_count"]),                      "{:d}",   "a0_pair_orderings.csv", "wait_vs_close.tie_count", "val", "OP-V")
    entry("a0_wait_gt_close_pct",  int(wc["a_gt_b_count"]) / n_val * 100,   "{:.1f}", "a0_pair_orderings.csv", "wait_vs_close.a_gt_b_count/n_val", "val", "OP-V")
    entry("a0_close_gt_wait_pct",  int(wc["b_gt_a_count"]) / n_val * 100,   "{:.1f}", "a0_pair_orderings.csv", "wait_vs_close.b_gt_a_count/n_val", "val", "OP-V")
    entry("a0_wc_min_diff",        float(wc["min_abs_diff"]),                 "{:.4f}", "a0_pair_orderings.csv", "wait_vs_close.min_abs_diff", "val", "OP-V")
    entry("a0_wc_med_diff",        float(wc["median_abs_diff"]),              "{:.4f}", "a0_pair_orderings.csv", "wait_vs_close.median_abs_diff", "val", "OP-V")
    entry("a0_wc_max_diff",        float(wc["max_abs_diff"]),                 "{:.4f}", "a0_pair_orderings.csv", "wait_vs_close.max_abs_diff", "val", "OP-V")

    rd = _pr("retry_vs_discount")
    entry("a0_retry_gt_disc",      int(rd["a_gt_b_count"]),                  "{:,d}",  "a0_pair_orderings.csv", "retry_vs_discount.a_gt_b_count", "val", "OP-V")
    entry("a0_disc_gt_retry",      int(rd["b_gt_a_count"]),                  "{:,d}",  "a0_pair_orderings.csv", "retry_vs_discount.b_gt_a_count", "val", "OP-V")
    entry("a0_retry_gt_disc_pct",  int(rd["a_gt_b_count"]) / n_val * 100,   "{:.1f}", "a0_pair_orderings.csv", "retry_vs_discount.a_gt_b_count/n_val", "val", "OP-V")
    entry("a0_disc_gt_retry_pct",  int(rd["b_gt_a_count"]) / n_val * 100,   "{:.1f}", "a0_pair_orderings.csv", "retry_vs_discount.b_gt_a_count/n_val", "val", "OP-V")

    pl = _pr("payment_link_vs_reminder")
    entry("a0_pl_gt_rem",          int(pl["a_gt_b_count"]),                  "{:,d}",  "a0_pair_orderings.csv", "payment_link_vs_reminder.a_gt_b_count", "val", "OP-V")
    entry("a0_rem_gt_pl",          int(pl["b_gt_a_count"]),                  "{:,d}",  "a0_pair_orderings.csv", "payment_link_vs_reminder.b_gt_a_count", "val", "OP-V")
    entry("a0_pl_gt_rem_pct",      int(pl["a_gt_b_count"]) / n_val * 100,   "{:.1f}", "a0_pair_orderings.csv", "payment_link_vs_reminder.a_gt_b_count/n_val", "val", "OP-V")
    entry("a0_rem_gt_pl_pct",      int(pl["b_gt_a_count"]) / n_val * 100,   "{:.1f}", "a0_pair_orderings.csv", "payment_link_vs_reminder.b_gt_a_count/n_val", "val", "OP-V")

    # A1
    n_v = a1_j["n_validation"]
    entry("a1_val_n",              a1_j["n_validation"],                       "{:,d}",  "a1_close_wait.json", "n_validation", "val", "OP-V")
    entry("a1_close_gt_wait",      a1_j["p_close_gt_wait_count"],              "{:d}",   "a1_close_wait.json", "p_close_gt_wait_count", "val", "OP-V")
    entry("a1_wait_gt_close",      a1_j["p_wait_gt_close_count"],              "{:d}",   "a1_close_wait.json", "p_wait_gt_close_count", "val", "OP-V")
    entry("a1_equal_count",        a1_j["p_equal_count"],                      "{:d}",   "a1_close_wait.json", "p_equal_count", "val", "OP-V")
    entry("a1_close_gt_wait_pct",  a1_j["p_close_gt_wait_count"] / n_v * 100, "{:.2f}", "a1_close_wait.json", "p_close_gt_wait_count/n_val", "val", "OP-V")
    entry("a1_wait_gt_close_pct",  a1_j["p_wait_gt_close_count"] / n_v * 100, "{:.2f}", "a1_close_wait.json", "p_wait_gt_close_count/n_val", "val", "OP-V")
    entry("a1_equal_pct",          a1_j["p_equal_count"] / n_v * 100,         "{:.2f}", "a1_close_wait.json", "p_equal_count/n_val", "val", "OP-V")
    entry("a1_flips_count",        a1_j["flips_count"],                        "{:d}",   "a1_close_wait.json", "flips_count", "val", "OP-V")
    entry("a1_standard_net",       a1_j["standard_net"],                       "{:,.2f}","a1_close_wait.json", "standard_net", "val", "OP-V")
    entry("a1_corrected_net",      a1_j["corrected_net"],                      "{:,.2f}","a1_close_wait.json", "corrected_net", "val", "OP-V")
    entry("a1_delta_net",          abs(a1_j["delta_net"]),                     "{:.2f}", "a1_close_wait.json", "abs(delta_net)", "val", "OP-V")

    # A2 policy rows
    pr = pd.read_csv(os.path.join(artifacts_dir, "a2_policy_rows.csv"))
    def _prf(policy, split, col):
        rows = pr[(pr["policy"] == policy) & (pr["split"] == split)]
        return float(rows[col].iloc[0]) if len(rows) > 0 else float("nan")
    def _pri(policy, split, col): return int(_prf(policy, split, col))

    pol_map = [("pa","policy_a","val","OP-V"), ("b0","b0_waterfall","val","OP-V"),
               ("pa","policy_a","test","OP-F"), ("b0","b0_waterfall","test","OP-F"),
               ("b1","b1_random","test","OP-F"), ("b6","b6_oracle","test","OP-F")]

    for pol_key, pol_name, sp_name, dop in pol_map:
        pfx = f"a2_{pol_key}_{sp_name}"
        for col, fmtstr, sfx in [
            ("n_transactions",  "{:,d}",  "n"),
            ("recovered_count", "{:d}",   "rec_count"),
            ("recovery_rate",   "{:.2f}", "rec_rate"),
            ("gross_amount",    "{:,.2f}","gross"),
            ("intervention_cost","{:,.2f}","cost"),
            ("discount_haircut","{:,.2f}","discount"),
            ("net_amount",      "{:,.2f}","net"),
            ("net_per_txn",     "{:.2f}", "net_per_txn"),
        ]:
            v = _prf(pol_name, sp_name, col)
            entry(f"{pfx}_{sfx}", int(v) if sfx in ("n","rec_count") else v,
                  fmtstr, "a2_policy_rows.csv", f"{pol_name}.{sp_name}.{col}", sp_name, dop)

    # A3
    pbar = pd.read_csv(os.path.join(artifacts_dir, "a3_pbar.csv"))
    for _, r in pbar.iterrows():
        act = r["action"]
        entry(f"a3_pbar_{act}", float(r["pbar_allowed"]), "{:.4f}", "a3_pbar.csv", f"{act}.pbar_allowed", "val", "OP-V")
        entry(f"a3_n_{act}",    int(r["n_allowed"]),      "{:,d}",  "a3_pbar.csv", f"{act}.n_allowed", "val", "OP-V")

    sweep = pd.read_csv(os.path.join(artifacts_dir, "a3_lambda_sweep.csv"))
    lam_labels = {0.0: "lam0", 0.25: "lam25", 0.5: "lam50", 0.75: "lam75", 1.0: "lam100"}
    for _, r in sweep.iterrows():
        lk = lam_labels.get(r["lambda"], f"lam{r['lambda']}")
        entry(f"a3_{lk}_net",   float(r["net_recovered_amount"]),"{:,.2f}",  "a3_lambda_sweep.csv", f"{lk}.net_recovered_amount", "val", "OP-V")
        entry(f"a3_{lk}_prior", float(r["prior_class_r_net"]),   "{:,.2f}",  "a3_lambda_sweep.csv", f"{lk}.prior_class_r_net", "val", "OP-V")
        entry(f"a3_{lk}_delta", float(r["delta_from_prior"]),    "{:+,.2f}", "a3_lambda_sweep.csv", f"{lk}.delta_from_prior", "val", "OP-V")
        entry(f"a3_{lk}_count", int(r["recovered_count"]),       "{:d}",     "a3_lambda_sweep.csv", f"{lk}.recovered_count", "val", "OP-V")
        entry(f"a3_{lk}_rate",  float(r["recovery_rate"]),       "{:.2f}",   "a3_lambda_sweep.csv", f"{lk}.recovery_rate", "val", "OP-V")

    harness = json.load(open(os.path.join(artifacts_dir, "a3_harness_baseline.json")))
    entry("a3_live_baseline_net", harness["live_class_h_validation_net"], "{:,.2f}", "a3_harness_baseline.json", "live_class_h_validation_net", "val", "OP-V")

    lam0_net = float(sweep[sweep["lambda"] == 0.0]["net_recovered_amount"].iloc[0])
    lam1_net = float(sweep[sweep["lambda"] == 1.0]["net_recovered_amount"].iloc[0])
    gain_abs = lam1_net - lam0_net
    gain_pct = (gain_abs / lam0_net * 100) if lam0_net != 0 else 0.0
    entry("a3_shrinkage_gain_abs", gain_abs, "{:,.2f}", "a3_lambda_sweep.csv", "lam1.net - lam0.net", "val", "OP-V")
    entry("a3_shrinkage_gain_pct", gain_pct, "{:.1f}",  "a3_lambda_sweep.csv", "(lam1.net-lam0.net)/lam0.net*100", "val", "OP-V")

    # A4
    a4s = json.load(open(os.path.join(artifacts_dir, "a4_partition_summary.json")))
    entry("a4_derived_count",       a4s["derived_count"],          "{:d}",    "a4_partition_summary.json", "derived_count", "test", "OP-F")
    entry("a4_derived_net_diff",    abs(a4s["derived_net_diff"]),  "{:,.2f}", "a4_partition_summary.json", "abs(derived_net_diff)", "test", "OP-F")
    entry("a4_close_only_n",        a4s["close_only_n"],           "{:d}",    "a4_partition_summary.json", "close_only_n", "test", "OP-F")
    entry("a4_close_only_total",    a4s["close_only_total"],       "{:,.2f}", "a4_partition_summary.json", "close_only_total", "test", "OP-F")
    entry("a4_wait_only_n",         a4s["wait_only_n"],            "{:d}",    "a4_partition_summary.json", "wait_only_n", "test", "OP-F")
    entry("a4_wait_only_total",     a4s["wait_only_total"],        "{:,.2f}", "a4_partition_summary.json", "wait_only_total", "test", "OP-F")
    entry("a4_both_n",              a4s["both_n"],                 "{:d}",    "a4_partition_summary.json", "both_n", "test", "OP-F")
    entry("a4_both_total",          a4s["both_total"],             "{:,.2f}", "a4_partition_summary.json", "both_total", "test", "OP-F")
    entry("a4_neither_n",           a4s["neither_n"],              "{:d}",    "a4_partition_summary.json", "neither_n", "test", "OP-F")
    entry("a4_neither_total",       a4s["neither_total"],          "{:,.2f}", "a4_partition_summary.json", "neither_total", "test", "OP-F")
    entry("a4_close_rec_n",         a4s["close_recovered_n"],      "{:d}",    "a4_partition_summary.json", "close_recovered_n", "test", "OP-F")
    entry("a4_close_rec_total",     a4s["close_recovered_total"],  "{:,.2f}", "a4_partition_summary.json", "close_recovered_total", "test", "OP-F")
    entry("a4_wait_rec_n",          a4s["wait_recovered_n"],       "{:d}",    "a4_partition_summary.json", "wait_recovered_n", "test", "OP-F")
    entry("a4_wait_rec_total",      a4s["wait_recovered_total"],   "{:,.2f}", "a4_partition_summary.json", "wait_recovered_total", "test", "OP-F")
    entry("a4_top3_close_sum",      a4s["top3_close_only_sum"],    "{:,.2f}", "a4_partition_summary.json", "top3_close_only_sum", "test", "OP-F")
    # DENOMINATOR 1 of 2 — share of the wait->close SUBSET gap (Rs.247,409.56) = 133.3%.
    # Read straight from the frozen artifact, whose key name is legacy/mislabelled.
    entry("a4_top3_pct_of_waitclose_subset_gap", a4s["top3_pct_of_test_gap"], "{:.1f}",
          "a4_partition_summary.json", "top3_close_only_sum/abs(derived_net_diff)*100", "test", "OP-F")
    n_d = a4s["derived_count"]
    entry("a4_close_rec_rate",      a4s["close_recovered_n"] / n_d * 100, "{:.1f}", "a4_partition_summary.json", "close_rec_n/derived_count*100", "test", "OP-F")
    entry("a4_wait_rec_rate",       a4s["wait_recovered_n"]  / n_d * 100, "{:.1f}", "a4_partition_summary.json", "wait_rec_n/derived_count*100", "test", "OP-F")

    part_rows = pd.read_csv(os.path.join(artifacts_dir, "a4_partition_rows.csv"))
    top3 = part_rows[part_rows["category"] == "CLOSE_ONLY"].sort_values("amount", ascending=False).head(3)
    for i, (_, tr) in enumerate(top3.iterrows()):
        entry(f"a4_top3_txn{i+1}_id",  int(tr["transaction_id"]), "{:d}",    "a4_partition_rows.csv", f"top3_close_only[{i}].transaction_id", "test", "OP-F")
        entry(f"a4_top3_txn{i+1}_amt", float(tr["amount"]),       "{:,.2f}", "a4_partition_rows.csv", f"top3_close_only[{i}].amount", "test", "OP-F")

    wc_gap = abs(a4s["derived_net_diff"])

    if a4s.get("both_transaction_ids"):
        entry("a4_both_txn_id", a4s["both_transaction_ids"][0], "{:d}", "a4_partition_summary.json", "both_transaction_ids[0]", "test", "OP-F")

    # A5
    subst = pd.read_csv(os.path.join(artifacts_dir, "a5_substitution_matrix.csv"))
    total_gap_a5 = float(subst["delta"].sum())
    entry("a5_total_gap",     abs(total_gap_a5),         "{:,.2f}", "a5_substitution_matrix.csv", "abs(sum(delta))", "test", "OP-F")
    entry("a5_total_gap_raw", total_gap_a5,              "{:,.2f}", "a5_substitution_matrix.csv", "sum(delta)", "test", "OP-F")
    entry("a5_n_cells",       len(subst),                "{:d}",    "a5_substitution_matrix.csv", "nrows", "test", "OP-F")
    entry("a5_divergent_n",   int(subst["count"].sum()), "{:,d}",   "a5_substitution_matrix.csv", "sum(count)", "test", "OP-F")

    # DENOMINATOR 2 of 2 — share of the TOTAL test deficit (Rs.198,016.92) = 166.5%.
    # Registered here rather than beside the other a4_* keys because the total gap
    # only becomes available once the A5 substitution matrix has been summed. Both
    # this figure and a4_top3_pct_of_waitclose_subset_gap are correct against their
    # own denominator; they are NOT expected to be equal, and X4 checks each
    # separately. The pre-Phase-3 report published both (snapshot line 163).
    entry("a4_top3_pct_of_total_test_gap",
          (a4s["top3_close_only_sum"] / abs(total_gap_a5) * 100) if total_gap_a5 != 0 else 0.0,
          "{:.1f}", "a4_partition_summary.json + a5_substitution_matrix.csv",
          "top3_close_only_sum/abs(sum(delta))*100", "test", "OP-F")

    wc_s = subst[(subst["action_pa"] == "wait") & (subst["action_b0"] == "close")]
    if len(wc_s) > 0:
        entry("a5_wc_delta",  float(wc_s["delta"].iloc[0]),   "{:,.2f}", "a5_substitution_matrix.csv", "wait->close.delta", "test", "OP-F")
        entry("a5_wc_pa_net", float(wc_s["pa_net"].iloc[0]), "{:,.2f}", "a5_substitution_matrix.csv", "wait->close.pa_net", "test", "OP-F")
        entry("a5_wc_b0_net", float(wc_s["b0_net"].iloc[0]), "{:,.2f}", "a5_substitution_matrix.csv", "wait->close.b0_net", "test", "OP-F")
        entry("a5_wc_count",  int(wc_s["count"].iloc[0]),     "{:d}",   "a5_substitution_matrix.csv", "wait->close.count", "test", "OP-F")

    # A8
    a8 = json.load(open(os.path.join(artifacts_dir, "a8_carry_forward.json")))
    css = a8["cross_split_stability"]
    a8_map = [
        ("a8_val_n",              css["val_n"],                   "{:,d}",  "val", "OP-V"),
        ("a8_test_n",             css["test_n"],                  "{:,d}",  "test","OP-F"),
        ("a8_pa_net_per_txn_val", css["pa_net_per_txn_val"],      "{:.2f}", "val", "OP-V"),
        ("a8_pa_net_per_txn_test",css["pa_net_per_txn_test"],     "{:.2f}", "test","OP-F"),
        ("a8_pa_pct_change",      css["pa_pct_change"],           "{:+.1f}","",    ""),
        ("a8_b0_net_per_txn_val", css["b0_net_per_txn_val"],      "{:.2f}", "val", "OP-V"),
        ("a8_b0_net_per_txn_test",css["b0_net_per_txn_test"],     "{:.2f}", "test","OP-F"),
        ("a8_b0_pct_change",      css["b0_pct_change"],           "{:+.1f}","",    ""),
        ("a8_gap_val",            css["gap_val"],                 "{:,.2f}","val", "OP-V"),
        ("a8_gap_test",           abs(css["gap_test"]),           "{:,.2f}","test","OP-F"),
        ("a8_gap_swing",          abs(css["gap_swing"]),          "{:,.2f}","",    ""),
        ("a8_bs_ci_low",          css["test_bootstrap_ci_low"],   "{:,.2f}","test","OP-F"),
        ("a8_bs_ci_high",         css["test_bootstrap_ci_high"],  "{:,.2f}","test","OP-F"),
        ("a8_bs_ci_width",        css["test_bootstrap_ci_width"], "{:,.2f}","test","OP-F"),
        ("a8_oracle_net_val",     css["oracle_net_val"],          "{:,.2f}","val", "OP-V"),
        ("a8_oracle_per_txn_val", css["oracle_net_per_txn_val"],  "{:.2f}", "val", "OP-V"),
        ("a8_oracle_net_test",    css["oracle_net_test"],         "{:,.2f}","test","OP-F"),
        ("a8_oracle_net_per_txn_test", css["oracle_net_per_txn_test"], "{:.2f}", "test","OP-F"),
        ("a8_val_max_amt",        css["val_max_amount"],          "{:,.2f}","val", "OP-V"),
        ("a8_test_max_amt",       css["test_max_amount"],         "{:,.2f}","test","OP-F"),
        ("a8_val_top1_share",     css["val_top1_value_share"],    "{:.1f}", "val", "OP-V"),
        ("a8_test_top1_share",    css["test_top1_value_share"],   "{:.1f}", "test","OP-F"),
    ]
    for key, val, fmtstr, sp, dop in a8_map:
        entry(key, val, fmtstr, "a8_carry_forward.json", key.replace("a8_",""), sp, dop)

    # Policy-level nets from a2 (for cross-split table)
    for pol_key, pol_name, sp_name, dop in [
        ("pa_val",  "policy_a",   "val",  "OP-V"), ("b0_val",  "b0_waterfall","val",  "OP-V"),
        ("pa_test", "policy_a",   "test", "OP-F"), ("b0_test", "b0_waterfall","test", "OP-F"),
        ("b6_test", "b6_oracle",  "test", "OP-F"),
    ]:
        v = _prf(pol_name, sp_name, "net_amount")
        if v == v:  # not nan
            entry(f"a2_{pol_key}_net_full", v, "{:,.2f}", "a2_policy_rows.csv", f"{pol_name}.{sp_name}.net_amount", sp_name, dop)

    # Write registry CSV
    pd.DataFrame([{"key": k, "value": v["value"], "fmt": v["fmt"],
                   "source_file": v["source_file"], "source_field": v["source_field"],
                   "split": v["split"], "data_op": v["data_op"]} for k, v in F.items()]).to_csv(
        os.path.join(artifacts_dir, "figures_registry.csv"), index=False)

    log(f"FIGURES registry: {len(F)} entries.")
    return F


def render(key, F):
    e = F[key]
    return e["fmt"].format(e["value"])


# ==============================================================================
# TASK 1 — XREF-1
# ==============================================================================
def run_xref1(F, subst_matrix_df, total_gap_a5, raise_on_fail=True):
    failures = []
    log_lines = []
    checks = []

    def chk(xid, lhs_label, lhs_val, rhs_label, rhs_val, tol=0.01, is_count=False):
        if is_count:
            diff = abs(int(lhs_val) - int(rhs_val))
            ok = (diff == 0)
            diff_s = str(diff)
        else:
            diff = abs(float(lhs_val) - float(rhs_val))
            ok = (diff <= tol)
            diff_s = f"{diff:.4f}"
        line = (f"  {xid}: {lhs_label}={lhs_val} vs {rhs_label}={rhs_val} "
                f"| diff={diff_s} | {'PASS' if ok else 'FAIL'}")
        log_lines.append(line)
        checks.append((xid, ok))
        if not ok:
            failures.append((xid, line))
        return ok

    wc = subst_matrix_df[(subst_matrix_df["action_pa"] == "wait") & (subst_matrix_df["action_b0"] == "close")]
    mx_wc_cnt = int(wc["count"].sum()) if len(wc) > 0 else 0
    chk("X1", "A4.derived_count", F["a4_derived_count"]["value"], "matrix.wait->close.count", mx_wc_cnt, is_count=True)

    a4_ndiff_signed = -abs(F["a4_derived_net_diff"]["value"])
    mx_wc_delta = float(wc["delta"].sum()) if len(wc) > 0 else 0.0
    chk("X2", "A4.net_diff(signed)", a4_ndiff_signed, "matrix.wc.delta", mx_wc_delta)

    a2_pa  = F["a2_pa_test_net"]["value"]
    a2_b0  = F["a2_b0_test_net"]["value"]
    chk("X3", "A2.pa_test_net - A2.b0_test_net", a2_pa - a2_b0, "A5.total_gap_raw", total_gap_a5)

    # X4 — TWO independent identities, one per denominator. The old single X4
    # compared the top-3 share of the TOTAL test gap (166.5%) against the figure
    # holding the share of the wait->close SUBSET gap (133.3%) and necessarily
    # failed by 33.24pp. Both quantities are correct; they answer different
    # questions. Each is now validated against the denominator it actually uses,
    # and neither is required to equal the other.
    a4_top3 = F["a4_top3_close_sum"]["value"]

    # X4a: share of the TOTAL test deficit. 329,675.72 / 198,016.92 * 100 = 166.5%
    deriv_pct_total = (a4_top3 / abs(total_gap_a5) * 100) if abs(total_gap_a5) > 0 else 0.0
    chk("X4a", "top3_sum/|total_test_gap|*100", deriv_pct_total,
        "FIGURES.a4_top3_pct_of_total_test_gap",
        F["a4_top3_pct_of_total_test_gap"]["value"], tol=0.2)

    # X4b: share of the wait->close SUBSET gap. 329,675.72 / 247,409.56 * 100 = 133.3%
    deriv_pct_subset = (a4_top3 / abs(mx_wc_delta) * 100) if abs(mx_wc_delta) > 0 else 0.0
    chk("X4b", "top3_sum/|waitclose_subset_gap|*100", deriv_pct_subset,
        "FIGURES.a4_top3_pct_of_waitclose_subset_gap",
        F["a4_top3_pct_of_waitclose_subset_gap"]["value"], tol=0.2)

    # X4c: the two denominators must genuinely differ, otherwise X4a and X4b would
    # be the same check twice and the split would be vacuous. The separation is
    # asserted against an INDEPENDENTLY sourced route to the same quantity (A4's
    # own net diff and A2's policy nets) rather than against a typed constant, so
    # nothing in this check is hand-entered.
    sep_via_matrix = abs(mx_wc_delta) - abs(total_gap_a5)
    sep_via_a4_a2  = abs(F["a4_derived_net_diff"]["value"]) - abs(a2_pa - a2_b0)
    chk("X4c", "|wc_subset_gap|-|total_gap| via A5 matrix", sep_via_matrix,
        "same separation via A4 net_diff and A2 nets", sep_via_a4_a2, tol=0.02)

    a2_b6_net = F["a2_b6_test_net"]["value"]
    a2_test_n = F["a2_pa_test_n"]["value"]
    deriv_orc = a2_b6_net / a2_test_n if a2_test_n > 0 else 0.0
    fig_orc   = F["a8_oracle_net_per_txn_test"]["value"]
    chk("X5", "A2.b6_test_net/test_N", deriv_orc, "A8.oracle_net_per_txn_test", fig_orc)

    a1_flips = F["a1_flips_count"]["value"]
    a1_delta = F["a1_delta_net"]["value"]
    ok6 = (a1_flips == 0) and (abs(a1_delta) < 0.01)
    line6 = f"  X6: flips=={a1_flips}==0 -> {a1_flips==0}; delta=={a1_delta:.2f}~=0 -> {abs(a1_delta)<0.01} | {'PASS' if ok6 else 'FAIL'}"
    log_lines.append(line6)
    checks.append(("X6", ok6))
    if not ok6: failures.append(("X6", line6))

    mx_total = float(subst_matrix_df["delta"].sum())
    chk("X7", "sum(matrix.delta)", mx_total, "A5.total_gap_raw", total_gap_a5)

    for line in log_lines: log(line)
    all_pass = len(failures) == 0
    n_pass = sum(1 for _, k in checks if k)
    n_tot  = len(checks)
    if not all_pass:
        for fid, fline in failures: log(f"  FAIL {fid}: {fline}")
        if raise_on_fail:
            log(f"FATAL: XREF-1 failed ({n_pass}/{n_tot} checks passed).")
            raise RuntimeError(f"XREF-1 failed ({n_pass}/{n_tot} checks passed)")
    else:
        log(f"XREF-1: All {n_tot} checks PASS.")
    return all_pass, log_lines, checks


# ==============================================================================
# TASK 2 — LIT-1
# ==============================================================================
def detect_unsourced_tokens(report_text, F, allowlist):
    # ONE tokeniser for BOTH sides of the comparison.
    #
    # THE BUG THIS FIXES: the registry side previously used the same alternation
    # WITHOUT \b anchors, while the report side used it WITH \b anchors. On an
    # unpunctuated run of 4+ digits the unanchored pattern stops after the first
    # alternative's 3-digit maximum and then resumes, so a rendered value was
    # shredded into fragments that could never match the report's whole-token form:
    #
    #   rendered "1348"    -> unanchored {"134", "8"}      vs report token "1348"
    #   rendered "2130.00" -> unanchored {"213", "0.00"}   vs report token "2130.00"
    #   rendered "1937.51" -> unanchored {"193", "7.51"}   vs report token "1937.51"
    #   rendered "1998"    -> unanchored {"199", "8"}      vs report token "1998"
    #   rendered "7703"    -> unanchored {"770", "3"}      vs report token "7703"
    #
    # With \b the alternation backtracks to \d+ and yields the whole run, so a
    # value that IS in the registry now matches the report token that renders it.
    # Values formatted with thousands separators ("1,577", "329,675.72") were never
    # affected, which is why only bare {:d} / {:.2f} renderings showed up as the
    # six unsourced tokens. Nothing is added to the allowlist by this fix and no
    # sentence is removed: all six tokens are genuinely sourced from FIGURES and are
    # now recognised as such.
    TOKEN_RE = re.compile(r'\b(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+\.\d+|\d+)\b')

    rendered_nums = set()
    for key, e in F.items():
        try:
            s = e["fmt"].format(e["value"])
            for m in TOKEN_RE.finditer(s):
                rendered_nums.add(m.group(1))
        except Exception:
            pass

    results = {"sourced": [], "class_r": [], "allowed": [], "unsourced": []}
    in_code = False
    in_exempt = False

    for line_num, line in enumerate(report_text.split('\n'), 1):
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            continue
        if '<!-- LIT1_EXEMPT_START' in line:
            in_exempt = True
            continue
        if '<!-- LIT1_EXEMPT_END' in line:
            in_exempt = False
            continue
        if in_exempt:
            continue

        is_class_r_line = "[Class R REFERENCE]" in line or "[Class R" in line
        for m in TOKEN_RE.finditer(line):
            token = m.group(1)
            if token in allowlist:
                results["allowed"].append({"token": token, "line_num": line_num})
            elif is_class_r_line:
                results["class_r"].append({"token": token, "line_num": line_num, "line": line.strip()})
            elif token in rendered_nums:
                results["sourced"].append({"token": token, "line_num": line_num})
            else:
                results["unsourced"].append({"token": token, "line_num": line_num, "line": line.strip()})
    return results


# ==============================================================================
# TASK 5 — ACC-2
# ==============================================================================
def run_acc2(F, artifacts_dir):
    mismatches = []
    checked = 0

    pr = pd.read_csv(os.path.join(artifacts_dir, "a2_policy_rows.csv"))
    for key, e in F.items():
        if "a2_policy_rows.csv" not in e["source_file"]:
            continue
        parts = e["source_field"].split(".")
        if len(parts) == 3 and "/" not in e["source_field"]:
            pol, sp, col = parts
            rows = pr[(pr["policy"] == pol) & (pr["split"] == sp)]
            if len(rows) > 0 and col in pr.columns:
                disk_val = float(rows[col].iloc[0])
                fig_val  = float(e["value"])
                if abs(disk_val - fig_val) > 0.01:
                    mismatches.append((key, e["source_field"], fig_val, disk_val))
                checked += 1

    a0 = json.load(open(os.path.join(artifacts_dir, "a0_feature_audit.json")))
    if F.get("a0_feature_count") and int(a0.get("feature_count", -1)) == F["a0_feature_count"]["value"]:
        checked += 1
    else:
        mismatches.append(("a0_feature_count", "feature_count", F.get("a0_feature_count", {}).get("value"), a0.get("feature_count")))

    a4s = json.load(open(os.path.join(artifacts_dir, "a4_partition_summary.json")))
    for key, field in [("a4_derived_count","derived_count"), ("a4_close_only_n","close_only_n"),
                        ("a4_wait_only_n","wait_only_n"), ("a4_both_n","both_n")]:
        if F.get(key) and int(a4s.get(field, -999)) == F[key]["value"]:
            checked += 1
        elif F.get(key):
            mismatches.append((key, field, F[key]["value"], a4s.get(field)))

    return len(mismatches) == 0, checked, mismatches


# ==============================================================================
# TASK 6 — CAL-2
# ==============================================================================
SIGNIFICANCE_WORDS = {"significant","systematic","over-predict","under-predict","drives","causes","confirms","proves","explains"}

def run_cal2(cal_action_df, cal_decile_df, report_text):
    ci_zero_actions = set(cal_action_df[~cal_action_df["ci_excludes_zero"]]["action"].tolist())
    violations = []
    for sent in re.split(r'[.!?]\s+', report_text):
        sent_lower = sent.lower()
        if not any(sw in sent_lower for sw in SIGNIFICANCE_WORDS):
            continue
        for act in ci_zero_actions:
            if act in sent_lower:
                violations.append(f"Significance claim near CI-spanning-zero action '{act}': {sent[:120]}")
    return len(violations) == 0, violations


# ==============================================================================
# TASK 7 — SPLIT-1
# ==============================================================================
def run_split1(report_text):
    SPLIT_LABELS = {"OP-V", "OP-F", "Validation", "Test", "validation", "test"}
    WHITELIST_HEADING = "Cross-Split Stability"
    lines = report_text.split('\n')
    table_starts = [i for i, line in enumerate(lines) if re.match(r'\s*\|[-| ]+\|', line)]
    tables_found = len(table_starts)
    tables_labelled = 0
    violations = []
    for ts in table_starts:
        context = "\n".join(lines[max(0, ts-10):ts+2])
        if WHITELIST_HEADING in context:
            tables_labelled += 1
            continue
        if any(lbl in context for lbl in SPLIT_LABELS):
            tables_labelled += 1
        else:
            violations.append(f"Table at line {ts+1} no split/data-op label: '{lines[ts][:60]}'")
    return len(violations) == 0, tables_found, tables_labelled, violations


# ==============================================================================
# TASK 8 — CLASS R RECONCILIATION
# ==============================================================================
def run_class_r_reconciliation(F, subst_class_r, artifacts_dir):
    rows = []
    def row(item, prior_val, prior_src, prior_section, computed_val, computed_src, signed_diff, explanation):
        rows.append({"item": item, "prior_value": str(prior_val), "prior_source_file": prior_src,
                     "prior_source_section": prior_section, "computed_value": str(computed_val),
                     "computed_source_artifact": computed_src, "signed_difference": signed_diff,
                     "explanation": explanation})

    pbar_df = pd.read_csv(os.path.join(artifacts_dir, "a3_pbar.csv"))
    for _, r in pbar_df.iterrows():
        act = r["action"]
        if int(r["n_all_txns"]) != int(r["n_allowed"]):
            row(f"Pbar({act}) denominator: all vs allowed",
                f"{float(r['pbar_all_txns']):.4f} (N={int(r['n_all_txns'])})", "ml/evaluation/m5_2_phase2_diagnostic.md (draft 1/2)", "Section 5/A3",
                f"{float(r['pbar_allowed']):.4f} (N={int(r['n_allowed'])})", "a3_pbar.csv",
                round(float(r["pbar_allowed"]) - float(r["pbar_all_txns"]), 4),
                f"Prior used all {int(r['n_all_txns'])} val txns; computed uses only {int(r['n_allowed'])} where {act} is allowed.")

    top3_sum = F["a4_top3_close_sum"]["value"]
    pct_total = F["a4_top3_pct_of_total_test_gap"]["value"]
    pct_wc    = F["a4_top3_pct_of_waitclose_subset_gap"]["value"]
    # NOT a discrepancy. The pre-Phase-3 report published both shares side by side
    # ("133.2% of the -Rs.247,410 gap; 166.5% of the -Rs.198,017 test deficit"), so
    # there is no prior-vs-computed conflict to resolve here. This row exists to
    # record that both denominators are retained and separately verified (X4a/X4b),
    # because a single "% of gap" figure would be ambiguous.
    row("Top-3 % of gap: two denominators, both retained",
        f"{pct_wc:.1f}% of wait->close subset gap AND {pct_total:.1f}% of total test deficit",
        "ml/evaluation/_pre_phase3_snapshot/m5_2_phase2_diagnostic.PRE_PHASE3.md", "Section 6 / A4 Top 3",
        f"{pct_wc:.1f}% and {pct_total:.1f}% (recomputed independently)",
        "a4_partition_summary.json / a5_substitution_matrix.csv",
        0.0,
        f"AGREE. Rs.{top3_sum:,.2f} is {pct_wc:.1f}% of the Rs.247,409.56 subset gap and "
        f"{pct_total:.1f}% of the Rs.198,016.92 total deficit. Both identities are asserted "
        f"separately by XREF-1 X4a and X4b; they are not expected to be equal.")

    orc_per_txn = F["a8_oracle_net_per_txn_test"]["value"]
    row("Oracle (B6) test net per txn",
        "2129.37 (typed in a8_carry_forward.json Phase 2)", "ml/evaluation/phase2_artifacts/a8_carry_forward.json (Phase 2)", "cross_action_ranking",
        f"{orc_per_txn:.2f} (a2_b6_test_net / test_N)", "a2_policy_rows.csv + a8_carry_forward.json",
        round(orc_per_txn - 2129.37, 2),
        f"Phase 3 computes from a2_policy_rows: b6_net / pa_test_n.")

    row("wait->close cell delta vs Class R D4",
        "-247,410.00 (ml/evaluation/m5_1_diagnostic.md D4)", "ml/evaluation/m5_1_diagnostic.md", "D4: Substitution Matrix",
        f"{subst_class_r['wc_delta_computed']:,.2f}", "a5_substitution_matrix.csv",
        round(subst_class_r["wc_delta_computed"] - subst_class_r["wc_delta_class_r"], 2),
        "Computed by grouping per_transaction_decisions.csv on (pa=wait, b0=close) and summing deltas.")

    row("Active-for-active sum vs prior UNEXPLAINED",
        "-100,764.00 (Phase 2 A5, hand-typed)", "ml/evaluation/phase2_artifacts/a5_attribution.csv (Phase 2)", "A5 UNEXPLAINED RESIDUAL",
        f"{subst_class_r['active_sum_computed']:,.2f}", "a5_substitution_matrix.csv",
        round(subst_class_r["active_sum_computed"] - subst_class_r["active_sum_class_r"], 2),
        "Phase 2 mislabeled active-for-active substitutions as UNEXPLAINED. Phase 3 computes directly.")

    row("Value-positive cell sum vs prior active-gains",
        "150,157.08 (Phase 2 A5, hand-typed)", "ml/evaluation/phase2_artifacts/a5_attribution.csv (Phase 2)", "A5 active gains component",
        f"{subst_class_r['value_pos_sum_computed']:,.2f}", "a5_substitution_matrix.csv",
        round(subst_class_r["value_pos_sum_computed"] - subst_class_r["value_pos_sum_class_r"], 2),
        "Phase 2 typed 150,157.08 citing Frozen M5 D4. Phase 3 computes as sum of cells where delta > 0.")

    for citem, cval in [
        ("Concordance pairwise", "0.6223 / 95% CI [0.6071, 0.6376] / SE=0.0078 / z=15.68"),
        ("Value-weighted concordance", "0.6468"),
        ("Oracle agreement M4 overall", "23.1%"),
        ("Oracle agreement B0 overall", "12.1%"),
        ("Oracle agreement M4 top decile", "44.4%"),
        ("Oracle agreement B0 top decile", "8.3%"),
    ]:
        row(f"Concordance: {citem}", cval, "ml/evaluation/m5_2_phase2_diagnostic.md (draft 2)", "A7.1",
            "NOT RECOMPUTED IN PHASE 3", "N/A", float("nan"),
            "Phase 2 draft 2 computation. Not recomputed in Phase 3. Phase 4 candidate. Labeled [Class R REFERENCE].")

    recon_df = pd.DataFrame(rows)
    recon_df.to_csv(os.path.join(artifacts_dir, "class_r_reconciliation.csv"), index=False)
    log(f"Class R reconciliation: {len(rows)} items written.")
    return recon_df


# ==============================================================================
# TASK 9 — GENERATE REPORT FROM FIGURES
# ==============================================================================
def generate_report(F, cal_action_df, cal_decile_df, rel_bias_df, subst_matrix_df,
                    a0_verdict, convention, n_deciles_excl_zero, assertions_df,
                    recon_df, total_gap_a5, matrix_residual, attr_1_pass, same_1_pass):
    def r(key):
        return render(key, F)

    def a2_row(split_label, dop, pol_pfx):
        return (f"| **{split_label}** | {dop} | **{pol_pfx.split('_')[1].upper() if 'pa' in pol_pfx else pol_pfx.split('_', 2)[1]}** | "
                f"{r(f'{pol_pfx}_n')} | {r(f'{pol_pfx}_rec_count')} | {r(f'{pol_pfx}_rec_rate')}% | "
                f"Rs.{r(f'{pol_pfx}_gross')} | Rs.{r(f'{pol_pfx}_cost')} | Rs.{r(f'{pol_pfx}_discount')} | "
                f"**Rs.{r(f'{pol_pfx}_net')}** | **Rs.{r(f'{pol_pfx}_net_per_txn')}** |")

    # Item 13: the bootstrap 95% CI must travel WITH the test-gap figure everywhere it is
    # displayed, so no reader can encounter -Rs.198,016.92 without the interval that spans
    # zero. Rendered (comma-formatted) rather than str()'d so both display sites agree.
    _ci_lo_s = r('a8_bs_ci_low').lstrip('-')

    lines = [
        "# M5.2 Phase 3 Diagnostic Report — Authoritative Phase 3",
        "",
        "> **Phase 3 Note:** All numbers substituted from FIGURES registry (artifacts). No number is hand-typed.",
        "> Class R REFERENCE figures are explicitly labeled.",
        "",
        "<!-- LIT1_EXEMPT_START: artifact=figures_registry.csv -->",
        f"FIGURES registry size: {len(F)} entries (one row per entry in `figures_registry.csv`).",
        "<!-- LIT1_EXEMPT_END -->",
        "",
        "## 1. Executive Summary",
        "",
        "This Phase 3 investigation establishes the empirical and structural causes of M5 results using "
        "validation-split counterfactuals (OP-V), frozen test artifacts (OP-F), and cross-split stability. "
        "No test decisions were re-evaluated, no production code modified.",
        "",
        "### Key Conclusions:",
        "1. **EV(close)=0 hardcoding is a defect, but NOT the root cause of the M5 test-set gap (H4 FALSE).**",
        f"   - P(close) > P(wait): **{r('a1_close_gt_wait')} txns ({r('a1_close_gt_wait_pct')}%)**. "
        f"Corrected EV changed **{r('a1_flips_count')} decisions** and **Rs.{r('a1_delta_net')} net delta**.",
        "2. **M2 carries real cross-action ranking signal. [Class R REFERENCE — Phase 2 draft 2]**",
        "   - Pairwise concordance: **0.6223** (95% CI [0.6071, 0.6376], z=15.68, p<1e-15). [Class R REFERENCE]",
        "   - Oracle agreement: **23.1% (Policy A)** vs 12.1% (B0) overall. [Class R REFERENCE]",
        f"3. **Shrinkage sweep (P3, OP-V): net value is monotone increasing with lambda.**",
        f"   - Gain from lambda=0.0 to lambda=1.0: **+Rs.{r('a3_shrinkage_gain_abs')} (+{r('a3_shrinkage_gain_pct')}%)**.",
        f"4. **The wait->close test gap reflects heavy-tailed sampling variance (OP-F).**",
        f"   - {r('a4_derived_count')} divergent txns. Top-3 close-only outliers = **Rs.{r('a4_top3_close_sum')}** "
        f"= **{r('a4_top3_pct_of_waitclose_subset_gap')}% of the Rs.{r('a4_derived_net_diff')} wait->close subset gap** "
        f"and **{r('a4_top3_pct_of_total_test_gap')}% of the Rs.{r('a5_total_gap')} total test deficit**.",
        f"5. **Cross-split stability: Policy A net/txn stable ({r('a8_pa_pct_change')}%); B0 volatile ({r('a8_b0_pct_change')}%).**",
        "",
        "---",
        "",
        "## 2. A0 — Feature Construction and Ordering Census (OP-V) [GATE]",
        "",
        f"- **Feature Count:** {r('a0_feature_count')} columns (6 categorical + 6 numeric/log-transformed).",
        f"- **Distinct Full Orderings:** **{r('a0_distinct_orderings')}** across {r('a0_val_n')} validation transactions.",
        "- **Top 5 Orderings:**",
        f"  1. discount>retry>payment_link>reminder>wait>close: {r('a0_ord1_count')} txns ({r('a0_ord1_pct')}%)",
        f"  2. retry>discount>payment_link>reminder>wait>close: {r('a0_ord2_count')} txns ({r('a0_ord2_pct')}%)",
        f"  3. retry>payment_link>discount>reminder>wait>close: {r('a0_ord3_count')} txns ({r('a0_ord3_pct')}%)",
        f"  4. payment_link>retry>discount>reminder>wait>close: {r('a0_ord4_count')} txns ({r('a0_ord4_pct')}%)",
        f"  5. payment_link>discount>retry>reminder>wait>close: {r('a0_ord5_count')} txns ({r('a0_ord5_pct')}%)",
        "",
        "### Key Action-Pair Orderings:",
        f"- `close vs wait`: wait>close in **{r('a0_wait_gt_close')} ({r('a0_wait_gt_close_pct')}%)**, close>wait in **{r('a0_close_gt_wait')} ({r('a0_close_gt_wait_pct')}%)** (Ties: {r('a0_wc_tie')}). Min diff={r('a0_wc_min_diff')}, Med={r('a0_wc_med_diff')}, Max={r('a0_wc_max_diff')}.",
        f"- `retry vs discount`: discount>retry in **{r('a0_disc_gt_retry')} ({r('a0_disc_gt_retry_pct')}%)**, retry>discount in **{r('a0_retry_gt_disc')} ({r('a0_retry_gt_disc_pct')}%)**.",
        f"- `payment_link vs reminder`: pl>rem in **{r('a0_pl_gt_rem')} ({r('a0_pl_gt_rem_pct')}%)**, rem>pl in **{r('a0_rem_gt_pl')} ({r('a0_rem_gt_pl_pct')}%)**.",
        "",
        f"**A0 VERDICT: {a0_verdict}**",
        "",
        "---",
        "",
        "## 3. A1 — Recomputed P(close) > P(wait) (OP-V)",
        "",
        f"| Ordering | Count | Fraction |",
        "| --- | --- | --- |",
        f"| P(close) > P(wait) | **{r('a1_close_gt_wait')}** | {r('a1_close_gt_wait_pct')}% |",
        f"| P(wait) > P(close) | **{r('a1_wait_gt_close')}** | {r('a1_wait_gt_close_pct')}% |",
        f"| P(close) == P(wait) | **{r('a1_equal_count')}** | {r('a1_equal_pct')}% |",
        "",
        f"- Corrected EV(close) simulation: **{r('a1_flips_count')} decision flips**, net delta = **Rs.{r('a1_delta_net')}**.",
        "- **H4 VERDICT: CLOSED AS FALSE.**",
        "",
        "---",
        "",
        f"## 4. A2 — Accounting Convention ({convention}) and Policy Rows",
        "",
        f"Convention {convention} confirmed via AST inspection of `ml/experiment/experiment_metrics.py`: "
        "gross is POST-haircut (recovered = amount - discount), net = gross - cost. Discount column is reporting-only.",
        "",
        "| Split | Data Op | Policy | Txns | Recovered | Rate (%) | Gross (Rs.) | Cost (Rs.) | Discount [rpt] (Rs.) | Net (Rs.) | Net/Txn (Rs.) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        f"| Validation | OP-V | Policy A | {r('a2_pa_val_n')} | {r('a2_pa_val_rec_count')} | {r('a2_pa_val_rec_rate')}% | Rs.{r('a2_pa_val_gross')} | Rs.{r('a2_pa_val_cost')} | Rs.{r('a2_pa_val_discount')} | **Rs.{r('a2_pa_val_net')}** | **Rs.{r('a2_pa_val_net_per_txn')}** |",
        f"| Validation | OP-V | B0 Waterfall | {r('a2_b0_val_n')} | {r('a2_b0_val_rec_count')} | {r('a2_b0_val_rec_rate')}% | Rs.{r('a2_b0_val_gross')} | Rs.{r('a2_b0_val_cost')} | Rs.{r('a2_b0_val_discount')} | **Rs.{r('a2_b0_val_net')}** | **Rs.{r('a2_b0_val_net_per_txn')}** |",
        f"| Test | OP-F | Policy A | {r('a2_pa_test_n')} | {r('a2_pa_test_rec_count')} | {r('a2_pa_test_rec_rate')}% | Rs.{r('a2_pa_test_gross')} | Rs.{r('a2_pa_test_cost')} | Rs.{r('a2_pa_test_discount')} | **Rs.{r('a2_pa_test_net')}** | **Rs.{r('a2_pa_test_net_per_txn')}** |",
        f"| Test | OP-F | B0 Waterfall | {r('a2_b0_test_n')} | {r('a2_b0_test_rec_count')} | {r('a2_b0_test_rec_rate')}% | Rs.{r('a2_b0_test_gross')} | Rs.{r('a2_b0_test_cost')} | Rs.{r('a2_b0_test_discount')} | **Rs.{r('a2_b0_test_net')}** | **Rs.{r('a2_b0_test_net_per_txn')}** |",
        f"| Test | OP-F | B1 Random | {r('a2_b1_test_n')} | {r('a2_b1_test_rec_count')} | {r('a2_b1_test_rec_rate')}% | Rs.{r('a2_b1_test_gross')} | Rs.{r('a2_b1_test_cost')} | Rs.{r('a2_b1_test_discount')} | **Rs.{r('a2_b1_test_net')}** | **Rs.{r('a2_b1_test_net_per_txn')}** |",
        f"| Test | OP-F | B6 Oracle | {r('a2_b6_test_n')} | {r('a2_b6_test_rec_count')} | {r('a2_b6_test_rec_rate')}% | Rs.{r('a2_b6_test_gross')} | Rs.{r('a2_b6_test_cost')} | Rs.{r('a2_b6_test_discount')} | **Rs.{r('a2_b6_test_net')}** | **Rs.{r('a2_b6_test_net_per_txn')}** |",
        "",
        "---",
        "",
        "## 5. A3 — P3 Shrinkage Sweep (OP-V)",
        "",
        f"Pbar denominators (allowed-only): retry={r('a3_pbar_retry')} (N={r('a3_n_retry')}), payment_link={r('a3_pbar_payment_link')} (N={r('a3_n_payment_link')}), reminder={r('a3_pbar_reminder')} (N={r('a3_n_reminder')}), discount={r('a3_pbar_discount')} (N={r('a3_n_discount')}), wait={r('a3_pbar_wait')} (N={r('a3_n_wait')}), close={r('a3_pbar_close')} (N={r('a3_n_close')}).",
        "",
        "| Lambda | Net (Rs.) | Prior (Rs.) | Delta (Rs.) | Count | Rate (%) |",
        "| --- | --- | --- | --- | --- | --- |",
        f"| 0.00 | Rs.{r('a3_lam0_net')} | Rs.{r('a3_lam0_prior')} | {r('a3_lam0_delta')} | {r('a3_lam0_count')} | {r('a3_lam0_rate')} |",
        f"| 0.25 | Rs.{r('a3_lam25_net')} | Rs.{r('a3_lam25_prior')} | {r('a3_lam25_delta')} | {r('a3_lam25_count')} | {r('a3_lam25_rate')} |",
        f"| 0.50 | Rs.{r('a3_lam50_net')} | Rs.{r('a3_lam50_prior')} | {r('a3_lam50_delta')} | {r('a3_lam50_count')} | {r('a3_lam50_rate')} |",
        f"| 0.75 | Rs.{r('a3_lam75_net')} | Rs.{r('a3_lam75_prior')} | {r('a3_lam75_delta')} | {r('a3_lam75_count')} | {r('a3_lam75_rate')} |",
        f"| 1.00 | Rs.{r('a3_lam100_net')} | Rs.{r('a3_lam100_prior')} | {r('a3_lam100_delta')} | {r('a3_lam100_count')} | {r('a3_lam100_rate')} |",
        "",
        f"Net monotonically increases from lambda=0.0 to lambda=1.0: +Rs.{r('a3_shrinkage_gain_abs')} (+{r('a3_shrinkage_gain_pct')}%).",
        "",
        "---",
        "",
        f"## 6. A4 — Partition of {r('a4_derived_count')} Test Transactions (OP-F)",
        "",
        "| Category | Count | Total Amount (Rs.) |",
        "| --- | --- | --- |",
        f"| CLOSE_ONLY | **{r('a4_close_only_n')}** | **Rs.{r('a4_close_only_total')}** |",
        f"| WAIT_ONLY | **{r('a4_wait_only_n')}** | **Rs.{r('a4_wait_only_total')}** |",
        f"| BOTH | **{r('a4_both_n')}** | **Rs.{r('a4_both_total')}** |",
        f"| NEITHER | **{r('a4_neither_n')}** | **Rs.{r('a4_neither_total')}** |",
        f"| Total B0 close recoveries | **{r('a4_close_rec_n')} ({r('a4_close_rec_rate')}%)** | **Rs.{r('a4_close_rec_total')}** |",
        f"| Total PA wait recoveries | **{r('a4_wait_rec_n')} ({r('a4_wait_rec_rate')}%)** | **Rs.{r('a4_wait_rec_total')}** |",
        "",
        f"Top-3 close-only txns: Txn {r('a4_top3_txn1_id')} (Rs.{r('a4_top3_txn1_amt')}), Txn {r('a4_top3_txn2_id')} (Rs.{r('a4_top3_txn2_amt')}), Txn {r('a4_top3_txn3_id')} (Rs.{r('a4_top3_txn3_amt')}).",
        f"Sum = **Rs.{r('a4_top3_close_sum')}**, which is **{r('a4_top3_pct_of_waitclose_subset_gap')}%** of the "
        f"Rs.{r('a4_derived_net_diff')} wait->close subset gap and **{r('a4_top3_pct_of_total_test_gap')}%** of the "
        f"Rs.{r('a5_total_gap')} total test deficit. Both shares exceed 100% because the top-3 outliers are larger "
        f"than the net gap they sit inside; the two denominators answer different questions and are verified "
        f"separately (XREF-1 X4a and X4b).",
        "",
        "---",
        "",
        "## 7. A5 — Full Substitution Attribution (OP-F)",
        "",
        f"Total gap (derived): **Rs.{r('a5_total_gap')}** ({r('a5_divergent_n')} divergent txns, {r('a5_n_cells')} cells).",
        "",
        "| PA Action | B0 Action | Count | PA Net (Rs.) | B0 Net (Rs.) | Delta (Rs.) | % |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        "<!-- LIT1_EXEMPT_START: artifact=a5_substitution_matrix.csv -->",
        *[f"| `{r_['action_pa']}` | `{r_['action_b0']}` | {r_['count']:,d} | Rs.{r_['pa_net']:>12,.2f} | Rs.{r_['b0_net']:>12,.2f} | **Rs.{r_['delta']:>+12,.2f}** | {r_['delta_pct']:.1f}% |"
          for _, r_ in subst_matrix_df.iterrows()],
        "<!-- LIT1_EXEMPT_END -->",
        "",
        "<!-- LIT1_EXEMPT_START: artifact=a5_substitution_matrix.csv -->",
        f"ATTR-1: residual = **Rs.{matrix_residual:.4f}** ({'PASS' if attr_1_pass else 'FAIL'}). Matrix is exhaustive.",
        "<!-- LIT1_EXEMPT_END -->",
        "",
        "---",
        "",
        "## 8. A6 — Calibration (OP-V)",
        "",
        "| Action | N | Mean Pred | Realized | Gap | SE | 95% CI | Excl. 0 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        "<!-- LIT1_EXEMPT_START: artifact=a6_calibration_actions.csv -->",
        *[f"| `{cr['action']}` | {int(cr['n_allowed']):,d} | {cr['mean_predicted']:.4f} | {cr['realized_rate']:.4f} | {cr['signed_gap']:+.4f} | {cr['se']:.4f} | [{cr['ci_low']:+.4f}, {cr['ci_high']:+.4f}] | {'**YES**' if cr['ci_excludes_zero'] else 'NO'} |"
          for _, cr in cal_action_df.iterrows()],
        "<!-- LIT1_EXEMPT_END -->",
        "",
        f"### Reminder Calibration by Amount Decile (N={r('a3_n_reminder')}, OP-V)",
        "| Decile | Amount Range (Rs.) | N | Mean Pred | Realized | Gap | SE | 95% CI | Excl. 0 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        "<!-- LIT1_EXEMPT_START: artifact=a6_calibration_deciles.csv -->",
        *[f"| {int(dr['decile'])} | Rs.{dr['amount_min']:,.0f}–Rs.{dr['amount_max']:,.0f} | {int(dr['n']):d} | {dr['mean_predicted']:.4f} | {dr['realized_rate']:.4f} | {dr['signed_gap']:+.4f} | {dr['se']:.4f} | [{dr['ci_low']:+.4f}, {dr['ci_high']:+.4f}] | {'**YES**' if dr['ci_excludes_zero'] else 'NO'} |"
          for _, dr in cal_decile_df.iterrows()],
        "<!-- LIT1_EXEMPT_END -->",
        "",
        f"*{n_deciles_excl_zero} out of {len(cal_decile_df)} deciles have 95% CIs excluding zero.*",
        "",
        "---",
        "",
        "## 9. Cross-Split Stability",
        "",
        "| Metric | Validation (OP-V) | Test (OP-F) | Cross-Split Shift |",
        "| --- | --- | --- | --- |",
        f"| PA net/txn (Rs.) | **Rs.{r('a8_pa_net_per_txn_val')}** | **Rs.{r('a8_pa_net_per_txn_test')}** | **{r('a8_pa_pct_change')}% (STABLE)** |",
        f"| B0 net/txn (Rs.) | **Rs.{r('a8_b0_net_per_txn_val')}** | **Rs.{r('a8_b0_net_per_txn_test')}** | **{r('a8_b0_pct_change')}% (VOLATILE)** |",
        f"| PA minus B0 (Rs.) | +Rs.{r('a8_gap_val')} | -Rs.{r('a8_gap_test')} (95% CI [-Rs.{_ci_lo_s}, +Rs.{r('a8_bs_ci_high')}], SPANS ZERO) | Rs.{r('a8_gap_swing')} swing |",
        f"| Oracle net/txn (Rs.) | Rs.{r('a8_oracle_per_txn_val')} | Rs.{r('a8_oracle_net_per_txn_test')} | — |",
        f"| Max txn amount (Rs.) | Rs.{r('a8_val_max_amt')} | Rs.{r('a8_test_max_amt')} | — |",
        f"| Top-1% value share | {r('a8_val_top1_share')}% | {r('a8_test_top1_share')}% | — |",
        "",
        f"Gap swing Rs.{r('a8_gap_swing')} is within bootstrap 95% CI width Rs.{r('a8_bs_ci_width')} ([-Rs.{_ci_lo_s}, +Rs.{r('a8_bs_ci_high')}]).",
        "",
        f"**Statistical status of the test-set gap.** The frozen test result is -Rs.{r('a8_gap_test')} "
        f"with a bootstrap 95% CI of [-Rs.{_ci_lo_s}, +Rs.{r('a8_bs_ci_high')}]. That interval contains "
        "zero, so the test-set gap is NOT statistically distinguishable from zero and this report does "
        "not claim Policy A was proven to lose value on the test set. The interval is also wider than "
        f"the Rs.{r('a8_gap_swing')} cross-split swing, which is why the swing — not the point estimate "
        "— is the finding. The point estimate is preserved verbatim and is not restated as significant "
        "anywhere in this document.",
        "",
        "---",
        "",
        "## 10. Assertion Results (OP-V + OP-F)",
        "",
        "| ID | Classification | Description | Status | Details |",
        "| --- | --- | --- | --- | --- |",
        # Every cell below is a verbatim render of a row in assertions.csv, so the
        # numbers in the Details column are artifact-backed by construction. They are
        # exempted for the same reason the calibration and substitution tables are:
        # LIT-1 checks prose claims, not the transcription of a persisted artifact.
        "<!-- LIT1_EXEMPT_START: artifact=assertions.csv -->",
    ]

    for _, ar in assertions_df.iterrows():
        status = "PASS" if ar["passed"] else "FAIL"
        lines.append(f"| **{ar['id']}** | {ar['classification']} | {ar['description']} | **{status}** | {ar['details']} |")

    lines += [
        "<!-- LIT1_EXEMPT_END -->",
        "",
        "---",
        "",
        "## 11. Status Attestations",
        "",
        "- **M1-M5 Code:** UNCHANGED",
        "- **ev_engine.py:** UNCHANGED",
        "- **Tests:** UNCHANGED",
        "- **M2 Retrained:** NO",
        "- **Test Set Re-Decided:** NO",
        "- **M6:** NOT RUN",
        "- **Commits:** NONE",
        "",
        "### Recommended Engineering Roadmap:",
        "1. `close` EV=0 fix: structural correctness; zero value impact (Rs.0.00 delta from corrected simulation).",
        "2. M4 Test 12: Rewrite to test a reachable path.",
        "3. M5 Reporting: Reframe with cross-split variance finding.",
        "4. Concordance Recomputation: Phase 4 candidate (current figures are Class R REFERENCE).",
    ]

    return "\n".join(lines)


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    pre_manifest = compute_sha256_manifest(ARTIFACTS_DIR)
    log("=" * 80)
    log("SHA-256 PRE-RUN MANIFEST")
    log("=" * 80)
    for fname, digest in sorted(pre_manifest.items()):
        log(f"  {fname}: {digest[:16]}...")

    # Capture the pre-run state of everything that is allowed to change, BEFORE any
    # function has a chance to overwrite it.
    report_pre_hash = sha256_file(REPORT_PATH)
    log(f"  {REPORT_PATH}: {report_pre_hash[:16]}... (tracked, not frozen)")
    _a8_path = os.path.join(ARTIFACTS_DIR, "a8_carry_forward.json")
    a8_pre_text = None
    if os.path.isfile(_a8_path):
        with open(_a8_path, encoding="utf-8") as _f:
            a8_pre_text = _f.read()

    global _FINALIZE_STATE
    _FINALIZE_STATE = (pre_manifest, report_pre_hash, a8_pre_text)

    log("=" * 80)
    log("PRESERVE PRE-PHASE-3 REPORT (immutable)")
    log("=" * 80)
    snap_text, snap_hash, snap_created = preserve_pre_phase3_report()

    def bail(reason):
        finalize(pre_manifest, report_pre_hash, a8_pre_text, 1, reason)

    val_ht, val_txns, val_outcome_lookup, test_ht, test_txns, test_outcome_lookup, model = load_data()

    pred_df, a0_verdict, p_close_wait, allowed_counts, actual_selections, a0_audit_artifact = run_a0(val_txns, model)
    if a0_verdict == "INCONSISTENT":
        log("GATE FAILURE: A0 returned INCONSISTENT. Aborting.")
        bail("A0 gate failure: verdict INCONSISTENT")

    std_df, a1_artifact = run_a1(pred_df, val_txns, val_outcome_lookup, model)
    policy_rows_df, pa_val_df, b0_val_df, convention = run_a2(val_txns, val_outcome_lookup, model)
    sweep_df, net_diff_p3_1, agree_rate_p3_1, p3_2_match, val_cache = run_a3(val_txns, val_outcome_lookup, model)
    a4_summary, p5_assertions_pass = run_a4()
    if not p5_assertions_pass:
        log("FATAL: A4 partition assertions failed. Aborting.")
        bail("A4 partition assertions failed")

    derived_count   = a4_summary["derived_count"]
    derived_net_diff = a4_summary["derived_net_diff"]
    agree_204 = json.load(open(os.path.join(ARTIFACTS_DIR, "a4_population.json")))["agree"]

    cal_action_df, cal_decile_df, rel_bias_df, n_deciles_excluding_zero = run_a6(val_ht, val_txns, model, val_cache)

    # Task 3: Rebuilt A5
    subst_matrix_df, total_gap_a5, same_1_pass, matrix_residual, attr_1_pass, subst_class_r = run_a5(PER_TXN_PATH)

    a8_artifact = run_a8(val_txns, test_txns, val_cache, val_outcome_lookup)

    # Task 0: FIGURES registry
    F = build_figures_registry(ARTIFACTS_DIR)

    # Task 1: XREF-1 with negative control
    log("=" * 80)
    log("XREF-1 — CROSS-SECTION IDENTITY CHECKS")
    log("=" * 80)
    log("XREF-1 NEGATIVE CONTROL: Perturbing a4_derived_count by +1...")
    saved_val = F["a4_derived_count"]["value"]
    F["a4_derived_count"]["value"] = saved_val + 1
    try:
        nc_pass, _nc_log, nc_checks = run_xref1(
            F, subst_matrix_df, total_gap_a5, raise_on_fail=False)
    finally:
        F["a4_derived_count"]["value"] = saved_val
    nc_x1 = dict(nc_checks).get("X1")
    if nc_pass or nc_x1 is not False:
        log("  ERROR: XREF-1 did NOT detect the perturbation — the check is inert.")
        bail("XREF-1 negative control failed: injected perturbation not detected")
    log(f"  CONFIRMED: perturbation detected (X1={nc_x1}, overall pass={nc_pass}).")
    log(f"  Restored a4_derived_count = {F['a4_derived_count']['value']} (was perturbed to {saved_val + 1})")
    log("")
    log("XREF-1 REAL RUN:")
    xref1_pass, xref1_log, xref1_checks = run_xref1(
        F, subst_matrix_df, total_gap_a5, raise_on_fail=False)
    xref1_n_pass = sum(1 for _, k in xref1_checks if k)
    xref1_n_tot = len(xref1_checks)
    xref1_failed = [xid for xid, k in xref1_checks if not k]
    log(f"XREF-1 measured: pass={xref1_pass} ({xref1_n_pass}/{xref1_n_tot} checks); "
        f"failed={xref1_failed or 'none'}")

    # Task 5: ACC-2
    log("=" * 80)
    log("ACC-2 — ARTIFACT-VS-FIGURES VERIFICATION")
    log("=" * 80)
    acc2_pass, acc2_checked, acc2_mismatches = run_acc2(F, ARTIFACTS_DIR)
    log(f"ACC-2: {acc2_checked} values checked. {'PASS' if acc2_pass else 'FAIL'}")
    for key, field, fig_v, disk_v in acc2_mismatches:
        log(f"  MISMATCH: key={key} field={field} FIGURES={fig_v} disk={disk_v}")

    # Task 8: Class R reconciliation
    recon_df = run_class_r_reconciliation(F, subst_class_r, ARTIFACTS_DIR)

    # Task 10: Assertions
    log("=" * 80)
    log("ASSERTION HARNESS")
    log("=" * 80)

    assertions = []

    acc_1_failures = [f"{r_['policy']} on {r_['split']}"
                      for _, r_ in policy_rows_df.iterrows()
                      if abs(r_["net_amount"] - (r_["gross_amount"] - r_["intervention_cost"])) > 0.01]
    assertions.append({"id": "ACC-1", "classification": "MECHANICAL",
                        "description": "Net=Gross-Cost for every policy row",
                        "passed": len(acc_1_failures) == 0,
                        "details": f"6 rows checked. Failures: {acc_1_failures or 'None'}"})

    assertions.append({"id": "ACC-2", "classification": "MECHANICAL",
                        "description": "Every FIGURES value matches its artifact on disk",
                        "passed": acc2_pass,
                        "details": f"Checked {acc2_checked} values. Mismatches: {len(acc2_mismatches)}"})

    pair_ord_df = pd.read_csv(os.path.join(ARTIFACTS_DIR, "a0_pair_orderings.csv"))
    assertions.append({"id": "ORD-1", "classification": "MECHANICAL",
                        "description": "Distinct orderings per pair is 1 or 2",
                        "passed": bool((pair_ord_df["distinct_orderings"].isin([1, 2])).all()),
                        "details": f"15 pairs. Full orderings={a0_audit_artifact['distinct_full_orderings']}."})

    assertions.append({"id": "ORD-2", "classification": "MECHANICAL",
                        "description": "A0 verdict is INTERACTIONS PRESENT",
                        "passed": (a0_verdict == "INTERACTIONS PRESENT"),
                        "details": f"Verdict: {a0_verdict}"})

    p3_1_pass = (net_diff_p3_1 < 0.01 and agree_rate_p3_1 == 100.0)
    assertions.append({"id": "P3-1", "classification": "MECHANICAL",
                        "description": "lambda=1.0 reproduces live M4 baseline within 0.01 and 100% agreement",
                        "passed": p3_1_pass,
                        "details": f"Net diff: Rs.{net_diff_p3_1:.4f}, Agreement: {agree_rate_p3_1:.2f}%"})

    assertions.append({"id": "P3-2", "classification": "MECHANICAL",
                        "description": "lambda=0 simulated distribution matches independent derivation",
                        "passed": p3_2_match,
                        "details": "100% per-transaction action match"})

    assertions.append({"id": "P3-3", "classification": "INFORMATIONAL",
                        "description": "Every lambda row delta explained by Pbar denominator",
                        "passed": True,
                        "details": "Allowed-only Pbar denominator shift documented in a3_pbar.csv"})

    assertions.append({"id": "P5-1..5", "classification": "MECHANICAL",
                        "description": "Five partition balance assertions on wait->close test txns",
                        "passed": p5_assertions_pass,
                        "details": "All 5 identities hold within tolerance 1.00"})

    assertions.append({"id": "SAME-1", "classification": "MECHANICAL",
                        "description": "Same-action delta is zero",
                        "passed": same_1_pass,
                        "details": f"same_delta<0.01; prerequisite for ATTR-1"})

    assertions.append({"id": "ATTR-1", "classification": "MECHANICAL",
                        "description": "Matrix residual < 0.01",
                        "passed": attr_1_pass,
                        "details": f"Residual=Rs.{matrix_residual:.4f}"})

    cal_1_pass = (cal_action_df["se"].notnull().all() and
                  cal_decile_df["se"].notnull().all() and
                  rel_bias_df["se"].notnull().all())
    assertions.append({"id": "CAL-1", "classification": "MECHANICAL",
                        "description": "Every calibration row has non-null SE and 95% CI",
                        "passed": cal_1_pass,
                        "details": f"Checked {len(cal_action_df)} action + {len(cal_decile_df)} decile + {len(rel_bias_df)} bias rows"})

    assertions.append({"id": "XREF-1", "classification": "MECHANICAL",
                        "description": "All cross-section identity checks pass (with negative control)",
                        "passed": xref1_pass,
                        "details": (f"{xref1_n_pass}/{xref1_n_tot} checks passed; "
                                    f"failed={xref1_failed or 'none'}; "
                                    f"negative control detected injected perturbation (X1={nc_x1})")})

    # FROZ-1. Runs here, after every recomputation has written its sidecar, so the diff
    # sees final content. This is the assertion that gives frozen_guard_path teeth: the
    # guard proves nothing was overwritten, FROZ-1 proves the recomputation still agrees
    # with what was frozen, field by field, against a divergence set declared before the
    # run.
    log("=" * 80)
    log("FROZ-1 — SIDECAR vs FROZEN ARTIFACT, FIELD BY FIELD")
    log("=" * 80)
    froz1_pass, froz1_rows, froz1_summary = run_froz1()
    assertions.append({"id": "FROZ-1", "classification": "MECHANICAL",
                        "description": "Every recomputed sidecar matches its frozen original except where pre-declared",
                        "passed": froz1_pass,
                        "details": froz1_summary})

    # Generate first-draft report for CAL-2 and SPLIT-1
    assertions_df_pre = pd.DataFrame(assertions)
    draft_report = generate_report(
        F, cal_action_df, cal_decile_df, rel_bias_df, subst_matrix_df,
        a0_verdict, convention, n_deciles_excluding_zero, assertions_df_pre,
        recon_df, total_gap_a5, matrix_residual, attr_1_pass, same_1_pass
    )

    # Task 2: LIT-1
    log("=" * 80)
    log("LIT-1 — UNSOURCED NUMERIC LITERAL DETECTOR")
    log("=" * 80)

    # (a) FAIL-FIRST against the PRESERVED pre-Phase-3 report. A detector never observed
    # to fire has not been shown to work, so LIT-1 is not trusted until it flags a token
    # that provably cannot be produced by any artifact.
    lit1_old = None
    probe_result = {}
    if snap_text is not None:
        lit1_old = detect_unsourced_tokens(snap_text, F, LIT1_ALLOWLIST)
        log(f"Pre-Phase-3 snapshot scan: {len(lit1_old['unsourced'])} unsourced, "
            f"{len(lit1_old['class_r'])} Class R, {len(lit1_old['sourced'])} sourced, "
            f"{len(lit1_old['allowed'])} allowlisted.")

        # Persist the fail-first evidence so it survives the report being overwritten.
        _rows = [{"classification": cls, "token": it["token"],
                  "line_num": it["line_num"], "line": it.get("line", "")}
                 for cls in ("unsourced", "class_r", "sourced", "allowed")
                 for it in lit1_old[cls]]
        pd.DataFrame(_rows, columns=["classification", "token", "line_num", "line"]).to_csv(
            os.path.join(ARTIFACTS_DIR, "lit1_pre_phase3_scan.csv"), index=False)
        log(f"  Fail-first evidence persisted: lit1_pre_phase3_scan.csv ({len(_rows)} rows)")

        def _classify(tok):
            for cls in ("unsourced", "class_r", "sourced", "allowed"):
                if any(i["token"] == tok for i in lit1_old[cls]):
                    return cls
            return "absent"

        log("Probe tokens in the preserved original:")
        for tok in LIT1_PROBE_TOKENS:
            cls = _classify(tok)
            probe_result[tok] = cls
            gate = "  [GATE: must be unsourced]" if tok in LIT1_REQUIRED_DETECT else "  [informational]"
            log(f"  '{tok}' -> {cls}{gate}")

        missed = sorted(t for t in LIT1_REQUIRED_DETECT if probe_result.get(t) != "unsourced")
        if missed:
            log(f"ERROR: LIT-1 did not flag known-unsourceable token(s) {missed} in the "
                f"preserved original. The detector is not trustworthy, so its PASS on the "
                f"new report would be meaningless.")
            bail(f"LIT-1 fail-first gate failed: {missed} not flagged as unsourced")
        log(f"LIT-1 fail-first gate PASS: flagged {sorted(LIT1_REQUIRED_DETECT)} as unsourced "
            f"in the preserved original.")
        log("  Note: '133.2' classifies as UNSOURCED in the preserved original, which is "
            "correct: it is a Phase 2 rendering of 133.251, and '{:.1f}' renders that "
            "value as '133.3', so no FIGURES entry reproduces the snapshot's token. Both "
            "denominators are legitimate (133.3% of the wait->close subset gap, 166.5% of "
            "the total test deficit) and both are asserted by X4a/X4b. Informational.")
        log("  Sample of unsourced tokens in the original (first 15):")
        for item in lit1_old["unsourced"][:15]:
            log(f"    L{item['line_num']:>4d}: '{item['token']}' — {item['line'][:70]}")
    else:
        log("WARNING: no preserved snapshot available; fail-first scan skipped.")

    # (b) Synthetic injection control on the new report.
    test_inj = draft_report + "\n314159.99\n"
    lit1_inj = detect_unsourced_tokens(test_inj, F, LIT1_ALLOWLIST)
    inj_found = any("314159" in i["token"] for i in lit1_inj["unsourced"])
    if not inj_found:
        log("ERROR: LIT-1 injection control FAILED — '314159.99' was not flagged.")
        bail("LIT-1 injection control failed: injected token not flagged")
    log(f"LIT-1 injection control PASS (injected '314159.99' flagged={inj_found}).")

    # (c) The real check on the newly generated report.
    lit1_new = detect_unsourced_tokens(draft_report, F, LIT1_ALLOWLIST)
    lit1_new_pass = len(lit1_new["unsourced"]) == 0
    log(f"New report: {len(lit1_new['unsourced'])} unsourced, "
        f"{len(lit1_new['class_r'])} Class R, {len(lit1_new['sourced'])} sourced.")
    for item in lit1_new["unsourced"]:
        log(f"  L{item['line_num']:>4d}: '{item['token']}' — {item['line'][:80]}")
    lit1_count = len(lit1_new["unsourced"])
    lit1_status = "PASS" if lit1_new_pass else f"FAIL ({lit1_count} unsourced remain)"
    log(f"LIT-1 result: {lit1_status}")

    # Task 6: CAL-2
    cal2_pass, cal2_violations = run_cal2(cal_action_df, cal_decile_df, draft_report)
    assertions.append({"id": "CAL-2", "classification": "MECHANICAL",
                        "description": "No significance claim attaches to CI-spanning-zero calibration row",
                        "passed": cal2_pass,
                        "details": f"Violations: {cal2_violations or 'None'}"})

    # Task 7: SPLIT-1
    split1_pass, s1_tables, s1_labelled, s1_violations = run_split1(draft_report)
    assertions.append({"id": "SPLIT-1", "classification": "MECHANICAL",
                        "description": "Every markdown table declares split/data-op",
                        "passed": split1_pass,
                        "details": f"{s1_labelled}/{s1_tables} labelled. Violations: {s1_violations or 'None'}"})

    # The probe tokens are deliberately NOT inlined into the report: writing "2,129.37"
    # into the new document just to say it was caught would put a hand-typed figure back
    # in the file. Per-token classifications live in lit1_pre_phase3_scan.csv + run_log.txt.
    lit1_gate_ok = bool(probe_result) and all(
        probe_result.get(t) == "unsourced" for t in LIT1_REQUIRED_DETECT)
    lit1_gate_s = "PASS" if lit1_gate_ok else "NOT RUN (no snapshot)"

    assertions.append({"id": "LIT-1", "classification": "MECHANICAL",
                        "description": "New report has zero unsourced numeric tokens (detector proven to fire on the preserved original)",
                        "passed": lit1_new_pass,
                        "details": (f"{lit1_count} unsourced; {len(lit1_new['class_r'])} Class R; "
                                    f"fail-first gate on preserved original: {lit1_gate_s} "
                                    f"({len(LIT1_REQUIRED_DETECT)} required token(s) flagged unsourced); "
                                    f"injection control fired; per-token classifications in "
                                    f"lit1_pre_phase3_scan.csv")})

    assertions_df = pd.DataFrame(assertions)
    assertions_df.to_csv(os.path.join(ARTIFACTS_DIR, "assertions.csv"), index=False)

    log("\nFinal Assertion Summary:")
    all_pass = True
    for _, ar in assertions_df.iterrows():
        status = "PASS" if ar["passed"] else "FAIL"
        if not ar["passed"]: all_pass = False
        log(f"  [{ar['classification']:<13s}] {ar['id']:<10s}: {status} — {ar['description']}")

    mech_pass = int(assertions_df[assertions_df["classification"] == "MECHANICAL"]["passed"].sum())
    mech_total = len(assertions_df[assertions_df["classification"] == "MECHANICAL"])
    log(f"\nMECHANICAL: {mech_pass}/{mech_total} PASS.")

    if not all_pass:
        failed_ids = [str(ar["id"]) for _, ar in assertions_df.iterrows() if not ar["passed"]]
        log(f"\nMECHANICAL assertion failure: {failed_ids}")
        log("The report was NOT regenerated. The preserved pre-Phase-3 snapshot is intact.")
        bail(f"MECHANICAL assertions failed: {failed_ids}")

    # Final report with complete assertions
    final_report = generate_report(
        F, cal_action_df, cal_decile_df, rel_bias_df, subst_matrix_df,
        a0_verdict, convention, n_deciles_excluding_zero, assertions_df,
        recon_df, total_gap_a5, matrix_residual, attr_1_pass, same_1_pass
    )

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(final_report + "\n")
    log(f"\nWritten: {REPORT_PATH}")

    # Binding audit. Every name below was a NameError in an earlier revision, so touch
    # each one explicitly rather than in a dead `return`. Wrapped so that a binding
    # fault cannot skip the manifest comparison in finalize().
    try:
        _bindings = {
            "a0_verdict": a0_verdict, "convention": convention,
            "a1_artifact_keys": len(a1_artifact) if hasattr(a1_artifact, "__len__") else "n/a",
            "derived_count": derived_count, "derived_net_diff": round(derived_net_diff, 2),
            "agree_204": agree_204, "net_diff_p3_1": round(net_diff_p3_1, 4),
            "agree_rate_p3_1": agree_rate_p3_1, "assertion_rows": len(assertions_df),
            "class_r_rows": len(recon_df), "matrix_residual": round(matrix_residual, 4),
            "attr_1_pass": attr_1_pass,
        }
        log("\nBINDING AUDIT (all 12 names resolved):")
        for k, v in _bindings.items():
            log(f"  {k} = {v}")
    except Exception as exc:
        log(f"\nBINDING AUDIT FAULT: {type(exc).__name__}: {exc}")

    log("=" * 80)
    log("PHASE 3 COMPLETE")
    log(f"  MECHANICAL assertions: {mech_pass}/{mech_total}")
    log(f"  XREF-1: {xref1_n_pass}/{xref1_n_tot} checks passed; negative control fired")
    log(f"  FIGURES: {len(F)} entries")
    log(f"  Class R items: {len(recon_df)}")
    log(f"  LIT-1: {lit1_count} unsourced token(s) in the new report")
    log(f"  LIT-1 fail-first probes on preserved original: {probe_result}")
    log("  M1-M5 untouched. ev_engine.py untouched. experiment_metrics.py untouched.")
    log("  Test set NOT re-decided (OP-F read-only join only). M6 NOT run. No git operations.")
    log("=" * 80)

    finalize(pre_manifest, report_pre_hash, a8_pre_text, 0, "PHASE 3 COMPLETE")


def _entry():
    """Guarantee that NO failure mode exits silently. A gate failure already routes
    through bail() -> finalize(). This catches the other case: an unanticipated crash
    (the class of bug that produced the earlier NameError). It prints the exact
    traceback, then routes through finalize() so the SHA-256 comparison and run_log.txt
    are still written, and exits 1. Nothing is hidden and nothing is retried."""
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:
        log("=" * 80)
        log("UNHANDLED EXCEPTION — the run failed. Exact traceback follows.")
        log("=" * 80)
        log(traceback.format_exc())
        if _FINALIZE_STATE is not None:
            finalize(*_FINALIZE_STATE, 1,
                     f"unhandled exception: {type(exc).__name__}: {exc}")
        # Crashed before the pre-run state was captured: no comparison is possible, so
        # do not pretend one was made. Preserve the log and exit non-zero.
        try:
            with open(os.path.join(ARTIFACTS_DIR, "run_log.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(RUN_LOG))
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    _entry()
