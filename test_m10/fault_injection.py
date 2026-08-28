"""
Section 4.5 — Fault injection / resilience (Category 5).

Against isolated test infrastructure only:
 1. M4 unavailable (model pipeline missing/broken)
 2. M7 write failure (temp DB made unwritable)
 3. Slowed decision path (heavy concurrent load)
 4. M6 fallback triggers (missing channel, invalid discount — inputs that
    naturally trigger existing M6 fallback logic without modifying M6)

Verifies M8 fail-safe:
 - Fail-closed for policy/decision (model unavailable → escalate or no_action)
 - Fail-open for audit (M7 write failure → HTTP 200, decision preserved,
   trace_id may be null)
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    ARTIFACTS,
    DECIDE_200_FIELDS,
    assert_isolated_db,
    percentiles,
    run_until,
    scoring_payload,
    start_isolated_server,
    stop_isolated_server,
    validate_decide_200,
    write_json,
)


# ──────────────────────────────────────────────────────────────
# Test 1: M4 model unavailable
# ──────────────────────────────────────────────────────────────

def test_model_unavailable() -> dict:
    """Inject a broken model_pipeline via M10 server env (no M8 source change)."""
    print("\n=== Test 1: M4 Model Unavailable ===")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="m10_fault_model_", dir=str(ARTIFACTS))
    db_path = str(Path(tmp) / "isolated.db")
    handle = start_isolated_server(db_path, extra_env={"M10_BROKEN_MODEL": "1"})
    client = httpx.Client(base_url=handle["base_url"], timeout=httpx.Timeout(30.0))

    results = {"scenario": "model_unavailable"}
    try:
        payload = scoring_payload()
        resp = client.post("/decide", json=payload)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:500]}
        text = resp.text
        results["observed"] = {
            "status": resp.status_code,
            "selected_action": body.get("selected_action") if isinstance(body, dict) else None,
            "decision_type": body.get("decision_type") if isinstance(body, dict) else None,
            "decision_reason": body.get("decision_reason") if isinstance(body, dict) else None,
            "has_traceback": "Traceback" in text,
            "contract_200": resp.status_code == 200,
            "documented_unavailable_path": (
                isinstance(body, dict)
                and body.get("decision_type") in {"model_unavailable", "safe_fallback"}
            ),
        }
        print(
            f"  HTTP {resp.status_code} action={results['observed']['selected_action']} "
            f"type={results['observed']['decision_type']} "
            f"reason={results['observed']['decision_reason']}"
        )
    finally:
        client.close()
        stop_isolated_server(handle)

    return results


# ──────────────────────────────────────────────────────────────
# Test 2: M7 write failure (DB unwritable)
# ──────────────────────────────────────────────────────────────

def test_m7_write_failure() -> dict:
    """Start server, then make the DB unwritable. Verify:
    - /decide still returns HTTP 200
    - Decision fields are preserved
    - trace_id may be null"""
    print("\n=== Test 2: M7 Write Failure (DB Unwritable) ===")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="m10_fault_m7_", dir=str(ARTIFACTS))
    db_path = str(Path(tmp) / "isolated.db")
    handle = start_isolated_server(db_path)
    client = httpx.Client(base_url=handle["base_url"], timeout=httpx.Timeout(30.0))

    results = {"scenario": "m7_write_failure"}
    try:
        # Phase A: Normal request (should write audit, trace_id not null)
        payload_a = scoring_payload(transaction_id="m10-fault-m7-normal")
        resp_a = client.post("/decide", json=payload_a)
        body_a = resp_a.json() if resp_a.status_code == 200 else None

        results["phase_a_normal"] = {
            "status": resp_a.status_code,
            "trace_id": body_a.get("trace_id") if body_a else None,
            "trace_id_not_null": body_a.get("trace_id") is not None if body_a else False,
        }
        print(f"  Phase A (normal): HTTP {resp_a.status_code}, trace_id={body_a.get('trace_id') if body_a else 'N/A'}")

        # Phase B: Make DB read-only (simulate write failure)
        db_file = Path(db_path)
        if db_file.exists():
            try:
                # Make the DB file read-only
                os.chmod(db_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
                # Also try to make the directory read-only for WAL/journal
                os.chmod(tmp, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
            except OSError as e:
                results["chmod_error"] = str(e)
                print(f"  Warning: Could not chmod: {e}")

        # Send requests after making DB unwritable
        fault_results = []
        for i in range(5):
            payload_b = scoring_payload(transaction_id=f"m10-fault-m7-broken-{i}")
            resp_b = client.post("/decide", json=payload_b)
            try:
                body_b = resp_b.json()
            except Exception:
                body_b = {"raw": resp_b.text[:500]}

            fault_results.append({
                "status": resp_b.status_code,
                "trace_id": body_b.get("trace_id") if isinstance(body_b, dict) else None,
                "has_selected_action": "selected_action" in body_b if isinstance(body_b, dict) else False,
                "has_decision_fields": all(
                    f in body_b for f in ["selected_action", "decision_type", "decision_reason"]
                ) if isinstance(body_b, dict) else False,
            })
            print(f"  Phase B request {i}: HTTP {resp_b.status_code}, "
                  f"trace_id={body_b.get('trace_id') if isinstance(body_b, dict) else 'N/A'}")

        # M8 contract check: HTTP 200, decision preserved, trace_id may be null
        all_200 = all(r["status"] == 200 for r in fault_results)
        all_have_decision = all(r["has_decision_fields"] for r in fault_results)
        any_null_trace = any(r["trace_id"] is None for r in fault_results)

        results["phase_b_fault"] = {
            "requests": len(fault_results),
            "details": fault_results,
            "all_http_200": all_200,
            "all_have_decision_fields": all_have_decision,
            "any_null_trace_id": any_null_trace,
            "m8_contract_holds": all_200 and all_have_decision,
        }

    finally:
        # Restore permissions before cleanup
        try:
            os.chmod(tmp, stat.S_IRWXU)
            if Path(db_path).exists():
                os.chmod(db_path, stat.S_IRWXU)
        except OSError:
            pass
        client.close()
        stop_isolated_server(handle)

    return results


# ──────────────────────────────────────────────────────────────
# Test 3: M7 write failure via missing DB directory
# ──────────────────────────────────────────────────────────────

def test_m7_missing_db() -> dict:
    """Start server with a DB path pointing to a non-existent directory.
    The server should still start (model loads independently of audit DB),
    and /decide should return HTTP 200 with trace_id=null."""
    print("\n=== Test 3: M7 Missing DB Directory ===")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    # Use a path where the directory will be auto-created by audit_writer
    # but we verify the behavior
    tmp = tempfile.mkdtemp(prefix="m10_fault_missing_", dir=str(ARTIFACTS))
    missing_dir = str(Path(tmp) / "nonexistent_subdir" / "deep")
    db_path = str(Path(missing_dir) / "isolated.db")

    # The audit_writer.initialise_db creates directories, so this should actually
    # work. We test this path to confirm robustness.
    handle = start_isolated_server(db_path)
    client = httpx.Client(base_url=handle["base_url"], timeout=httpx.Timeout(30.0))

    results = {"scenario": "m7_missing_db_dir"}
    try:
        payload = scoring_payload(transaction_id="m10-fault-missing-db")
        resp = client.post("/decide", json=payload)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:500]}

        results["result"] = {
            "status": resp.status_code,
            "trace_id": body.get("trace_id") if isinstance(body, dict) else None,
            "has_selected_action": "selected_action" in body if isinstance(body, dict) else False,
            "db_was_created": Path(db_path).exists(),
        }
        print(f"  HTTP {resp.status_code}, trace_id={body.get('trace_id') if isinstance(body, dict) else 'N/A'}, "
              f"DB created: {Path(db_path).exists()}")

    finally:
        client.close()
        stop_isolated_server(handle)

    return results


# ──────────────────────────────────────────────────────────────
# Test 4: M6 fallback triggers (legitimate inputs)
# ──────────────────────────────────────────────────────────────

def test_m6_fallback_triggers() -> dict:
    """Send inputs that naturally trigger M6's fallback path:
    - Missing communication_channel
    - Invalid discount (action=discount but discount=0)
    These don't modify M6; they supply inputs that legitimately trigger fallback."""
    print("\n=== Test 4: M6 Fallback Triggers ===")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="m10_fault_m6_", dir=str(ARTIFACTS))
    db_path = str(Path(tmp) / "isolated.db")
    handle = start_isolated_server(db_path)
    client = httpx.Client(base_url=handle["base_url"], timeout=httpx.Timeout(30.0))

    results = {"scenario": "m6_fallback_triggers", "cases": []}
    try:
        # Case 1: No communication_channel (omitted → should use M6 default)
        payload_no_channel = scoring_payload()
        payload_no_channel.pop("communication_channel", None)
        resp = client.post("/decide", json=payload_no_channel)
        body = resp.json() if resp.status_code == 200 else {"raw": resp.text[:500]}
        comm = body.get("communication", {}) if isinstance(body, dict) else {}
        results["cases"].append({
            "case": "no_communication_channel",
            "status": resp.status_code,
            "communication": comm,
            "fallback_used": comm.get("fallback_used"),
        })
        print(f"  No channel: HTTP {resp.status_code}, fallback_used={comm.get('fallback_used')}")

        # Case 2: communication_channel = "none"
        payload_none_ch = scoring_payload(communication_channel="none")
        resp2 = client.post("/decide", json=payload_none_ch)
        body2 = resp2.json() if resp2.status_code == 200 else {"raw": resp2.text[:500]}
        comm2 = body2.get("communication", {}) if isinstance(body2, dict) else {}
        results["cases"].append({
            "case": "channel_none",
            "status": resp2.status_code,
            "communication": comm2,
            "fallback_used": comm2.get("fallback_used"),
        })
        print(f"  Channel='none': HTTP {resp2.status_code}, fallback_used={comm2.get('fallback_used')}")

        # Case 3: payment_link_url omitted (M6 needs it for payment_link action)
        payload_no_link = scoring_payload()
        payload_no_link.pop("payment_link_url", None)
        resp3 = client.post("/decide", json=payload_no_link)
        body3 = resp3.json() if resp3.status_code == 200 else {"raw": resp3.text[:500]}
        comm3 = body3.get("communication", {}) if isinstance(body3, dict) else {}
        results["cases"].append({
            "case": "no_payment_link_url",
            "status": resp3.status_code,
            "communication": comm3,
            "fallback_used": comm3.get("fallback_used"),
        })
        print(f"  No payment_link_url: HTTP {resp3.status_code}, fallback_used={comm3.get('fallback_used')}")

        # Case 4: customer_name omitted (M6 uses for greeting)
        payload_no_name = scoring_payload()
        payload_no_name.pop("customer_name", None)
        resp4 = client.post("/decide", json=payload_no_name)
        body4 = resp4.json() if resp4.status_code == 200 else {"raw": resp4.text[:500]}
        comm4 = body4.get("communication", {}) if isinstance(body4, dict) else {}
        results["cases"].append({
            "case": "no_customer_name",
            "status": resp4.status_code,
            "communication": comm4,
            "sendable": comm4.get("sendable"),
        })
        print(f"  No customer_name: HTTP {resp4.status_code}, sendable={comm4.get('sendable')}")

        # Case 5: Inputs that trigger a terminal/policy-only decision
        # (high risk_score → blocks automated recovery → M6 not invoked)
        payload_high_risk = scoring_payload(risk_score=0.95)
        resp5 = client.post("/decide", json=payload_high_risk)
        body5 = resp5.json() if resp5.status_code == 200 else {"raw": resp5.text[:500]}
        comm5 = body5.get("communication", {}) if isinstance(body5, dict) else {}
        results["cases"].append({
            "case": "high_risk_policy_block",
            "status": resp5.status_code,
            "selected_action": body5.get("selected_action") if isinstance(body5, dict) else None,
            "decision_type": body5.get("decision_type") if isinstance(body5, dict) else None,
            "communication": comm5,
            "sendable": comm5.get("sendable"),
        })
        print(f"  High risk (0.95): HTTP {resp5.status_code}, action={body5.get('selected_action') if isinstance(body5, dict) else 'N/A'}")

        # Case 6: already_recovered=True (should be terminal)
        payload_recovered = scoring_payload(already_recovered=True)
        resp6 = client.post("/decide", json=payload_recovered)
        body6 = resp6.json() if resp6.status_code == 200 else {"raw": resp6.text[:500]}
        comm6 = body6.get("communication", {}) if isinstance(body6, dict) else {}
        results["cases"].append({
            "case": "already_recovered",
            "status": resp6.status_code,
            "selected_action": body6.get("selected_action") if isinstance(body6, dict) else None,
            "terminal": body6.get("terminal") if isinstance(body6, dict) else None,
            "communication": comm6,
            "sendable": comm6.get("sendable"),
        })
        print(f"  Already recovered: HTTP {resp6.status_code}, action={body6.get('selected_action') if isinstance(body6, dict) else 'N/A'}, "
              f"terminal={body6.get('terminal') if isinstance(body6, dict) else 'N/A'}")

        payload_pl = scoring_payload(failure_type="card_expired")
        payload_pl.pop("payment_link_url", None)
        resp7 = client.post("/decide", json=payload_pl)
        body7 = resp7.json() if resp7.status_code == 200 else {"raw": resp7.text[:500]}
        comm7 = body7.get("communication", {}) if isinstance(body7, dict) else {}
        results["cases"].append({
            "case": "card_expired_missing_payment_link",
            "status": resp7.status_code,
            "selected_action": body7.get("selected_action") if isinstance(body7, dict) else None,
            "communication": comm7,
            "fallback_used": comm7.get("fallback_used"),
        })
        print(
            f"  card_expired no link: HTTP {resp7.status_code} "
            f"action={body7.get('selected_action') if isinstance(body7, dict) else 'N/A'} "
            f"fallback_used={comm7.get('fallback_used')}"
        )

    finally:
        client.close()
        stop_isolated_server(handle)

    return results


# ──────────────────────────────────────────────────────────────
# Test 3b: Slow upstream
# ──────────────────────────────────────────────────────────────

def test_slow_upstream() -> dict:
    """Artificially delay M2 predict_proba; request must still complete."""
    print("\n=== Test 3b: Slow upstream (injected delay) ===")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="m10_fault_slow_", dir=str(ARTIFACTS))
    db_path = str(Path(tmp) / "isolated.db")
    handle = start_isolated_server(db_path, extra_env={"M10_SLOW_SEC": "2"})
    client = httpx.Client(base_url=handle["base_url"], timeout=httpx.Timeout(60.0))
    results = {"scenario": "slow_upstream"}
    try:
        t0 = time.perf_counter()
        resp = client.post("/decide", json=scoring_payload())
        elapsed = time.perf_counter() - t0
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:300]}
        results["observed"] = {
            "status": resp.status_code,
            "elapsed_seconds": elapsed,
            "has_selected_action": isinstance(body, dict) and "selected_action" in body,
            "completed_under_60s": elapsed < 60,
            "has_traceback": "Traceback" in resp.text,
        }
        print(f"  HTTP {resp.status_code} in {elapsed:.1f}s")
    except Exception as exc:
        results["observed"] = {
            "status": None,
            "error": f"{type(exc).__name__}: {exc}"[:400],
            "completed_under_60s": False,
        }
        print(f"  Failed: {exc}")
    finally:
        client.close()
        stop_isolated_server(handle)
    return results


# ──────────────────────────────────────────────────────────────
# Test 5: Decision under heavy concurrent load (slowed path)
# ──────────────────────────────────────────────────────────────

def test_heavy_load_degradation() -> dict:
    """Measure decision quality under heavy concurrent load —
    does the system still return correct responses under stress?"""
    print("\n=== Test 5: Heavy Load Degradation ===")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="m10_fault_load_", dir=str(ARTIFACTS))
    db_path = str(Path(tmp) / "isolated.db")
    handle = start_isolated_server(db_path)
    timeout = httpx.Timeout(60.0, connect=10.0)
    limits = httpx.Limits(max_connections=150, max_keepalive_connections=150)
    client = httpx.Client(base_url=handle["base_url"], timeout=timeout, limits=limits)

    results = {"scenario": "heavy_load_degradation"}
    try:
        # Send 100 identical requests concurrently to check for corruption
        reference_payload = scoring_payload(transaction_id="m10-fault-load-ref")
        payloads = [
            scoring_payload(transaction_id=f"m10-fault-load-{i}") for i in range(100)
        ]

        def _post(payload: dict) -> dict:
            t0 = time.perf_counter()
            try:
                resp = client.post("/decide", json=payload)
                ms = (time.perf_counter() - t0) * 1000.0
                try:
                    body = resp.json()
                except Exception:
                    body = resp.text[:500]
                return {
                    "status": resp.status_code, "ms": ms,
                    "body": body, "error": None,
                    "transaction_id": payload["transaction_id"],
                }
            except Exception as exc:
                return {
                    "status": None, "ms": (time.perf_counter() - t0) * 1000.0,
                    "body": None, "error": f"{type(exc).__name__}: {exc}"[:400],
                    "transaction_id": payload["transaction_id"],
                }

        rows = run_until(payloads, workers=100, deadline=time.time() + 60, fn=_post)

        ok_rows = [r for r in rows if r.get("status") == 200]
        actions = set()
        integrity_issues = []
        for r in ok_rows:
            if isinstance(r.get("body"), dict):
                actions.add(r["body"].get("selected_action"))
                problems = validate_decide_200(r["transaction_id"], r["body"])
                if problems:
                    integrity_issues.append({"txn": r["transaction_id"], "problems": problems})

        lat = [r["ms"] for r in rows if r.get("ms") is not None]
        results["result"] = {
            "total": len(rows),
            "http_200": len(ok_rows),
            "http_5xx": len([r for r in rows if r.get("status") and str(r["status"]).startswith("5")]),
            "transport_errors": len([r for r in rows if r.get("error") and r.get("status") is None]),
            "distinct_actions": list(actions),
            "integrity_issues_count": len(integrity_issues),
            "integrity_issues_sample": integrity_issues[:5],
            "latency_ms": percentiles(lat),
        }

        print(f"  {len(ok_rows)}/{len(rows)} HTTP 200, "
              f"actions: {actions}, issues: {len(integrity_issues)}")

    finally:
        client.close()
        stop_isolated_server(handle)

    return results


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    report = {"tests": {}}

    report["tests"]["1_model_unavailable"] = test_model_unavailable()
    report["tests"]["2_m7_write_failure"] = test_m7_write_failure()
    report["tests"]["3_m7_missing_db"] = test_m7_missing_db()
    report["tests"]["3b_slow_upstream"] = test_slow_upstream()
    report["tests"]["4_m6_fallback"] = test_m6_fallback_triggers()
    report["tests"]["5_heavy_load"] = test_heavy_load_degradation()

    out = write_json("fault_injection_summary.json", report)
    print(f"\n{'='*60}")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
