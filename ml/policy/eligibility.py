"""
M3: Eligibility Matrix — Copied from M1
=========================================
This is an EXACT copy of the ELIGIBILITY dict from generate_data.py (M1).
It defines which actions are structurally eligible for each failure_type.

IMPORTANT: This must stay in sync with generate_data.py's ELIGIBILITY dict.
The test_policy.py drift-detection test verifies this by comparing against
hard-coded expected values (not a live import from M1, since M1 is locked).

Eligibility is keyed on failure_type, NEVER event_type.
M3 may REMOVE actions from this set (via safety rules).
M3 may NEVER ADD an action that isn't listed here.
"""

# Exact copy from generate_data.py (M1, seed=42, LOCKED)
ELIGIBILITY = {
    "temporary_bank_decline": {"retry", "payment_link", "reminder", "discount", "wait", "close", "escalate"},
    "network_timeout":        {"retry", "payment_link", "reminder", "wait", "close", "escalate"},
    "card_expired":           {"payment_link", "reminder", "discount", "wait", "close", "escalate"},
    "risk_block":             {"wait", "close", "escalate"},
    "customer_abandoned":     {"payment_link", "reminder", "discount", "wait", "close", "escalate"},
    "subscription_mandate_fail": {"payment_link", "reminder", "discount", "wait", "close", "escalate"},
    "insufficient_funds":     {"retry", "reminder", "payment_link", "wait", "close", "escalate"},
}

# All known actions
ALL_ACTIONS = {"retry", "payment_link", "reminder", "discount", "wait", "close", "escalate"}

# Contact actions — actions that involve reaching out to / incentivizing the customer
CONTACT_ACTIONS = {"reminder", "payment_link", "discount"}

# Automated financial recovery actions — actions blocked by amount ceiling / high-risk block
AUTOMATED_RECOVERY_ACTIONS = {"retry", "payment_link", "reminder", "discount"}


def get_eligible_actions(failure_type):
    """Return the set of eligible actions for a failure_type.
    Raises ValueError if failure_type is unknown."""
    if failure_type not in ELIGIBILITY:
        raise ValueError(f"Unknown failure_type: {failure_type}")
    return ELIGIBILITY[failure_type].copy()
