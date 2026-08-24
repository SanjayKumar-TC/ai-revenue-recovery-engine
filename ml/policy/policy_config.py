"""
M3: Policy Configuration — Centralized Thresholds
===================================================
All policy thresholds in one place. These are OUR prototype safety
policies, not claims about Razorpay's actual internal rules.

For the prototype, we impose these safety limits. Every threshold
is a named constant, documented, and versioned.
"""

# Policy version — carried on every policy result
POLICY_VERSION = "v1.0"

# ---------------------------------------------------------------------------
# THRESHOLDS
# ---------------------------------------------------------------------------

# Rule 2: Amount ceiling for automated recovery
# Transactions above this amount require human approval (escalate).
MAX_AUTO_RECOVERY_AMOUNT = 50000

# Rule 3: Risk gate — two non-overlapping bands
# risk_score < 0.75                -> normal, no risk-based block
# 0.75 <= risk_score < 0.85       -> mandatory human escalation
# risk_score >= 0.85              -> automated recovery blocked (wait/close/escalate only)
HIGH_RISK_ESCALATION_THRESHOLD = 0.75
HIGH_RISK_BLOCK_THRESHOLD = 0.85

# Rule 4: Maximum automated retries before retry is blocked
MAX_AUTO_RETRIES = 2

# Rule 5: Contact fatigue threshold
# At or above this, ALL customer-contact actions are blocked:
# reminder, payment_link, AND discount
MAX_CONTACT_FATIGUE = 0.80

# Rule 6: Recovery window (hours since failure)
# If elapsed > this, force close + terminal
RECOVERY_WINDOW_HOURS = 48

# Rule 7: Maximum discount percentage allowed
MAX_DISCOUNT_PERCENT = 20
