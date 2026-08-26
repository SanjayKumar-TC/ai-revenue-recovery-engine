"""
M5: Baseline Policies
=====================
Seven baselines for comparison with Policy A (M4 decision engine).

B0 — Fixed Waterfall (PRIMARY COMPARATOR): retry → retry → reminder → stop
B1 — Random Eligible: uniform random among M3-allowed actions
B2 — Always Retry
B3 — Always Payment Link
B4 — Always Reminder
B5 — Always Discount
B6 — Oracle Ceiling: best realized net outcome per transaction

ALL baselines are subject to the SAME M3 safety constraints as Policy A.
No baseline may select an action that M3 has blocked.
"""

import numpy as np
from ml.decision.decision_config import ACTION_COSTS, ACTION_PRIORITY_ORDER, DEFAULT_DISCOUNT_PERCENT

# ============================================================
# B0 Waterfall Configuration
# ============================================================
# The baseline sequence is: retry → retry → reminder → stop.
# With single-decision semantics, the position in the sequence is
# determined by attempt_number:
#   attempt_number <= BASELINE_MAX_RETRIES: prefer retry
#   else: prefer reminder, then stop (close)
# M3 may still block retry (e.g., at attempt_number >= MAX_AUTO_RETRIES),
# in which case the baseline advances to its next step.
BASELINE_MAX_RETRIES = 2


def _safe_fallback(allowed_set, escalation_required):
    """Last-resort action when no preferred action is available."""
    if escalation_required and "escalate" in allowed_set:
        return "escalate"
    for a in ACTION_PRIORITY_ORDER:
        if a in allowed_set:
            return a
    if "escalate" in allowed_set:
        return "escalate"
    return None


# ============================================================
# B0 — Fixed Waterfall (Primary Comparator)
# ============================================================

def select_b0_waterfall(allowed_actions, escalation_required, terminal,
                        attempt_number):
    """
    B0: Fixed waterfall — retry → retry → reminder → stop.

    Documented rules:
      - attempt_number <= 2 (BASELINE_MAX_RETRIES): prefer retry
        - retry #1: attempt_number=1 — prefer retry
        - retry #2: attempt_number=2 — prefer retry (M3 blocks → advance)
      - attempt_number > 2: prefer reminder
      - After all steps: stop (close)
      - If preferred blocked by M3: advance to next in sequence
      - If escalation_required and all automated blocked: escalate
      - retry unavailable (e.g. risk_block): advance to reminder
      - reminder unavailable (e.g. contact fatigue): stop (close)

    Returns: (action, source, fallback_used)
    """
    allowed = set(allowed_actions)

    # Terminal cases
    if terminal and len(allowed) == 0:
        return "no_action_required", "terminal_no_action", False
    if terminal and len(allowed) == 1:
        return list(allowed)[0], "terminal_forced", False

    # Waterfall: retry phase (attempt_number <= BASELINE_MAX_RETRIES)
    if attempt_number <= BASELINE_MAX_RETRIES:
        if "retry" in allowed:
            return "retry", f"waterfall_retry_attempt_{attempt_number}", False
        # Retry blocked → advance to reminder
        if "reminder" in allowed:
            return "reminder", "waterfall_retry_blocked_to_reminder", True
        # Reminder also blocked → stop
        if "close" in allowed:
            return "close", "waterfall_retry_reminder_blocked_close", True
        fb = _safe_fallback(allowed, escalation_required)
        return fb or "no_action_required", "waterfall_fallback", True

    # Waterfall: reminder phase (attempt_number > BASELINE_MAX_RETRIES)
    if "reminder" in allowed:
        return "reminder", "waterfall_reminder", False

    # Beyond sequence: stop (close)
    if "close" in allowed:
        return "close", "waterfall_stop", False

    fb = _safe_fallback(allowed, escalation_required)
    return fb or "no_action_required", "waterfall_fallback", True


# ============================================================
# B1 — Random Eligible
# ============================================================

def select_b1_random(allowed_actions, escalation_required, terminal, rng):
    """
    B1: Uniform random among M3-allowed non-escalate actions.
    Seeded for reproducibility.
    """
    allowed = set(allowed_actions)

    if terminal and len(allowed) == 0:
        return "no_action_required", "terminal_no_action", False
    if terminal and len(allowed) == 1:
        return list(allowed)[0], "terminal_forced", False

    candidates = sorted(a for a in allowed if a != "escalate")
    if not candidates:
        if "escalate" in allowed:
            return "escalate", "only_escalate", False
        return "no_action_required", "no_candidates", True

    selected = rng.choice(candidates)
    return selected, "random", False


# ============================================================
# B2–B5 — Constant-Action Diagnostics
# ============================================================

def select_constant_action(preferred, allowed_actions, escalation_required,
                           terminal):
    """
    Constant-action baseline: always prefer one action.
    When preferred is blocked, fall back to PRIORITY_ORDER among allowed.

    Returns: (action, source, fallback_used)
    """
    allowed = set(allowed_actions)

    if terminal and len(allowed) == 0:
        return "no_action_required", "terminal_no_action", False
    if terminal and len(allowed) == 1:
        return list(allowed)[0], "terminal_forced", False

    if preferred in allowed:
        return preferred, f"constant_{preferred}", False

    # Fallback
    fb = _safe_fallback(allowed, escalation_required)
    return fb or "no_action_required", f"constant_{preferred}_fallback", True


# ============================================================
# B6 — Oracle Ceiling
# ============================================================

def select_b6_oracle(allowed_actions, escalation_required, terminal,
                     transaction_id, amount, outcome_lookup,
                     discount_percent=None):
    """
    B6: Oracle — select the M3-allowed action with the highest realized
    net recovered amount.

    NOT a fair comparator. Exists to bound achievable headroom.

    Returns: (action, source, fallback_used)
    """
    allowed = set(allowed_actions)
    dp = discount_percent if discount_percent is not None else DEFAULT_DISCOUNT_PERCENT

    if terminal and len(allowed) == 0:
        return "no_action_required", "terminal_no_action", False
    if terminal and len(allowed) == 1:
        return list(allowed)[0], "terminal_forced", False

    # Exclude escalate (no realized outcome in M1)
    candidates = sorted(a for a in allowed if a != "escalate")
    if not candidates:
        if "escalate" in allowed:
            return "escalate", "oracle_only_escalate", False
        return "no_action_required", "oracle_no_candidates", True

    best_action = None
    best_net = float("-inf")

    for action in candidates:
        outcome = outcome_lookup.get((transaction_id, action), 0)
        if outcome == 1:
            if action == "discount":
                recovered = amount * (1.0 - dp / 100.0)
            else:
                recovered = amount
        else:
            recovered = 0.0
        cost = ACTION_COSTS.get(action, 0.0)
        net = recovered - cost

        if net > best_net:
            best_net = net
            best_action = action
        elif net == best_net:
            # Tiebreak: priority order
            try:
                curr_idx = ACTION_PRIORITY_ORDER.index(action)
            except ValueError:
                curr_idx = len(ACTION_PRIORITY_ORDER)
            try:
                best_idx = ACTION_PRIORITY_ORDER.index(best_action)
            except ValueError:
                best_idx = len(ACTION_PRIORITY_ORDER)
            if curr_idx < best_idx:
                best_action = action

    return best_action, "oracle", False
