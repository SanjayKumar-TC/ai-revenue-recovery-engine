"""
Section 4.2 — Concurrent audit reads (Category 2) running simultaneously
with moderate /decide load (Category 1, 50 workers, 2000 requests).

Both workloads hit the SAME isolated temporary database to measure
read/write concurrency (partial Category 3 coverage).
"""

from __future__ import annotations

import os
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
    newest_first,
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
# /decide worker (reuses _common helpers)
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


# ──────────────────────────────────────────────────────────────
# /audit/{txn} worker
# ──────────────────────────────────────────────────────────────

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
# Analysis helpers
# ──────────────────────────────────────────────────────────────

def _analyse_audit_rows(rows: list) -> dict:
    """Analyse audit GET responses for shape, leakage, ordering."""
    shape_problems = []
    leakage_count = 0
    ordering_violations = 0
    ordering_checked = 0

    for row in rows:
        if row.get("status") is None:
            continue
        if row["status"] == 404:
            continue  # no record yet — valid during concurrent write
        if row["status"] != 200:
            continue

        body = row.get("body")
        txn = row["transaction_id"]
        problems = validate_audit_shape(txn, row["status"], body)
        shape_problems.extend(problems)

        # Check cross-transaction leakage
        if isinstance(body, dict):
            records = body.get("records", [])
            if isinstance(records, list):
                for rec in records:
                    if isinstance(rec, dict) and rec.get("transaction_id") != txn:
                        leakage_count += 1

                # Check ordering (newest-first)
                if len(records) > 1:
                    ordering_checked += 1
                    if not newest_first(records):
                        ordering_violations += 1

    return {
        "shape_problems": _count(shape_problems),
        "cross_transaction_leakage": leakage_count,
        "ordering_checked": ordering_checked,
        "ordering_violations": ordering_violations,
    }


def _count(items: list) -> dict:
    out = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return out


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="m10_audit_", dir=str(ARTIFACTS))
    db_path = str(Path(tmp) / "isolated.db")
    handle = start_isolated_server(db_path)
    base_url = handle["base_url"]

    timeout = httpx.Timeout(60.0, connect=10.0)
    limits = httpx.Limits(max_connections=300, max_keepalive_connections=300)
    decide_client = httpx.Client(base_url=base_url, timeout=timeout, limits=limits)
    audit_client = httpx.Client(base_url=base_url, timeout=timeout, limits=limits)

    report = {"db_path": db_path, "base_url": base_url}

    try:
        # ── Phase 1: Seed some /decide transactions for audit lookups ──
        print("[Phase 1] Seeding 200 transactions for audit lookup pool...")
        seed_txns = []
        seed_payloads = []
        for i in range(200):
            txn = f"m10-audit-seed-{i}-{time.time_ns()}"
            seed_txns.append(txn)
            seed_payloads.append(scoring_payload(transaction_id=txn))

        seed_rows = run_until(
            seed_payloads, workers=20, deadline=time.time() + 60,
            fn=_make_decide_fn(decide_client),
        )
        seeded_ok = [r for r in seed_rows if r.get("status") == 200]
        seeded_txns = [r["transaction_id"] for r in seeded_ok]
        print(f"  Seeded {len(seeded_ok)}/{len(seed_payloads)} transactions OK")
        report["seed"] = {
            "requested": len(seed_payloads),
            "seeded_ok": len(seeded_ok),
        }

        print("[Phase 1b] Seeding multi-row transaction for newest-first check...")
        multi_txn = f"m10-audit-multi-{time.time_ns()}"
        multi_payloads = [scoring_payload(transaction_id=multi_txn) for _ in range(5)]
        run_until(
            multi_payloads, workers=1, deadline=time.time() + 60,
            fn=_make_decide_fn(decide_client),
        )
        order_resp = audit_client.get(f"/audit/{multi_txn}")
        try:
            order_body = order_resp.json()
        except Exception:
            order_body = {}
        order_records = order_body.get("records") if isinstance(order_body, dict) else []
        report["server_side_ordering"] = {
            "transaction_id": multi_txn,
            "http_status": order_resp.status_code,
            "record_count": len(order_records) if isinstance(order_records, list) else None,
            "timestamps": [r.get("timestamp") for r in order_records] if isinstance(order_records, list) else [],
            "newest_first": newest_first(order_records) if isinstance(order_records, list) else None,
            "m8_sql_orders_by_timestamp_desc": True,
        }
        print(
            f"  Multi-row GET /audit: {order_resp.status_code} "
            f"n={report['server_side_ordering']['record_count']} "
            f"newest_first={report['server_side_ordering']['newest_first']}"
        )

        if os.environ.get("M10_AUDIT_ORDERING_ONLY") == "1":
            write_json("audit_load_summary.json", report)
            return

        # ── Phase 2: Concurrent /decide (moderate) + /audit reads ──
        print("[Phase 2] Running concurrent moderate /decide + audit reads...")

        # Build payloads for moderate /decide scenario
        decide_payloads = [
            scoring_payload(transaction_id=f"m10-audit-mod-{i}-{time.time_ns()}")
            for i in range(2000)
        ]

        # Build audit lookup targets — cycle through seeded txns
        audit_targets = []
        for i in range(1000):
            audit_targets.append(seeded_txns[i % len(seeded_txns)] if seeded_txns else f"m10-audit-seed-{i}")

        decide_rows = []
        audit_rows = []
        deadline = time.time() + 120

        # Launch both workloads in parallel threads
        def run_decide():
            nonlocal decide_rows
            decide_rows = run_until(
                decide_payloads, workers=50, deadline=deadline,
                fn=_make_decide_fn(decide_client),
            )

        def run_audit():
            nonlocal audit_rows
            audit_rows = run_until(
                audit_targets, workers=50, deadline=deadline,
                fn=_make_audit_fn(audit_client),
            )

        t_decide = threading.Thread(target=run_decide, name="decide-moderate")
        t_audit = threading.Thread(target=run_audit, name="audit-concurrent")
        t0 = time.time()
        t_decide.start()
        t_audit.start()
        t_decide.join()
        t_audit.join()
        elapsed = time.time() - t0

        print(f"  Completed in {elapsed:.1f}s: {len(decide_rows)} decide, {len(audit_rows)} audit")

        # ── Analyse decide results ──
        decide_lat = [r["ms"] for r in decide_rows if r.get("ms") is not None]
        decide_breakdown = status_breakdown(decide_rows)
        decide_problems = []
        for row in decide_rows:
            if row.get("status") == 200:
                decide_problems.extend(validate_decide_200(row["transaction_id"], row.get("body")))

        report["concurrent_decide"] = {
            "requested": len(decide_payloads),
            "completed": len(decide_rows),
            "workers": 50,
            "elapsed_seconds": elapsed,
            "breakdown": decide_breakdown,
            "latency_ms": percentiles(decide_lat),
            "integrity_problems": _count(decide_problems),
        }

        # ── Analyse audit results ──
        audit_lat = [r["ms"] for r in audit_rows if r.get("ms") is not None]
        audit_breakdown = status_breakdown(audit_rows)
        audit_analysis = _analyse_audit_rows(audit_rows)

        report["concurrent_audit"] = {
            "requested": len(audit_targets),
            "completed": len(audit_rows),
            "workers": 50,
            "elapsed_seconds": elapsed,
            "breakdown": audit_breakdown,
            "latency_ms": percentiles(audit_lat),
            **audit_analysis,
        }

        # ── Sample for detailed output ──
        write_json("audit_concurrent_decide_sample.json", decide_rows[:20])
        write_json("audit_concurrent_audit_sample.json", audit_rows[:20])

    finally:
        decide_client.close()
        audit_client.close()
        stop_isolated_server(handle)

    import json
    out = write_json("audit_load_summary.json", report)
    print(json.dumps(report, indent=2, default=str))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
