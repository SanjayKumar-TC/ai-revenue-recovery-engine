"""
M4: Decision Engine Configuration
===================================
Centralized action costs, tie-breaking order, and version.

All costs are PROTOTYPE ASSUMPTIONS — not claims about
Razorpay's actual operating costs.
"""

DECISION_ENGINE_VERSION = "v1.0"

# ---------------------------------------------------------------------------
# ACTION COSTS (₹)
# ---------------------------------------------------------------------------
# These are marginal intervention costs incurred when the action is taken.
# They represent the operational cost of executing the action, regardless
# of whether recovery succeeds.
#
# Prototype assumptions:
#   - retry: ₹2 — payment gateway fee per retry attempt
#   - payment_link: ₹5 — generating + delivering a payment link (SMS/email/WhatsApp)
#   - reminder: ₹3 — sending a notification to the customer
#   - discount: ₹0 — the discount itself is a conditional cost (subtracted from
#     recoverable amount), not a fixed operational cost. This field represents
#     only the fixed operational cost of offering the discount (e.g. sending the
#     offer message), which we set to ₹0 for simplicity. The actual discount
#     amount is handled separately in the EV formula.
#   - wait: ₹0 — no operational cost for deferral
#   - close: ₹0 — no operational cost for permanent closure
#
# Escalate is NOT included here because it does not participate in normal
# EV optimization. Escalation is a routing decision made by M3.
#
# These are NOT Razorpay internal cost estimates.

ACTION_COSTS = {
    "retry": 2.0,
    "payment_link": 5.0,
    "reminder": 3.0,
    "discount": 0.0,
    "wait": 0.0,
    "close": 0.0,
}

# ---------------------------------------------------------------------------
# DEFAULT DISCOUNT
# ---------------------------------------------------------------------------
# If no discount_percent is specified in the transaction context, use this
# default for EV calculation when evaluating the discount action.
# This represents a typical discount offer in the prototype.
DEFAULT_DISCOUNT_PERCENT = 10.0

# ---------------------------------------------------------------------------
# TIE-BREAKING PRIORITY ORDER
# ---------------------------------------------------------------------------
# When two or more permitted actions have effectively equal EV:
#   1. Prefer lower intervention cost (handled in code)
#   2. Prefer higher predicted recovery probability (handled in code)
#   3. Use this fixed deterministic priority order
#
# Lower index = higher priority.
# This order reflects a preference for less-intrusive actions when economics
# are equivalent.
#
# Escalate is excluded from this ranking — it is not an EV competitor.
ACTION_PRIORITY_ORDER = [
    "retry",          # cheapest automated recovery, least customer contact
    "wait",           # no intervention cost, preserves option value
    "reminder",       # light-touch customer contact
    "payment_link",   # alternative payment path
    "discount",       # involves revenue concession
    "close",          # permanent closure (last resort among automated)
]

# EV equality tolerance for tie-breaking (floating point comparison)
EV_TIE_TOLERANCE = 1e-6
