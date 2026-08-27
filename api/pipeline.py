"""
M8 pipeline: M3 policy → M4 decision → conditional M6 → M7 audit.

Does not select or override an action. Field-name mapping from the HTTP
contract onto M3/M4/M6 happens only here.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, Optional

from ml.audit.audit_writer import write_record
from ml.decision.decision_engine import make_decision
from ml.llm.communication import compose_customer_communication
from ml.llm.contracts import ACTIVE_RECOVERY_ACTIONS
from ml.policy.eligibility import ELIGIBILITY
from ml.policy.policy_engine import evaluate_policy

# M2 requires payment_method; it is not part of the M8 request contract.
_DEFAULT_PAYMENT_METHOD = "card"

_AUDIT_SELECT_SQL = """
SELECT
    trace_id,
    timestamp,
    transaction_id,
    selected_action,
    decision_type,
    decision_reason,
    policy_version,
    model_version,
    decision_engine_version,
    rules_fired,
    escalation_required,
    terminal,
    selected_ev,
    selected_probability,
    m6_sendable,
    m6_channel,
    m6_fallback_used
FROM decisions
WHERE transaction_id = ?
ORDER BY timestamp DESC
"""


class UnknownFailureTypeError(ValueError):
    """Raised when the request failure_type is not in the M1/M3 eligibility matrix."""


def _build_transaction(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "transaction_id": payload["transaction_id"],
        "failure_type": payload["failure_type"],
        "amount": payload["amount"],
        "attempt_number": payload["attempt_number"],
        "risk_score": payload["risk_score"],
        "contact_fatigue_score": payload["contact_fatigue"],
        "hours_since_failure": payload["hours_since_failure"],
        "already_recovered": payload["already_recovered"],
        "discount_percent": payload["current_discount_percent"],
        "segment": payload["customer_segment"],
        "payment_method": _DEFAULT_PAYMENT_METHOD,
    }


def _empty_communication() -> Dict[str, Any]:
    return {
        "sendable": False,
        "channel": None,
        "message_body": None,
        "fallback_used": False,
    }


def _map_communication(m6_result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sendable": bool(m6_result.get("sendable", False)),
        "channel": m6_result.get("channel"),
        "message_body": m6_result.get("body"),
        "fallback_used": bool(m6_result.get("fallback_used", False)),
    }


def _build_audit_record(
    decision: Dict[str, Any],
    communication: Dict[str, Any],
    m6_invoked: bool,
) -> Dict[str, Any]:
    if m6_invoked:
        m6_sendable = communication["sendable"]
        m6_channel = communication["channel"]
        m6_fallback_used = communication["fallback_used"]
    else:
        m6_sendable = 0
        m6_channel = None
        m6_fallback_used = 0

    return {
        "transaction_id": decision["transaction_id"],
        "selected_action": decision["decision"],
        "decision_type": decision["decision_type"],
        "decision_reason": decision["decision_reason"],
        "policy_version": decision["policy_version"],
        "model_version": decision.get("model_version", "N/A"),
        "decision_engine_version": decision.get("decision_engine_version", "N/A"),
        "rules_fired": [],
        "escalation_required": decision["escalation_required"],
        "terminal": decision["terminal"],
        "selected_ev": decision.get("selected_ev"),
        "selected_probability": decision.get("selected_probability"),
        "m6_sendable": m6_sendable,
        "m6_channel": m6_channel,
        "m6_fallback_used": m6_fallback_used,
    }


def run_decide_pipeline(
    payload: Dict[str, Any],
    model_pipeline=None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute M3 → M4 → (M6) → M7 and return the HTTP response mapping.

    Raises UnknownFailureTypeError for unknown failure_type (API 400).
    Audit write failures do not block the decision response.
    """
    failure_type = payload["failure_type"]
    if failure_type not in ELIGIBILITY:
        raise UnknownFailureTypeError(failure_type)

    transaction = _build_transaction(payload)

    policy_result = evaluate_policy(transaction)
    decision = make_decision(
        transaction,
        model_pipeline=model_pipeline,
        _policy_result_override=policy_result,
    )
    selected_action = decision["decision"]

    m6_invoked = selected_action in ACTIVE_RECOVERY_ACTIONS
    if m6_invoked:
        approved_context = {
            "transaction_id": payload["transaction_id"],
            "amount": payload["amount"],
            "currency": "INR",
            "customer_segment": payload["customer_segment"],
            "channel": payload.get("communication_channel"),
            "failure_type": payload["failure_type"],
            "approved_discount_percent": payload.get("current_discount_percent"),
            "approved_payment_link": payload.get("payment_link_url"),
            "customer_display_name": payload.get("customer_name"),
        }
        if selected_action != "discount":
            approved_context["approved_discount_percent"] = None
        if selected_action != "payment_link":
            approved_context["approved_payment_link"] = None

        m6_result = compose_customer_communication(decision, approved_context)
        communication = _map_communication(m6_result)
    else:
        communication = _empty_communication()

    audit_record = _build_audit_record(decision, communication, m6_invoked)
    trace_id: Optional[str] = None
    try:
        trace_id = write_record(audit_record, db_path=db_path)
    except Exception:
        trace_id = None

    return {
        "transaction_id": str(decision["transaction_id"]),
        "trace_id": trace_id,
        "selected_action": selected_action,
        "decision_type": decision["decision_type"],
        "decision_reason": decision["decision_reason"],
        "escalation_required": bool(decision["escalation_required"]),
        "terminal": bool(decision["terminal"]),
        "selected_ev": decision.get("selected_ev"),
        "selected_probability": decision.get("selected_probability"),
        "policy_version": decision["policy_version"],
        "communication": communication,
    }


def fetch_audit_records(
    transaction_id: str,
    db_path: Optional[str] = None,
) -> list:
    """Read-only lookup of M7 decisions rows for a transaction_id. Newest first."""
    if not db_path or not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(_AUDIT_SELECT_SQL, (transaction_id,))
        rows = cursor.fetchall()
    finally:
        conn.close()

    records = []
    for row in rows:
        raw_rules = row[9]
        try:
            rules_fired = json.loads(raw_rules) if raw_rules else []
        except (TypeError, json.JSONDecodeError):
            rules_fired = []

        records.append(
            {
                "trace_id": row[0],
                "timestamp": row[1],
                "transaction_id": row[2],
                "selected_action": row[3],
                "decision_type": row[4],
                "decision_reason": row[5],
                "policy_version": row[6],
                "model_version": row[7],
                "decision_engine_version": row[8],
                "rules_fired": rules_fired,
                "escalation_required": bool(row[10]),
                "terminal": bool(row[11]),
                "selected_ev": row[12],
                "selected_probability": row[13],
                "m6_sendable": bool(row[14]),
                "m6_channel": row[15],
                "m6_fallback_used": bool(row[16]),
            }
        )
    return records
