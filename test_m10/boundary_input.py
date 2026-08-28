"""
Section 4.4 — Boundary / malformed / abuse input (Category 4).

Tests each field-level boundary case from the M10 spec against POST /decide
and GET /audit/{transaction_id}. Expects clean 400/422 for invalid input,
clean 200 for technically-valid-but-unusual input, and never an unhandled 500
with a raw traceback.

risk_score valid range confirmed from M3: 0.0 <= risk_score <= 1.0
customer_segment valid values: b2c_new, b2c_returning, b2b
communication_channel valid values: email, sms, whatsapp, none (or omitted)
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    ARTIFACTS,
    scoring_payload,
    start_isolated_server,
    stop_isolated_server,
    write_json,
)


# ──────────────────────────────────────────────────────────────
# Test case definitions
# ──────────────────────────────────────────────────────────────

def _boundary_cases() -> List[Tuple[str, dict, str]]:
    """Return (case_name, payload_overrides, description)."""
    cases = []

    # --- amount ---
    cases.append(("amount_zero", {"amount": 0}, "amount=0"))
    cases.append(("amount_negative", {"amount": -500.0}, "negative amount"))
    cases.append(("amount_1e12", {"amount": 1e12}, "very large amount (1 trillion)"))
    cases.append(("amount_subcent", {"amount": 0.001}, "sub-cent precision"))
    cases.append(("amount_float_max", {"amount": 1e308}, "near float max"))

    # --- attempt_number ---
    cases.append(("attempt_zero", {"attempt_number": 0}, "attempt_number=0"))
    cases.append(("attempt_negative", {"attempt_number": -1}, "negative attempt_number"))
    cases.append(("attempt_very_large", {"attempt_number": 999999}, "very large attempt_number"))

    # --- risk_score (valid range: 0.0 to 1.0 per M3) ---
    cases.append(("risk_below_range", {"risk_score": -0.1}, "risk_score below 0"))
    cases.append(("risk_above_range", {"risk_score": 1.5}, "risk_score above 1"))
    cases.append(("risk_exactly_zero", {"risk_score": 0.0}, "risk_score=0.0 (boundary)"))
    cases.append(("risk_exactly_one", {"risk_score": 1.0}, "risk_score=1.0 (boundary)"))
    cases.append(("risk_large", {"risk_score": 100.0}, "risk_score=100"))

    # --- contact_fatigue ---
    cases.append(("fatigue_negative", {"contact_fatigue": -1.0}, "negative contact_fatigue"))
    cases.append(("fatigue_huge", {"contact_fatigue": 1e6}, "huge contact_fatigue"))

    # --- hours_since_failure ---
    cases.append(("hours_negative", {"hours_since_failure": -10.0}, "negative hours_since_failure"))
    cases.append(("hours_zero", {"hours_since_failure": 0.0}, "hours_since_failure=0"))
    cases.append(("hours_huge", {"hours_since_failure": 1e7}, "huge hours_since_failure"))

    # --- current_discount_percent ---
    cases.append(("discount_negative", {"current_discount_percent": -5.0}, "negative discount"))
    cases.append(("discount_over_100", {"current_discount_percent": 150.0}, "discount > 100%"))
    cases.append(("discount_fractional", {"current_discount_percent": 7.777}, "fractional discount"))

    # --- customer_segment ---
    cases.append(("segment_uppercase", {"customer_segment": "B2C_NEW"}, "uppercase segment"))
    cases.append(("segment_whitespace", {"customer_segment": " b2c_new "}, "whitespace-padded segment"))
    cases.append(("segment_mixed_case", {"customer_segment": "B2c_Returning"}, "mixed case segment"))
    cases.append(("segment_invalid", {"customer_segment": "enterprise"}, "invalid segment value"))

    # --- transaction_id ---
    cases.append(("txn_empty", {"transaction_id": ""}, "empty transaction_id"))
    cases.append(("txn_10k_chars", {"transaction_id": "x" * 10001}, "10,000+ char transaction_id"))
    cases.append(("txn_unicode", {"transaction_id": "交易-🔥-тест"}, "unicode transaction_id"))
    cases.append(("txn_sql_injection", {"transaction_id": "'; DROP TABLE decisions;--"}, "SQL-like transaction_id"))
    cases.append(("txn_path_separators", {"transaction_id": "../../etc/passwd"}, "path separator transaction_id"))
    cases.append(("txn_null_bytes", {"transaction_id": "test\x00null"}, "null byte in transaction_id"))

    # --- customer_name ---
    cases.append(("name_huge", {"customer_name": "A" * 50000}, "huge customer_name"))
    cases.append(("name_unicode", {"customer_name": "سلام عالیکم 🎉 Ñoño"}, "unicode customer_name"))
    cases.append(("name_null", {"customer_name": None}, "null customer_name"))
    cases.append(("name_empty", {"customer_name": ""}, "empty string customer_name"))

    # --- payment_link_url ---
    cases.append(("url_malformed", {"payment_link_url": "not-a-url"}, "malformed URL"))
    cases.append(("url_non_url", {"payment_link_url": "ftp://weird/path"}, "non-HTTP URL"))
    cases.append(("url_huge", {"payment_link_url": "https://example.com/" + "x" * 50000}, "huge URL"))
    cases.append(("url_javascript", {"payment_link_url": "javascript:alert(1)"}, "javascript: URL"))

    # --- communication_channel ---
    cases.append(("channel_invalid", {"communication_channel": "telegram"}, "invalid channel"))
    cases.append(("channel_uppercase", {"communication_channel": "EMAIL"}, "uppercase channel"))
    cases.append(("channel_empty", {"communication_channel": ""}, "empty channel"))

    return cases


def _audit_abuse_cases() -> List[Tuple[str, str, str]]:
    """Return (case_name, transaction_id, description) for GET /audit abuse."""
    return [
        ("audit_empty_txn", "", "empty transaction_id"),
        ("audit_10k_chars", "x" * 10001, "10,000+ char transaction_id"),
        ("audit_unicode", "交易-🔥-тест", "unicode transaction_id"),
        ("audit_sql_injection", "'; DROP TABLE decisions;--", "SQL injection attempt"),
        ("audit_path_traversal", "../../etc/passwd", "path traversal"),
        ("audit_null_bytes", "test\x00null", "null bytes"),
        ("audit_special_chars", "<script>alert(1)</script>", "HTML/XSS in transaction_id"),
    ]


# ──────────────────────────────────────────────────────────────
# Test runner
# ──────────────────────────────────────────────────────────────

def _classify_result(status: Optional[int], body: Any, error: Optional[str]) -> str:
    """Classify the result: 'expected_reject', 'expected_accept', 'unexpected_500', 'transport_error'."""
    if error and status is None:
        return "transport_error"
    if status in (400, 422):
        return "expected_reject"
    if status == 200:
        return "expected_accept"
    if status and str(status).startswith("5"):
        return "unexpected_500"
    return f"other_{status}"


def _check_traceback_leak(body: Any, error: Optional[str]) -> bool:
    """Check if internal error details leak into the response."""
    text = str(body or "") + str(error or "")
    leak_patterns = ["Traceback", 'File "', "sqlite3.", "pydantic", "ValidationError"]
    return any(p in text for p in leak_patterns)


def run_decide_boundary(client: httpx.Client) -> List[dict]:
    results = []
    for case_name, overrides, description in _boundary_cases():
        payload = scoring_payload(**overrides)
        t0 = time.perf_counter()
        try:
            resp = client.post("/decide", json=payload)
            ms = (time.perf_counter() - t0) * 1000.0
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:1000]
            status = resp.status_code
            error = None
        except Exception as exc:
            ms = (time.perf_counter() - t0) * 1000.0
            body = None
            status = None
            error = f"{type(exc).__name__}: {exc}"[:400]

        classification = _classify_result(status, body, error)
        has_leak = _check_traceback_leak(body, error)

        result = {
            "case": case_name,
            "description": description,
            "status": status,
            "classification": classification,
            "ms": ms,
            "has_traceback_leak": has_leak,
            "body_snippet": str(body)[:500] if body else None,
            "error": error,
        }
        results.append(result)

        # Print inline
        marker = "✓" if classification in ("expected_reject", "expected_accept") else "✗"
        if has_leak:
            marker = "⚠"
        print(f"  [{marker}] {case_name}: HTTP {status} → {classification}" +
              (" [LEAK]" if has_leak else ""))

    return results


def run_audit_boundary(client: httpx.Client) -> List[dict]:
    results = []
    for case_name, txn_id, description in _audit_abuse_cases():
        t0 = time.perf_counter()
        try:
            resp = client.get(f"/audit/{txn_id}")
            ms = (time.perf_counter() - t0) * 1000.0
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:1000]
            status = resp.status_code
            error = None
        except Exception as exc:
            ms = (time.perf_counter() - t0) * 1000.0
            body = None
            status = None
            error = f"{type(exc).__name__}: {exc}"[:400]

        has_leak = _check_traceback_leak(body, error)

        result = {
            "case": case_name,
            "description": description,
            "status": status,
            "ms": ms,
            "has_traceback_leak": has_leak,
            "body_snippet": str(body)[:500] if body else None,
            "error": error,
        }
        results.append(result)

        marker = "✓" if status in (200, 404, 400, 422) else "✗"
        if has_leak:
            marker = "⚠"
        print(f"  [{marker}] {case_name}: HTTP {status}" +
              (" [LEAK]" if has_leak else ""))

    return results


# ──────────────────────────────────────────────────────────────
# Type coercion abuse — raw JSON with wrong types
# ──────────────────────────────────────────────────────────────

def run_type_abuse(client: httpx.Client) -> List[dict]:
    """Send payloads with wrong types (string for int, etc.)."""
    cases = [
        ("amount_string", {"amount": "not_a_number"}, "amount as string"),
        ("attempt_float", {"attempt_number": 1.5}, "attempt_number as float"),
        ("attempt_string", {"attempt_number": "abc"}, "attempt_number as string"),
        ("risk_string", {"risk_score": "high"}, "risk_score as string"),
        ("already_recovered_string", {"already_recovered": "yes"}, "bool as string"),
        ("missing_amount", "REMOVE_amount", "missing required field: amount"),
        ("missing_failure_type", "REMOVE_failure_type", "missing required field: failure_type"),
        ("missing_transaction_id", "REMOVE_transaction_id", "missing required field: transaction_id"),
        ("extra_field", {"extra_malicious": "data"}, "extra field (forbidden by schema)"),
        ("empty_body", "EMPTY_BODY", "empty JSON body"),
        ("null_body", "NULL_BODY", "null JSON body"),
    ]

    results = []
    for case_name, mutation, description in cases:
        if mutation == "EMPTY_BODY":
            raw = {}
        elif mutation == "NULL_BODY":
            raw = None
        elif isinstance(mutation, str) and mutation.startswith("REMOVE_"):
            field = mutation[7:]
            raw = scoring_payload()
            raw.pop(field, None)
        else:
            raw = scoring_payload(**mutation)

        t0 = time.perf_counter()
        try:
            resp = client.post("/decide", json=raw)
            ms = (time.perf_counter() - t0) * 1000.0
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:1000]
            status = resp.status_code
            error = None
        except Exception as exc:
            ms = (time.perf_counter() - t0) * 1000.0
            body = None
            status = None
            error = f"{type(exc).__name__}: {exc}"[:400]

        has_leak = _check_traceback_leak(body, error)
        classification = _classify_result(status, body, error)

        result = {
            "case": case_name,
            "description": description,
            "status": status,
            "classification": classification,
            "ms": ms,
            "has_traceback_leak": has_leak,
            "body_snippet": str(body)[:500] if body else None,
            "error": error,
        }
        results.append(result)

        marker = "✓" if classification in ("expected_reject", "expected_accept") else "✗"
        if has_leak:
            marker = "⚠"
        print(f"  [{marker}] {case_name}: HTTP {status} → {classification}" +
              (" [LEAK]" if has_leak else ""))

    return results


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="m10_boundary_", dir=str(ARTIFACTS))
    db_path = str(Path(tmp) / "isolated.db")
    handle = start_isolated_server(db_path)

    timeout = httpx.Timeout(30.0, connect=10.0)
    client = httpx.Client(base_url=handle["base_url"], timeout=timeout)

    report = {"db_path": db_path, "base_url": handle["base_url"]}

    try:
        # /decide boundary tests
        print("\n=== POST /decide boundary tests ===")
        decide_results = run_decide_boundary(client)

        # Type abuse tests
        print("\n=== POST /decide type abuse tests ===")
        type_results = run_type_abuse(client)

        # /audit boundary tests
        print("\n=== GET /audit boundary tests ===")
        audit_results = run_audit_boundary(client)

        # Summary
        all_decide = decide_results + type_results
        unexpected_500s = [r for r in all_decide if r["classification"] == "unexpected_500"]
        leaks = [r for r in all_decide + audit_results if r["has_traceback_leak"]]

        report["decide_boundary"] = decide_results
        report["type_abuse"] = type_results
        report["audit_boundary"] = audit_results
        report["summary"] = {
            "total_decide_cases": len(all_decide),
            "total_audit_cases": len(audit_results),
            "unexpected_500_count": len(unexpected_500s),
            "unexpected_500_cases": [r["case"] for r in unexpected_500s],
            "traceback_leak_count": len(leaks),
            "traceback_leak_cases": [r["case"] for r in leaks],
            "decide_by_classification": _count_by(all_decide, "classification"),
            "audit_by_status": _count_by(audit_results, "status"),
        }

        print(f"\n=== Summary ===")
        print(f"  Decide cases: {len(all_decide)}")
        print(f"  Audit cases: {len(audit_results)}")
        print(f"  Unexpected 500s: {len(unexpected_500s)}")
        print(f"  Traceback leaks: {len(leaks)}")

    finally:
        client.close()
        stop_isolated_server(handle)

    out = write_json("boundary_summary.json", report)
    print(f"\nWrote {out}")


def _count_by(items: list, key: str) -> dict:
    out: dict = {}
    for item in items:
        val = str(item.get(key))
        out[val] = out.get(val, 0) + 1
    return out


if __name__ == "__main__":
    main()
