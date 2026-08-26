"""
M7: Audit Trail Test Suite
==========================
Standalone test suite validating the append-only SQLite audit writer:
- Database initialisation and idempotency
- Schema integrity and table definitions
- Field validations and error handling (12 required fields)
- Deterministic UTC timestamps and UUID4 trace IDs
- Safe JSON serialization of rules_fired
- Boolean flag mapping and optional field NULL preservation
- Append-only multi-record persistence
- Full pipeline realistic fixture round-trip
- Test suite self-reproducibility

Runnable standalone:
    python -m ml.audit.test_audit_trail
"""

from datetime import datetime
import gc
import json
import os
import sqlite3
import sys
import tempfile
from typing import Any, Dict

from ml.audit.audit_writer import (
    DEFAULT_DB_PATH,
    REQUIRED_AUDIT_FIELDS,
    initialise_db,
    write_record,
)

# ---------------------------------------------------------------------------
# Test Reporting Infrastructure
# ---------------------------------------------------------------------------

PASS_COUNT = 0
FAIL_COUNT = 0
TEST_RESULTS = []


def _report(test_num: int, name: str, passed: bool, details: str = "") -> bool:
    global PASS_COUNT, FAIL_COUNT
    status = "PASS" if passed else "FAIL"
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1

    TEST_RESULTS.append({"test_num": test_num, "name": name, "passed": passed, "details": details})
    print(f"[Test {test_num:02d}] {name}: {status}")
    if details:
        for line in details.strip().split("\n"):
            print(f"  {line}")
    return passed


def _make_temp_db_path() -> str:
    """Create a temporary database path for isolated test execution."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="test_audit_")
    os.close(fd)
    if os.path.exists(path):
        os.remove(path)
    return path


def _safe_remove(path: str):
    """Deterministically remove temporary SQLite test file on Windows."""
    gc.collect()
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _base_valid_record() -> Dict[str, Any]:
    """Produce a minimal valid synthetic audit record."""
    return {
        "transaction_id": "txn_test_100",
        "selected_action": "retry",
        "decision_type": "ev_optimization",
        "decision_reason": "highest_expected_net_value",
        "policy_version": "v1.0",
        "model_version": "logistic_regression_v1",
        "decision_engine_version": "v1.0",
        "rules_fired": ["retry_cap_reached"],
        "escalation_required": False,
        "terminal": False,
        "selected_ev": 450.0,
        "selected_probability": 0.45,
        "m6_sendable": True,
        "m6_channel": "email",
        "m6_fallback_used": False,
    }


# ===========================================================================
# Mandatory Tests (1 - 15)
# ===========================================================================

def test_1_initialise_db_and_table_created(silent: bool = False):
    """Test 1: INITIALISE — DB AND TABLE CREATED"""
    db_path = _make_temp_db_path()
    try:
        resolved = initialise_db(db_path)
        exists = os.path.exists(resolved)

        conn = sqlite3.connect(resolved)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='decisions';"
            )
            table_row = cursor.fetchone()
            has_table = table_row is not None

            cursor.execute("PRAGMA table_info(decisions);")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
        finally:
            conn.close()

        expected_columns = {
            "trace_id": "TEXT",
            "timestamp": "TEXT",
            "transaction_id": "TEXT",
            "selected_action": "TEXT",
            "decision_type": "TEXT",
            "decision_reason": "TEXT",
            "policy_version": "TEXT",
            "model_version": "TEXT",
            "decision_engine_version": "TEXT",
            "rules_fired": "TEXT",
            "escalation_required": "INTEGER",
            "terminal": "INTEGER",
            "selected_ev": "REAL",
            "selected_probability": "REAL",
            "m6_sendable": "INTEGER",
            "m6_channel": "TEXT",
            "m6_fallback_used": "INTEGER",
        }
        all_cols_match = expected_columns.items() <= columns.items()

        passed = exists and has_table and all_cols_match
        if not silent:
            return _report(
                1,
                "INITIALISE — DB AND TABLE CREATED",
                passed,
                f"exists={exists}, table_found={has_table}, cols_match={all_cols_match}",
            )
        return passed
    finally:
        _safe_remove(db_path)


def test_2_write_minimal_valid_record(silent: bool = False):
    """Test 2: WRITE MINIMAL VALID RECORD"""
    db_path = _make_temp_db_path()
    try:
        rec = _base_valid_record()
        trace_id = write_record(rec, db_path=db_path)
        has_trace = bool(trace_id and isinstance(trace_id, str))

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM decisions WHERE trace_id = ?", (trace_id,))
            row = cursor.fetchone()
        finally:
            conn.close()

        row_exists = row is not None
        passed = (
            has_trace
            and row_exists
            and row[0] == trace_id
            and row[2] == "txn_test_100"
            and row[3] == "retry"
            and row[4] == "ev_optimization"
            and row[10] == 0
            and row[11] == 0
            and row[14] == 1
            and row[15] == "email"
            and row[16] == 0
        )
        if not silent:
            return _report(
                2,
                "WRITE MINIMAL VALID RECORD",
                passed,
                f"trace_id={trace_id}, row_found={row_exists}",
            )
        return passed
    finally:
        _safe_remove(db_path)


def test_3_trace_id_uniqueness(silent: bool = False):
    """Test 3: TRACE ID UNIQUENESS"""
    db_path = _make_temp_db_path()
    try:
        trace_ids = []
        for i in range(100):
            rec = _base_valid_record()
            rec["transaction_id"] = f"txn_unique_{i}"
            t_id = write_record(rec, db_path=db_path)
            trace_ids.append(t_id)

        distinct_count = len(set(trace_ids))
        passed = len(trace_ids) == 100 and distinct_count == 100

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM decisions;")
            db_count = cursor.fetchone()[0]
        finally:
            conn.close()

        passed = passed and (db_count == 100)
        if not silent:
            return _report(
                3,
                "TRACE ID UNIQUENESS",
                passed,
                f"written=100, distinct_ids={distinct_count}, db_count={db_count}",
            )
        return passed
    finally:
        _safe_remove(db_path)


def test_4_timestamp_format(silent: bool = False):
    """Test 4: TIMESTAMP FORMAT"""
    db_path = _make_temp_db_path()
    try:
        rec = _base_valid_record()
        rec.pop("timestamp", None)
        trace_id = write_record(rec, db_path=db_path)

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT timestamp FROM decisions WHERE trace_id = ?", (trace_id,))
            ts_str = cursor.fetchone()[0]
        finally:
            conn.close()

        ends_with_z = ts_str.endswith("Z")
        ts_clean = ts_str[:-1] if ends_with_z else ts_str
        dt = datetime.fromisoformat(ts_clean)
        is_valid_iso = dt is not None

        passed = ends_with_z and is_valid_iso
        if not silent:
            return _report(
                4,
                "TIMESTAMP FORMAT",
                passed,
                f"timestamp='{ts_str}', ends_with_z={ends_with_z}, valid_iso={is_valid_iso}",
            )
        return passed
    finally:
        _safe_remove(db_path)


def test_5_rules_fired_list_input(silent: bool = False):
    """Test 5: RULES FIRED — LIST INPUT"""
    db_path = _make_temp_db_path()
    try:
        original_rules = ["retry_cap_reached", "contact_fatigue_limit"]
        rec = _base_valid_record()
        rec["rules_fired"] = original_rules
        trace_id = write_record(rec, db_path=db_path)

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT rules_fired FROM decisions WHERE trace_id = ?", (trace_id,))
            stored_rules_str = cursor.fetchone()[0]
        finally:
            conn.close()

        deserialized = json.loads(stored_rules_str)
        passed = (deserialized == original_rules) and isinstance(stored_rules_str, str)
        if not silent:
            return _report(
                5,
                "RULES FIRED — LIST INPUT",
                passed,
                f"stored='{stored_rules_str}', round_trip={deserialized == original_rules}",
            )
        return passed
    finally:
        _safe_remove(db_path)


def test_6_rules_fired_empty_list(silent: bool = False):
    """Test 6: RULES FIRED — EMPTY LIST"""
    db_path = _make_temp_db_path()
    try:
        rec = _base_valid_record()
        rec["rules_fired"] = []
        trace_id = write_record(rec, db_path=db_path)

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT rules_fired FROM decisions WHERE trace_id = ?", (trace_id,))
            stored_rules_str = cursor.fetchone()[0]
        finally:
            conn.close()

        passed = stored_rules_str == "[]"
        if not silent:
            return _report(
                6,
                "RULES FIRED — EMPTY LIST",
                passed,
                f"stored='{stored_rules_str}'",
            )
        return passed
    finally:
        _safe_remove(db_path)


def test_7_null_optional_fields(silent: bool = False):
    """Test 7: NULL OPTIONAL FIELDS"""
    db_path = _make_temp_db_path()
    try:
        rec = _base_valid_record()
        rec["selected_ev"] = None
        rec["selected_probability"] = None
        rec["m6_channel"] = None

        trace_id = write_record(rec, db_path=db_path)

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT selected_ev, selected_probability, m6_channel FROM decisions WHERE trace_id = ?",
                (trace_id,),
            )
            row = cursor.fetchone()
        finally:
            conn.close()

        ev_null = row[0] is None
        prob_null = row[1] is None
        chan_null = row[2] is None
        passed = ev_null and prob_null and chan_null

        if not silent:
            return _report(
                7,
                "NULL OPTIONAL FIELDS",
                passed,
                f"ev_null={ev_null}, prob_null={prob_null}, chan_null={chan_null}",
            )
        return passed
    finally:
        _safe_remove(db_path)


def test_8_missing_required_field_raises_value_error(silent: bool = False):
    """Test 8: MISSING REQUIRED FIELD — RAISES VALUE ERROR"""
    db_path = _make_temp_db_path()
    try:
        # Explicitly initialize temporary DB so table exists before testing failure to write
        initialise_db(db_path)

        rec = _base_valid_record()
        rec.pop("transaction_id")

        error_raised = False
        try:
            write_record(rec, db_path=db_path)
        except ValueError:
            error_raised = True

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM decisions;")
            row_count = cursor.fetchone()[0]
        finally:
            conn.close()

        passed = error_raised and (row_count == 0)
        if not silent:
            return _report(
                8,
                "MISSING REQUIRED FIELD — RAISES VALUE ERROR",
                passed,
                f"ValueError_raised={error_raised}, db_rows_written={row_count}",
            )
        return passed
    finally:
        _safe_remove(db_path)


def test_9_missing_required_field_each_field(silent: bool = False):
    """Test 9: MISSING REQUIRED FIELD — EACH FIELD"""
    db_path = _make_temp_db_path()
    try:
        # Explicitly initialize temporary DB so table exists before testing failure to write
        initialise_db(db_path)

        sub_results = []
        for field in REQUIRED_AUDIT_FIELDS:
            rec = _base_valid_record()
            rec.pop(field)

            raised = False
            try:
                write_record(rec, db_path=db_path)
            except ValueError:
                raised = True
            sub_results.append((field, raised))

        all_raised = all(r[1] for r in sub_results)

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM decisions;")
            row_count = cursor.fetchone()[0]
        finally:
            conn.close()

        passed = all_raised and (row_count == 0) and len(sub_results) == 12
        if not silent:
            return _report(
                9,
                "MISSING REQUIRED FIELD — EACH FIELD",
                passed,
                f"checked_fields=12, all_raised_ValueError={all_raised}, db_rows={row_count}",
            )
        return passed
    finally:
        _safe_remove(db_path)



def test_10_append_only_multiple_writes(silent: bool = False):
    """Test 10: APPEND ONLY — MULTIPLE WRITES"""
    db_path = _make_temp_db_path()
    try:
        t_ids = []
        for i in range(3):
            rec = _base_valid_record()
            rec["transaction_id"] = f"txn_seq_{i}"
            t_id = write_record(rec, db_path=db_path)
            t_ids.append(t_id)

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT trace_id, transaction_id FROM decisions ORDER BY rowid ASC;")
            rows = cursor.fetchall()
        finally:
            conn.close()

        count_matches = len(rows) == 3
        ids_match = [r[0] for r in rows] == t_ids
        txns_match = [r[1] for r in rows] == ["txn_seq_0", "txn_seq_1", "txn_seq_2"]

        passed = count_matches and ids_match and txns_match
        if not silent:
            return _report(
                10,
                "APPEND ONLY — MULTIPLE WRITES",
                passed,
                f"count={len(rows)}, ids_match={ids_match}, txns_match={txns_match}",
            )
        return passed
    finally:
        _safe_remove(db_path)


def test_11_idempotent_initialise(silent: bool = False):
    """Test 11: IDEMPOTENT INITIALISE"""
    db_path = _make_temp_db_path()
    try:
        p1 = initialise_db(db_path)
        write_record(_base_valid_record(), db_path=db_path)
        p2 = initialise_db(db_path)

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM decisions;")
            row_count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='decisions';"
            )
            table_count = cursor.fetchone()[0]
        finally:
            conn.close()

        passed = (p1 == p2) and (table_count == 1) and (row_count == 1)
        if not silent:
            return _report(
                11,
                "IDEMPOTENT INITIALISE",
                passed,
                f"tables_count={table_count}, rows_preserved={row_count}",
            )
        return passed
    finally:
        _safe_remove(db_path)


def test_12_escalation_and_terminal_flags(silent: bool = False):
    """Test 12: ESCALATION AND TERMINAL FLAGS"""
    db_path = _make_temp_db_path()
    try:
        rec_a = _base_valid_record()
        rec_a["escalation_required"] = True
        rec_a["terminal"] = False
        t_a = write_record(rec_a, db_path=db_path)

        rec_b = _base_valid_record()
        rec_b["escalation_required"] = False
        rec_b["terminal"] = True
        t_b = write_record(rec_b, db_path=db_path)

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT trace_id, escalation_required, terminal FROM decisions WHERE trace_id IN (?, ?);",
                (t_a, t_b),
            )
            rows = {r[0]: (r[1], r[2]) for r in cursor.fetchall()}
        finally:
            conn.close()

        match_a = rows[t_a] == (1, 0)
        match_b = rows[t_b] == (0, 1)
        passed = match_a and match_b

        if not silent:
            return _report(
                12,
                "ESCALATION AND TERMINAL FLAGS",
                passed,
                f"case_a_matches={match_a} (got {rows.get(t_a)}), case_b_matches={match_b} (got {rows.get(t_b)})",
            )
        return passed
    finally:
        _safe_remove(db_path)


def test_13_m6_not_called_defaults(silent: bool = False):
    """Test 13: M6 NOT CALLED — DEFAULTS"""
    db_path = _make_temp_db_path()
    try:
        rec = _base_valid_record()
        rec["m6_sendable"] = 0
        rec["m6_channel"] = None
        rec["m6_fallback_used"] = 0
        t_id = write_record(rec, db_path=db_path)

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT m6_sendable, m6_channel, m6_fallback_used FROM decisions WHERE trace_id = ?",
                (t_id,),
            )
            row = cursor.fetchone()
        finally:
            conn.close()

        passed = row[0] == 0 and row[1] is None and row[2] == 0
        if not silent:
            return _report(
                13,
                "M6 NOT CALLED — DEFAULTS",
                passed,
                f"m6_sendable={row[0]}, m6_channel={row[1]}, m6_fallback_used={row[2]}",
            )
        return passed
    finally:
        _safe_remove(db_path)


def test_14_full_pipeline_record_realistic_fixture(silent: bool = False):
    """Test 14: FULL PIPELINE RECORD — REALISTIC FIXTURE"""
    db_path = _make_temp_db_path()
    try:
        realistic_rec = {
            "transaction_id": "txn_test_001",
            "selected_action": "discount",
            "decision_type": "ev_optimization",
            "decision_reason": "highest_expected_net_value",
            "policy_version": "v1.0",
            "model_version": "logistic_regression_v1",
            "decision_engine_version": "v1.0",
            "rules_fired": ["retry_cap_reached"],
            "escalation_required": False,
            "terminal": False,
            "selected_ev": 537.57,
            "selected_probability": 0.315,
            "m6_sendable": True,
            "m6_channel": "email",
            "m6_fallback_used": False,
        }
        trace_id = write_record(realistic_rec, db_path=db_path)

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM decisions WHERE trace_id = ?", (trace_id,))
            row = cursor.fetchone()
        finally:
            conn.close()

        checks = [
            row[0] == trace_id,
            bool(row[1] and row[1].endswith("Z")),
            row[2] == "txn_test_001",
            row[3] == "discount",
            row[4] == "ev_optimization",
            row[5] == "highest_expected_net_value",
            row[6] == "v1.0",
            row[7] == "logistic_regression_v1",
            row[8] == "v1.0",
            json.loads(row[9]) == ["retry_cap_reached"],
            row[10] == 0,
            row[11] == 0,
            abs(row[12] - 537.57) < 1e-4,
            abs(row[13] - 0.315) < 1e-4,
            row[14] == 1,
            row[15] == "email",
            row[16] == 0,
        ]
        passed = all(checks)
        if not silent:
            return _report(
                14,
                "FULL PIPELINE RECORD — REALISTIC FIXTURE",
                passed,
                f"all_fields_round_trip={passed}, checks_passed={sum(checks)}/{len(checks)}",
            )
        return passed
    finally:
        _safe_remove(db_path)


def test_15_reproducibility():
    """Test 15: REPRODUCIBILITY"""
    sub_passes = []
    for _ in range(2):
        res = [
            test_1_initialise_db_and_table_created(silent=True),
            test_2_write_minimal_valid_record(silent=True),
            test_3_trace_id_uniqueness(silent=True),
            test_4_timestamp_format(silent=True),
            test_5_rules_fired_list_input(silent=True),
            test_6_rules_fired_empty_list(silent=True),
            test_7_null_optional_fields(silent=True),
            test_8_missing_required_field_raises_value_error(silent=True),
            test_9_missing_required_field_each_field(silent=True),
            test_10_append_only_multiple_writes(silent=True),
            test_11_idempotent_initialise(silent=True),
            test_12_escalation_and_terminal_flags(silent=True),
            test_13_m6_not_called_defaults(silent=True),
            test_14_full_pipeline_record_realistic_fixture(silent=True),
        ]
        sub_passes.append(all(res))

    passed = all(sub_passes)
    return _report(
        15,
        "REPRODUCIBILITY",
        passed,
        f"run_1_pass={sub_passes[0]}, run_2_pass={sub_passes[1]}",
    )


# ===========================================================================
# Runner
# ===========================================================================

def run_all_tests():
    global PASS_COUNT, FAIL_COUNT, TEST_RESULTS
    PASS_COUNT = 0
    FAIL_COUNT = 0
    TEST_RESULTS = []

    print("\n" + "=" * 70)
    print("M7 AUDIT TRAIL — TEST SUITE")
    print("=" * 70)

    test_1_initialise_db_and_table_created()
    test_2_write_minimal_valid_record()
    test_3_trace_id_uniqueness()
    test_4_timestamp_format()
    test_5_rules_fired_list_input()
    test_6_rules_fired_empty_list()
    test_7_null_optional_fields()
    test_8_missing_required_field_raises_value_error()
    test_9_missing_required_field_each_field()
    test_10_append_only_multiple_writes()
    test_11_idempotent_initialise()
    test_12_escalation_and_terminal_flags()
    test_13_m6_not_called_defaults()
    test_14_full_pipeline_record_realistic_fixture()
    test_15_reproducibility()

    print("\n" + "=" * 70)
    print(f"M7 TEST SUMMARY: {PASS_COUNT} PASSED, {FAIL_COUNT} FAILED")
    print("=" * 70 + "\n")

    return FAIL_COUNT == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
