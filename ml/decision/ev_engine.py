"""
M4: Expected Value Engine
==========================
Calculates Expected Net Value for each permitted action.

EV(action) = P(recovery | context, action) × recoverable_amount − intervention_cost

Special cases:
  - close: EV = 0 (permanent non-intervention)
  - discount: recoverable_amount = amount − discount_amount
  - escalate: not scored via ordinary EV (human routing)
"""

from ml.decision.decision_config import ACTION_COSTS, DEFAULT_DISCOUNT_PERCENT


def calculate_ev(action, probability, amount, discount_percent=None):
    """
    Calculate Expected Net Value for a single action.

    Parameters
    ----------
    action : str
    probability : float — P(recovery | context, action) from M2
    amount : float — transaction amount
    discount_percent : float or None — discount percentage if applicable

    Returns
    -------
    dict with:
        action, predicted_probability, recoverable_amount,
        gross_expected_recovery, intervention_cost, discount_amount,
        expected_net_value
    """
    # close: EV = 0, no recovery attempt
    if action == "close":
        return {
            "action": "close",
            "predicted_probability": probability,
            "recoverable_amount": amount,
            "gross_expected_recovery": 0.0,
            "intervention_cost": 0.0,
            "discount_amount": 0.0,
            "expected_net_value": 0.0,
        }

    intervention_cost = ACTION_COSTS.get(action, 0.0)

    # discount: recoverable_amount = amount − discount_amount
    if action == "discount":
        dp = discount_percent if discount_percent is not None else DEFAULT_DISCOUNT_PERCENT
        discount_amount = amount * (dp / 100.0)
        recoverable_amount = amount - discount_amount
    else:
        discount_amount = 0.0
        recoverable_amount = amount

    gross_expected_recovery = probability * recoverable_amount
    expected_net_value = gross_expected_recovery - intervention_cost

    return {
        "action": action,
        "predicted_probability": probability,
        "recoverable_amount": recoverable_amount,
        "gross_expected_recovery": gross_expected_recovery,
        "intervention_cost": intervention_cost,
        "discount_amount": discount_amount,
        "expected_net_value": expected_net_value,
    }


def calculate_ev_for_actions(action_probabilities, amount, discount_percent=None):
    """
    Calculate EV for all provided action-probability pairs.

    Parameters
    ----------
    action_probabilities : dict — {action: probability}
    amount : float
    discount_percent : float or None

    Returns
    -------
    dict — {action: ev_result_dict}
    """
    results = {}
    for action, prob in action_probabilities.items():
        results[action] = calculate_ev(action, prob, amount, discount_percent)
    return results
