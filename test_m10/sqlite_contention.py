"""
Section 4.3 — SQLite write/read contention (Category 3).

Runs concurrent /decide writes and /audit reads against the SAME isolated
temporary database. Focuses on:
 - "database is locked" errors
 - Missing audit rows
 - HTTP behavior when M7 write fails mid-contention
 - M8's documented contract: M7 write failure → HTTP 200, decision preserved,
   trace_id may be null
"""

from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    ARTIFACTS,
    percentiles,
    run_until,
    scoring_payload,
    start_isolated_server,
    status_breakdown,
    stop_isolated_server,
    validate_audit_shape,
    validate_decide_200,
    write_json,
)


# ──────────────────────────────────────────────────────────────
# Worker functions
# ──────────────────────────────────────────────────────────────

def _make_decide_fn(client: httpx.Client):
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
                "kind": "decide",
                "status": resp.status_code,
                "ms": ms,
                "body": body,
                "error": None,
                "transaction_id": payload["transaction_id"],
            }
        except Exception as exc:
            return {
                "kind": "decide",
                "status": None,
                "ms": (time.perf_counter() - t0) * 1000.0,
                "body": None,
                "error": f"{type(exc).__name__}: {exc}"[:400],
                "transaction_id": payload["transaction_id"],
            }
    return _post


def _make_audit_fn(client: httpx.Client):
    def _get(txn_id: str) -> dict:
        t0 = time.perf_counter()
        try:
            resp = client.get(f"/audit/{txn_id}")
            ms = (time.perf_counter() - t0) * 1000.0
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:500]
            return {
                "kind": "audit",
                "status": resp.status_code,
                "ms": ms,
                "body": body,
                "error": None,
                "transaction_id": txn_id,
            }
        except Exception as exc:
            return {
                "kind": "audit",
                "status": None,
                "ms": (time.perf_counter() - t0) * 1000.0,
                "body": None,
                "error": f"{type(exc).__name__}: {exc}"[:400],
                "transaction_id": txn_id,
            }
    return _get


# ──────────────────────────────────────────────────────────────
# Contention analysis
# ──────────────────────────────────────────────────────────────

def _analyse_contention(decide_rows: list, audit_rows: list, client: httpx.Client) -> dict:
    """Post-hoc analysis for contention artefacts."""
    findings = {}

    # 1. SQLite errors in responses
    sqlite_errors_decide = []
    sqlite_errors_audit = []
    for r in decide_rows:
        txt = str(r.get("body", "")) + str(r.get("error", ""))
        if "database is locked" in txt.lower():
            sqlite_errors_decide.append(r["transaction_id"])
    for r in audit_rows:
        txt = str(r.get("body", "")) + str(r.get("error", ""))
        if "database is locked" in txt.lower():
            sqlite_errors_audit.append(r["transaction_id"])
    findings["sqlite_locked_decide"] = len(sqlite_errors_decide)
    findings["sqlite_locked_audit"] = len(sqlite_errors_audit)

    # 2. 5xx on decide
    decide_5xx = [r for r in decide_rows if r.get("status") and str(r["status"]).startswith("5")]
    findings["decide_5xx_count"] = len(decide_5xx)
    findings["decide_5xx_detail"] = [
        {"txn": r["transaction_id"], "status": r["status"], "body_snippet": str(r.get("body"))[:200]}
        for r in decide_5xx[:10]
    ]

    # 3. M8 contract: M7 write failure → HTTP 200, trace_id null
    null_trace_on_200 = []
    for r in decide_rows:
        if r.get("status") == 200 and isinstance(r.get("body"), dict):
            if r["body"].get("trace_id") is None:
                null_trace_on_200.append(r["transaction_id"])
    findings["null_trace_id_on_200_count"] = len(null_trace_on_200)

    # 4. Verify those null-trace decisions still have correct fields
    contract_violations = []
    for r in decide_rows:
        if r.get("status") == 200 and isinstance(r.get("body"), dict):
            if r["body"].get("trace_id") is None:
                problems = validate_decide_200(r["transaction_id"], r["body"])
                # trace_id being null is acceptable per contract, remove from problems
                if problems:
                    contract_violations.append({
                        "txn": r["transaction_id"],
                        "problems": problems,
                    })
    findings["null_trace_contract_violations"] = contract_violations[:10]

    # 5. Missing audit rows — sample check
    # For decide rows that returned 200 with non-null trace_id,
    # verify the audit record exists
    sample_txns = [
        r["transaction_id"] for r in decide_rows
        if r.get("status") == 200 and isinstance(r.get("body"), dict)
        and r["body"].get("trace_id") is not None
    ][:50]  # sample 50

    missing_audit = 0
    audit_found = 0
    for txn in sample_txns:
        try:
            resp = client.get(f"/audit/{txn}")
            if resp.status_code == 200:
                audit_found += 1
            elif resp.status_code == 404:
                missing_audit += 1
        except Exception:
            pass
    findings["audit_sample_checked"] = len(sample_txns)
    findings["audit_sample_found"] = audit_found
    findings["audit_sample_missing"] = missing_audit

    return findings


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="m10_contention_", dir=str(ARTIFACTS))
    db_path = str(Path(tmp) / "isolated.db")
    handle = start_isolated_server(db_path)
    base_url = handle["base_url"]

    timeout = httpx.Timeout(60.0, connect=10.0)
    limits = httpx.Limits(max_connections=300, max_keepalive_connections=300)
    client = httpx.Client(base_url=base_url, timeout=timeout, limits=limits)
    audit_client = httpx.Client(base_url=base_url, timeout=timeout, limits=limits)

    report = {"db_path": db_path, "base_url": base_url}

    try:
        # ── Phase 1: Seed transactions so audit reads have targets ──
        print("[Phase 1] Seeding 100 transactions...")
        seed_payloads = [
            scoring_payload(transaction_id=f"m10-cont-seed-{i}")
            for i in range(100)
        ]
        seed_rows = run_until(
            seed_payloads, workers=10, deadline=time.time() + 30,
            fn=_make_decide_fn(client),
        )
        seeded_ok = [r["transaction_id"] for r in seed_rows if r.get("status") == 200]
        print(f"  Seeded {len(seeded_ok)}/100")

        # ── Phase 2: Simultaneous writes + reads ──
        print("[Phase 2] Concurrent writes (500 /decide) + reads (500 /audit)...")

        write_payloads = [
            scoring_payload(transaction_id=f"m10-cont-write-{i}-{time.time_ns()}")
            for i in range(500)
        ]
        # Reads cycle through seeded txns
        read_targets = [seeded_ok[i % len(seeded_ok)] for i in range(500)] if seeded_ok else []

        decide_rows = []
        audit_rows = []
        deadline = time.time() + 90

        def run_writes():
            nonlocal decide_rows
            decide_rows = run_until(
                write_payloads, workers=50, deadline=deadline,
                fn=_make_decide_fn(client),
            )

        def run_reads():
            nonlocal audit_rows
            if not read_targets:
                return
            audit_rows = run_until(
                read_targets, workers=50, deadline=deadline,
                fn=_make_audit_fn(audit_client),
            )

        t_write = threading.Thread(target=run_writes, name="writes")
        t_read = threading.Thread(target=run_reads, name="reads")
        t0 = time.time()
        t_write.start()
        t_read.start()
        t_write.join()
        t_read.join()
        elapsed = time.time() - t0
        print(f"  Completed in {elapsed:.1f}s: {len(decide_rows)} writes, {len(audit_rows)} reads")

        # ── Analyse ──
        decide_lat = [r["ms"] for r in decide_rows if r.get("ms") is not None]
        audit_lat = [r["ms"] for r in audit_rows if r.get("ms") is not None]

        contention_analysis = _analyse_contention(decide_rows, audit_rows, client)

        report["phase2"] = {
            "writes_requested": len(write_payloads),
            "writes_completed": len(decide_rows),
            "reads_requested": len(read_targets),
            "reads_completed": len(audit_rows),
            "elapsed_seconds": elapsed,
            "write_breakdown": status_breakdown(decide_rows),
            "read_breakdown": status_breakdown(audit_rows),
            "write_latency_ms": percentiles(decide_lat),
            "read_latency_ms": percentiles(audit_lat),
            "contention": contention_analysis,
        }

        # ── Phase 3: Heavy contention burst ──
        print("[Phase 3] Heavy contention burst (200 workers, 1000 writes + 1000 reads)...")
        burst_write_payloads = [
            scoring_payload(transaction_id=f"m10-cont-burst-{i}-{time.time_ns()}")
            for i in range(1000)
        ]
        burst_read_targets = [seeded_ok[i % len(seeded_ok)] for i in range(1000)] if seeded_ok else []

        burst_decide = []
        burst_audit = []
        deadline2 = time.time() + 120

        def run_burst_writes():
            nonlocal burst_decide
            burst_decide = run_until(
                burst_write_payloads, workers=100, deadline=deadline2,
                fn=_make_decide_fn(client),
            )

        def run_burst_reads():
            nonlocal burst_audit
            if not burst_read_targets:
                return
            burst_audit = run_until(
                burst_read_targets, workers=100, deadline=deadline2,
                fn=_make_audit_fn(audit_client),
            )

        tb_w = threading.Thread(target=run_burst_writes, name="burst-writes")
        tb_r = threading.Thread(target=run_burst_reads, name="burst-reads")
        t1 = time.time()
        tb_w.start()
        tb_r.start()
        tb_w.join()
        tb_r.join()
        elapsed2 = time.time() - t1
        print(f"  Completed in {elapsed2:.1f}s: {len(burst_decide)} writes, {len(burst_audit)} reads")

        burst_contention = _analyse_contention(burst_decide, burst_audit, client)
        burst_d_lat = [r["ms"] for r in burst_decide if r.get("ms") is not None]
        burst_a_lat = [r["ms"] for r in burst_audit if r.get("ms") is not None]

        report["phase3_heavy_burst"] = {
            "writes_requested": len(burst_write_payloads),
            "writes_completed": len(burst_decide),
            "reads_requested": len(burst_read_targets),
            "reads_completed": len(burst_audit),
            "elapsed_seconds": elapsed2,
            "write_breakdown": status_breakdown(burst_decide),
            "read_breakdown": status_breakdown(burst_audit),
            "write_latency_ms": percentiles(burst_d_lat),
            "read_latency_ms": percentiles(burst_a_lat),
            "contention": burst_contention,
        }

        write_json("contention_decide_sample.json", decide_rows[:20])
        write_json("contention_audit_sample.json", audit_rows[:20])

    finally:
        client.close()
        audit_client.close()
        stop_isolated_server(handle)

    import json
    out = write_json("contention_summary.json", report)
    print(json.dumps(report, indent=2, default=str))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
