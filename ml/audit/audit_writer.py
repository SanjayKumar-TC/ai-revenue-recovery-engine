"""
M7: Audit Writer Subsystem
==========================
Append-only SQLite storage layer for recording authoritative decisions
produced by the M3/M4/M6 pipeline.

M7 is purely observational and does not modify, override, or hook into
upstream decision layers.
"""

from datetime import datetime, timezone
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional
import uuid

# ---------------------------------------------------------------------------
# Default Database Path (Absolute, independent of cwd)
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "audit_trail.db")
)

# ---------------------------------------------------------------------------
# Required Fields Schema
# ---------------------------------------------------------------------------

REQUIRED_AUDIT_FIELDS: List[str] = [
    "transaction_id",
    "selected_action",
    "decision_type",
    "decision_reason",
    "policy_version",
    "model_version",
    "decision_engine_version",
    "rules_fired",
    "escalation_required",
    "terminal",
    "m6_sendable",
    "m6_fallback_used",
]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS decisions (
    trace_id TEXT PRIMARY KEY NOT NULL,
    timestamp TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    selected_action TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    decision_reason TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    model_version TEXT NOT NULL,
    decision_engine_version TEXT NOT NULL,
    rules_fired TEXT NOT NULL,
    escalation_required INTEGER NOT NULL,
    terminal INTEGER NOT NULL,
    selected_ev REAL,
    selected_probability REAL,
    m6_sendable INTEGER NOT NULL,
    m6_channel TEXT,
    m6_fallback_used INTEGER NOT NULL
)
"""

INSERT_DECISION_SQL = """
INSERT INTO decisions (
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
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


# ---------------------------------------------------------------------------
# Public Functions
# ---------------------------------------------------------------------------

def initialise_db(db_path: Optional[str] = None) -> str:
    """
    Create the audit database and 'decisions' table if they do not exist.
    Safe to call multiple times (idempotent).

    Parameters
    ----------
    db_path : str, optional
        Target SQLite database path. Defaults to ml/audit/audit_trail.db
        resolved as an absolute path.

    Returns
    -------
    str
        The resolved database file path.
    """
    resolved_path = os.path.abspath(db_path) if db_path else DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

    conn = sqlite3.connect(resolved_path)
    try:
        cursor = conn.cursor()
        cursor.execute(CREATE_TABLE_SQL)
        conn.commit()
    finally:
        conn.close()

    return resolved_path


def write_record(record: Dict[str, Any], db_path: Optional[str] = None) -> str:
    """
    Write a single decision record to the append-only audit trail.

    Parameters
    ----------
    record : dict
        Flat dictionary containing all required and optional audit fields.
    db_path : str, optional
        Target SQLite database path. Defaults to ml/audit/audit_trail.db.

    Returns
    -------
    str
        The generated or supplied trace_id (UUID4).

    Raises
    ------
    ValueError
        If any required field is missing from the record dictionary.
    sqlite3.IntegrityError
        If a trace_id primary key collision occurs.
    """
    if not isinstance(record, dict):
        raise ValueError("Audit record must be a dictionary.")

    # 1. Validate required fields
    missing_fields = [f for f in REQUIRED_AUDIT_FIELDS if f not in record]
    if missing_fields:
        raise ValueError(
            f"Missing required audit field(s): {missing_fields}. All {REQUIRED_AUDIT_FIELDS} must be provided."
        )

    resolved_path = os.path.abspath(db_path) if db_path else DEFAULT_DB_PATH

    # Ensure database and table exist
    initialise_db(resolved_path)

    # 2. Extract and format fields
    trace_id = str(record.get("trace_id") or uuid.uuid4())

    raw_ts = record.get("timestamp")
    if raw_ts:
        timestamp = str(raw_ts)
    else:
        # Standard ISO 8601 UTC timestamp ending in 'Z'
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    transaction_id = str(record["transaction_id"])
    selected_action = str(record["selected_action"])
    decision_type = str(record["decision_type"])
    decision_reason = str(record["decision_reason"])
    policy_version = str(record["policy_version"])
    model_version = str(record["model_version"])
    decision_engine_version = str(record["decision_engine_version"])

    # Format rules_fired
    raw_rules = record["rules_fired"]
    if isinstance(raw_rules, (list, tuple)):
        rules_fired = json.dumps(list(raw_rules))
    elif isinstance(raw_rules, str):
        rules_fired = raw_rules
    else:
        rules_fired = json.dumps(raw_rules)

    escalation_required = 1 if record["escalation_required"] else 0
    terminal = 1 if record["terminal"] else 0

    # Optional numerical / text fields
    raw_ev = record.get("selected_ev")
    selected_ev = float(raw_ev) if raw_ev is not None else None

    raw_prob = record.get("selected_probability")
    selected_probability = float(raw_prob) if raw_prob is not None else None

    m6_sendable = 1 if record["m6_sendable"] else 0

    raw_channel = record.get("m6_channel")
    m6_channel = str(raw_channel) if raw_channel is not None else None

    m6_fallback_used = 1 if record["m6_fallback_used"] else 0

    # 3. Append to SQLite
    conn = sqlite3.connect(resolved_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            INSERT_DECISION_SQL,
            (
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
                m6_fallback_used,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return trace_id

