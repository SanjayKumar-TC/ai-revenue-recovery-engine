"""
M8: FastAPI transport tests.

Run from project root:
    python -m api.test_api

Uses isolated temporary audit DBs. Never writes to ml/audit/audit_trail.db.
"""

from __future__ import annotations

import gc
import json
import os
import sqlite3
import sys
import tempfile

from fastapi.testclient import TestClient

from api.main import create_app
from ml.audit.audit_writer import DEFAULT_DB_PATH

PASS_COUNT = 0
FAIL_COUNT = 0

REQUIRED_DECIDE_FIELDS = {
    "transaction_id",
    "trace_id",
    "selected_action",
    "decision_type",
    "decision_reason",
    "escalation_required",
    "terminal",
    "selected_ev",
    "selected_probability",
    "policy_version",
    "communication",
}

FORBIDDEN_RESPONSE_KEYS = {
    "action_analysis",
    "blocked_actions",
    "allowed_actions",
    "latent_score",
    "true_prob_HIDDEN",
    "blocked_reasons",
}

FORBIDDEN_REQUEST_FIELDS = [
    ("action", "retry"),
    ("selected_action", "retry"),
    ("selected_ev", 1.0),
    ("selected_probability", 0.5),
    ("rules_fired", ["x"]),
    ("policy_version", "v9"),
    ("model_version", "hack"),
    ("decision_engine_version", "v9"),
    ("allowed_actions", ["retry"]),
    ("blocked_actions", {"retry": ["x"]}),
    ("latent_score", 0.1),
    ("true_prob_HIDDEN", 0.9),
]


def _base_payload(**overrides):
    body = {
        "transaction_id": "txn_m8_001",
        "failure_type": "temporary_bank_decline",
        "amount": 2000.0,
        "attempt_number": 1,
        "risk_score": 0.15,
        "contact_fatigue": 0.1,
        "hours_since_failure": 6.0,
        "current_discount_percent": 10.0,
        "customer_segment": "b2c_new",
        "already_recovered": False,
        "customer_name": "Ananya Sharma",
        "communication_channel": "email",
        "payment_link_url": "https://checkout.example.com/pay/txn_m8_001",
    }
    body.update(overrides)
    return body


def _make_temp_db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="test_m8_audit_")
    os.close(fd)
    if os.path.exists(path):
        os.remove(path)
    return path


def _safe_remove(path: str):
    gc.collect()
    if not path:
        return
    for suffix in ("", "-journal", "-wal", "-shm"):
        candidate = path + suffix
        if os.path.exists(candidate):
            try:
                os.remove(candidate)
            except OSError:
                pass


def _client(db_path: str) -> TestClient:
    return TestClient(create_app(audit_db_path=db_path))


def _report(test_num, test_name, passed, details=""):
    global PASS_COUNT, FAIL_COUNT
    status = "PASS" if passed else "FAIL"
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
    print(f"\n  Test {test_num}: {test_name} - {status}")
    if details:
        for line in details.split("\n"):
            print(f"    {line}")
    return passed


def _json_blob(obj) -> str:
    return json.dumps(obj, default=str)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_01_valid_decide_returns_required_fields():
    db_path = _make_temp_db_path()
    try:
        with _client(db_path) as client:
            resp = client.post("/decide", json=_base_payload())
        body = resp.json() if resp.content else {}
        comm = body.get("communication") or {}
        passed = (
            resp.status_code == 200
            and REQUIRED_DECIDE_FIELDS <= set(body.keys())
            and {"sendable", "channel", "message_body", "fallback_used"} <= set(comm.keys())
            and body.get("trace_id") is not None
        )
        return _report(
            1,
            "VALID /decide RETURNS 200 WITH REQUIRED FIELDS",
            passed,
            f"status={resp.status_code} keys={list(body.keys())} action={body.get('selected_action')}",
        )
    finally:
        _safe_remove(db_path)


def test_02_m4_selected_action_is_authoritative():
    db_path = _make_temp_db_path()
    try:
        from ml.decision.decision_engine import make_decision, load_model
        from api.pipeline import _build_transaction

        payload = _base_payload()
        model, _ = load_model()
        expected = make_decision(_build_transaction(payload), model_pipeline=model)

        with _client(db_path) as client:
            resp = client.post("/decide", json=payload)
        body = resp.json()
        passed = (
            resp.status_code == 200
            and body.get("selected_action") == expected["decision"]
            and body.get("decision_type") == expected["decision_type"]
            and body.get("decision_reason") == expected["decision_reason"]
        )
        return _report(
            2,
            "M4 SELECTED ACTION MATCHES RESPONSE (NO RE-RANK)",
            passed,
            f"api={body.get('selected_action')} m4={expected['decision']}",
        )
    finally:
        _safe_remove(db_path)


def test_03_policy_safety_block():
    db_path = _make_temp_db_path()
    try:
        payload = _base_payload(
            transaction_id="txn_m8_risk",
            failure_type="risk_block",
        )
        with _client(db_path) as client:
            resp = client.post("/decide", json=payload)
        body = resp.json()
        action = body.get("selected_action")
        passed = (
            resp.status_code == 200
            and action in {"wait", "close", "escalate"}
            and action not in {"retry", "payment_link", "reminder", "discount"}
        )
        return _report(
            3,
            "POLICY SAFETY BLOCK (risk_block) BEHAVES AS M3 DICTATES",
            passed,
            f"status={resp.status_code} action={action} escalation={body.get('escalation_required')}",
        )
    finally:
        _safe_remove(db_path)


def test_04_sendable_communication():
    db_path = _make_temp_db_path()
    try:
        payload = _base_payload(transaction_id="txn_m8_send")
        with _client(db_path) as client:
            resp = client.post("/decide", json=payload)
        body = resp.json()
        comm = body.get("communication") or {}
        passed = (
            resp.status_code == 200
            and body.get("selected_action") == "discount"
            and comm.get("sendable") is True
            and isinstance(comm.get("message_body"), str)
            and len(comm.get("message_body") or "") > 0
            and comm.get("fallback_used") is False
        )
        return _report(
            4,
            "SENDABLE ACTION GENERATES COMMUNICATION",
            passed,
            f"action={body.get('selected_action')} sendable={comm.get('sendable')} fallback={comm.get('fallback_used')}",
        )
    finally:
        _safe_remove(db_path)


def test_05_nonsendable_no_fabricated_body():
    db_path = _make_temp_db_path()
    try:
        payload = _base_payload(
            transaction_id="txn_m8_wait",
            failure_type="risk_block",
        )
        with _client(db_path) as client:
            resp = client.post("/decide", json=payload)
        body = resp.json()
        comm = body.get("communication") or {}
        passed = (
            resp.status_code == 200
            and body.get("selected_action") in {"wait", "close", "escalate", "no_action_required"}
            and comm.get("sendable") is False
            and comm.get("message_body") is None
            and comm.get("fallback_used") is False
            and comm.get("channel") is None
        )
        return _report(
            5,
            "NON-SENDABLE ACTION DOES NOT FABRICATE MESSAGE BODY",
            passed,
            f"action={body.get('selected_action')} comm={comm}",
        )
    finally:
        _safe_remove(db_path)


def test_06_audit_round_trip():
    db_path = _make_temp_db_path()
    try:
        payload = _base_payload(transaction_id="txn_m8_audit")
        with _client(db_path) as client:
            decide_resp = client.post("/decide", json=payload)
            decide_body = decide_resp.json()
            audit_resp = client.get("/audit/txn_m8_audit")
            audit_body = audit_resp.json()
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    "SELECT rules_fired FROM decisions WHERE transaction_id = ?",
                    ("txn_m8_audit",),
                ).fetchone()
            finally:
                conn.close()
        records = audit_body.get("records") or []
        rules = json.loads(row[0]) if row else None
        passed = (
            decide_resp.status_code == 200
            and audit_resp.status_code == 200
            and records
            and records[0]["transaction_id"] == "txn_m8_audit"
            and records[0]["trace_id"] == decide_body.get("trace_id")
            and records[0]["selected_action"] == decide_body.get("selected_action")
            and records[0]["rules_fired"] == []
            and rules == []
            and os.path.abspath(db_path) != os.path.abspath(DEFAULT_DB_PATH)
        )
        return _report(
            6,
            "/decide WRITES M7 RECORD; GET /audit ROUND-TRIPS",
            passed,
            f"decide={decide_resp.status_code} audit={audit_resp.status_code} rules={rules}",
        )
    finally:
        _safe_remove(db_path)


def test_07_malformed_request_422():
    db_path = _make_temp_db_path()
    try:
        with _client(db_path) as client:
            missing = client.post("/decide", json={"transaction_id": "x"})
            bad_type = client.post("/decide", json=_base_payload(amount="not-a-number"))
        passed = missing.status_code == 422 and bad_type.status_code == 422
        return _report(
            7,
            "MALFORMED REQUEST BODY -> 422",
            passed,
            f"missing={missing.status_code} bad_type={bad_type.status_code}",
        )
    finally:
        _safe_remove(db_path)


def test_08_unknown_failure_type_400():
    db_path = _make_temp_db_path()
    try:
        payload = _base_payload(
            transaction_id="txn_m8_unknown_ft",
            failure_type="not_a_real_failure",
        )
        with _client(db_path) as client:
            resp = client.post("/decide", json=payload)
        text = resp.text.lower()
        passed = (
            resp.status_code == 400
            and "traceback" not in text
            and "sqlite" not in text
        )
        return _report(
            8,
            "UNKNOWN failure_type -> 400",
            passed,
            f"status={resp.status_code} body={resp.text[:200]}",
        )
    finally:
        _safe_remove(db_path)


def test_09_health():
    db_path = _make_temp_db_path()
    try:
        with _client(db_path) as client:
            resp = client.get("/health")
        passed = resp.status_code == 200 and resp.json().get("status") == "ok"
        return _report(9, "GET /health -> 200", passed, f"status={resp.status_code} body={resp.json()}")
    finally:
        _safe_remove(db_path)


def test_10_audit_not_found_404():
    db_path = _make_temp_db_path()
    try:
        with _client(db_path) as client:
            resp = client.get("/audit/does_not_exist")
        passed = resp.status_code == 404
        return _report(10, "GET /audit MISSING TRANSACTION -> 404", passed, f"status={resp.status_code}")
    finally:
        _safe_remove(db_path)


def test_11_deterministic_decision():
    db_path = _make_temp_db_path()
    try:
        payload = _base_payload(transaction_id="txn_m8_det")
        with _client(db_path) as client:
            a = client.post("/decide", json=payload).json()
            b = client.post("/decide", json=payload).json()
        skip = {"trace_id"}
        a_cmp = {k: v for k, v in a.items() if k not in skip}
        b_cmp = {k: v for k, v in b.items() if k not in skip}
        passed = a_cmp == b_cmp and a.get("selected_action") == b.get("selected_action")
        return _report(
            11,
            "IDENTICAL INPUT YIELDS IDENTICAL DECISION (TRACE_ID EXCLUDED)",
            passed,
            f"action={a.get('selected_action')} traces=({a.get('trace_id')}, {b.get('trace_id')})",
        )
    finally:
        _safe_remove(db_path)


def test_12_no_internal_fields_leaked():
    db_path = _make_temp_db_path()
    try:
        with _client(db_path) as client:
            resp = client.post("/decide", json=_base_payload(transaction_id="txn_m8_leak"))
        body = resp.json()
        blob = _json_blob(body)
        leaked_keys = [k for k in FORBIDDEN_RESPONSE_KEYS if k in body]
        leaked_text = [k for k in ("true_prob_HIDDEN", "latent_score", "action_analysis") if k in blob]
        passed = resp.status_code == 200 and not leaked_keys and not leaked_text
        return _report(
            12,
            "RESPONSE CONTAINS NO HIDDEN/INTERNAL FIELDS",
            passed,
            f"leaked_keys={leaked_keys} leaked_text={leaked_text}",
        )
    finally:
        _safe_remove(db_path)


def test_13_already_recovered():
    db_path = _make_temp_db_path()
    try:
        payload = _base_payload(
            transaction_id="txn_m8_recovered",
            already_recovered=True,
        )
        with _client(db_path) as client:
            resp = client.post("/decide", json=payload)
        body = resp.json()
        comm = body.get("communication") or {}
        passed = (
            resp.status_code == 200
            and body.get("selected_action") == "no_action_required"
            and body.get("terminal") is True
            and body.get("decision_reason") == "already_recovered_terminal"
            and comm.get("sendable") is False
            and comm.get("message_body") is None
        )
        return _report(
            13,
            "already_recovered=true HANDLED PER M3/M4",
            passed,
            f"action={body.get('selected_action')} terminal={body.get('terminal')} reason={body.get('decision_reason')}",
        )
    finally:
        _safe_remove(db_path)


def test_14_high_value_escalation():
    db_path = _make_temp_db_path()
    try:
        payload = _base_payload(
            transaction_id="txn_m8_highval",
            amount=75000.0,
        )
        with _client(db_path) as client:
            resp = client.post("/decide", json=payload)
        body = resp.json()
        passed = (
            resp.status_code == 200
            and body.get("escalation_required") is True
            and body.get("selected_action") not in {"retry", "payment_link", "reminder", "discount"}
        )
        return _report(
            14,
            "HIGH-VALUE TRANSACTION SETS escalation_required=true",
            passed,
            f"action={body.get('selected_action')} escalation={body.get('escalation_required')} terminal={body.get('terminal')}",
        )
    finally:
        _safe_remove(db_path)


def test_15_m6_fallback():
    db_path = _make_temp_db_path()
    try:
        payload = _base_payload(
            transaction_id="txn_m8_fallback",
            failure_type="card_expired",
            payment_link_url=None,
        )
        payload.pop("payment_link_url")
        with _client(db_path) as client:
            resp = client.post("/decide", json=payload)
        body = resp.json()
        comm = body.get("communication") or {}
        passed = (
            resp.status_code == 200
            and body.get("selected_action") == "payment_link"
            and comm.get("fallback_used") is True
            and comm.get("sendable") is False
            and isinstance(comm.get("message_body"), str)
            and "suppressed" in (comm.get("message_body") or "").lower()
        )
        return _report(
            15,
            "M6 FALLBACK (MISSING PAYMENT LINK) -> fallback_used=true",
            passed,
            f"action={body.get('selected_action')} comm={comm}",
        )
    finally:
        _safe_remove(db_path)


def test_16_forbidden_request_fields_rejected():
    db_path = _make_temp_db_path()
    try:
        statuses = []
        with _client(db_path) as client:
            for field, value in FORBIDDEN_REQUEST_FIELDS:
                payload = _base_payload()
                payload[field] = value
                resp = client.post("/decide", json=payload)
                statuses.append((field, resp.status_code))
        passed = all(code == 422 for _, code in statuses)
        return _report(
            16,
            "FORBIDDEN REQUEST FIELDS CAUSE VALIDATION ERROR",
            passed,
            " ".join(f"{f}={c}" for f, c in statuses),
        )
    finally:
        _safe_remove(db_path)


def test_17_m7_write_failure_still_returns_decision():
    db_path = _make_temp_db_path()
    try:
        application = create_app(audit_db_path=db_path)

        from api import pipeline as pipeline_mod
        original = pipeline_mod.write_record

        def _boom(*args, **kwargs):
            raise sqlite3.OperationalError("injected audit failure")

        pipeline_mod.write_record = _boom
        try:
            with TestClient(application) as client:
                resp = client.post("/decide", json=_base_payload(transaction_id="txn_m8_auditfail"))
            body = resp.json()
            text = resp.text.lower()
            passed = (
                resp.status_code == 200
                and body.get("selected_action") is not None
                and body.get("trace_id") is None
                and "operationalerror" not in text
                and "injected audit failure" not in text
            )
        finally:
            pipeline_mod.write_record = original
        return _report(
            17,
            "M7 WRITE FAILURE STILL RETURNS 200 WITH null trace_id",
            passed,
            f"status={resp.status_code} trace_id={body.get('trace_id')} action={body.get('selected_action')}",
        )
    finally:
        _safe_remove(db_path)


def main():
    print("=" * 70)
    print("M8 FastAPI Backend - Test Suite")
    print("=" * 70)
    tests = [
        test_01_valid_decide_returns_required_fields,
        test_02_m4_selected_action_is_authoritative,
        test_03_policy_safety_block,
        test_04_sendable_communication,
        test_05_nonsendable_no_fabricated_body,
        test_06_audit_round_trip,
        test_07_malformed_request_422,
        test_08_unknown_failure_type_400,
        test_09_health,
        test_10_audit_not_found_404,
        test_11_deterministic_decision,
        test_12_no_internal_fields_leaked,
        test_13_already_recovered,
        test_14_high_value_escalation,
        test_15_m6_fallback,
        test_16_forbidden_request_fields_rejected,
        test_17_m7_write_failure_still_returns_decision,
    ]
    for fn in tests:
        fn()
    print("=" * 70)
    print(f"RESULTS: {PASS_COUNT} passed, {FAIL_COUNT} failed, {PASS_COUNT + FAIL_COUNT} total")
    print("=" * 70)
    if FAIL_COUNT:
        sys.exit(1)


if __name__ == "__main__":
    main()
