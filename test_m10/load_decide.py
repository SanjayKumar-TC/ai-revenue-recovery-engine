"""Section 4.1 — POST /decide concurrency/load against an isolated M8 instance."""

from __future__ import annotations

import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    ARTIFACTS,
    percentiles,
    scoring_payload,
    start_isolated_server,
    status_breakdown,
    stop_isolated_server,
    validate_decide_200,
    write_json,
)


def _post(client: httpx.Client, payload: dict) -> dict:
    t0 = time.perf_counter()
    try:
        resp = client.post("/decide", json=payload)
        ms = (time.perf_counter() - t0) * 1000.0
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:500]
        return {
            "status": resp.status_code,
            "ms": ms,
            "body": body,
            "error": None,
            "transaction_id": payload["transaction_id"],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": None,
            "ms": (time.perf_counter() - t0) * 1000.0,
            "body": None,
            "error": f"{type(exc).__name__}: {exc}"[:400],
            "transaction_id": payload["transaction_id"],
        }


def run_pool(client: httpx.Client, payloads: list, workers: int, deadline: float) -> list:
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_post, client, p) for p in payloads]
        for fut in as_completed(futs):
            if time.time() > deadline:
                for pending in futs:
                    pending.cancel()
                break
            rows.append(fut.result())
    return rows


def summarize(name: str, rows: list, extra: dict | None = None) -> dict:
    problems = []
    mixed = 0
    for row in rows:
        if row.get("status") == 200:
            issues = validate_decide_200(row["transaction_id"], row.get("body"))
            if "transaction_id_mismatch" in issues:
                mixed += 1
            problems.extend(issues)
        text = str(row.get("body"))
        if row.get("error") and "Traceback" in str(row.get("error")):
            problems.append("traceback_in_transport_error")
        if "Traceback" in text:
            problems.append("traceback_in_body")
    lat = [r["ms"] for r in rows if r.get("ms") is not None]
    summary = {
        "scenario": name,
        "total_completed": len(rows),
        "breakdown": status_breakdown(rows),
        "latency_ms": percentiles(lat),
        "data_mix_count": mixed,
        "integrity_problem_counts": _count(problems),
        **(extra or {}),
    }
    return summary


def _count(items: list) -> dict:
    out = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return out


def identical_scoring_check(rows: list) -> dict:
    tuples = []
    for row in rows:
        if row.get("status") != 200 or not isinstance(row.get("body"), dict):
            continue
        body = row["body"]
        tuples.append(
            (
                body.get("selected_action"),
                body.get("selected_ev"),
                body.get("selected_probability"),
            )
        )
    unique = {t for t in tuples}
    return {
        "scored_200": len(tuples),
        "unique_action_ev_prob_triples": len(unique),
        "consistent": len(unique) <= 1,
        "observed_triples": [list(t) for t in unique],
    }


def race_burst(client: httpx.Client, burst_id: int, workers: int = 20) -> dict:
    txn = f"m10-race-burst-{burst_id}"
    payloads = [scoring_payload(transaction_id=txn) for _ in range(workers)]
    rows = run_pool(client, payloads, workers=workers, deadline=time.time() + 60)
    audit = client.get(f"/audit/{txn}")
    try:
        audit_body = audit.json()
    except Exception:
        audit_body = {"raw": audit.text[:500]}
    records = audit_body.get("records") if isinstance(audit_body, dict) else None
    row_count = len(records) if isinstance(records, list) else None
    ok_200 = [r for r in rows if r.get("status") == 200]
    trace_ids = [
        r["body"].get("trace_id")
        for r in ok_200
        if isinstance(r.get("body"), dict)
    ]
    non_null = [t for t in trace_ids if t]
    null_traces = len(trace_ids) - len(non_null)
    return {
        "burst_id": burst_id,
        "transaction_id": txn,
        "http_completed": len(rows),
        "http_200": len(ok_200),
        "null_trace_id_on_200": null_traces,
        "distinct_non_null_trace_ids": len(set(non_null)),
        "audit_status": audit.status_code,
        "audit_row_count": row_count,
        "explainable_if_rows_le_200": True,
        "unexplained_missing_row": (
            row_count is not None
            and row_count < len(ok_200) - null_traces
        ),
        "summary": summarize(f"race_burst_{burst_id}", rows),
    }


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="m10_decide_", dir=str(ARTIFACTS))
    db_path = str(Path(tmp) / "isolated.db")
    handle = start_isolated_server(db_path)
    timeout = httpx.Timeout(60.0, connect=10.0)
    limits = httpx.Limits(max_connections=250, max_keepalive_connections=250)
    client = httpx.Client(base_url=handle["base_url"], timeout=timeout, limits=limits)
    report = {"db_path": db_path, "base_url": handle["base_url"], "scenarios": {}}
    try:
        scenarios = [
            ("baseline", 10, 500, 60),
            ("moderate", 50, 2000, 120),
            ("peak", 200, 5000, 180),
        ]
        for name, workers, total, max_s in scenarios:
            payloads = [
                scoring_payload(transaction_id=f"m10-{name}-{i}-{time.time_ns()}")
                for i in range(total)
            ]
            t0 = time.time()
            rows = run_pool(client, payloads, workers=workers, deadline=t0 + max_s)
            elapsed = time.time() - t0
            extra = {
                "requested": total,
                "workers": workers,
                "max_seconds": max_s,
                "elapsed_seconds": elapsed,
                "stopped_early": elapsed >= max_s and len(rows) < total,
                "identical_scoring": identical_scoring_check(rows),
            }
            report["scenarios"][name] = summarize(name, rows, extra)
            write_json(f"decide_{name}_sample.json", rows[:25])

        bursts = []
        for i in range(25):
            bursts.append(race_burst(client, i))
        unexplained = sum(1 for b in bursts if b["unexplained_missing_row"])
        report["scenarios"]["same_transaction_id_race"] = {
            "bursts": 25,
            "workers_per_burst": 20,
            "requests_per_burst": 20,
            "unexplained_missing_row_bursts": unexplained,
            "burst_summaries": bursts,
        }
    finally:
        client.close()
        stop_isolated_server(handle)

    out = write_json("decide_load_summary.json", report)
    print(json_dumps_preview(report))
    print(f"Wrote {out}")


def json_dumps_preview(report: dict) -> str:
    import json

    slim = {
        "db_path": report["db_path"],
        "base_url": report["base_url"],
        "scenarios": {},
    }
    for key, val in report["scenarios"].items():
        if key == "same_transaction_id_race":
            slim["scenarios"][key] = {
                "bursts": val["bursts"],
                "unexplained_missing_row_bursts": val["unexplained_missing_row_bursts"],
                "example_burst": val["burst_summaries"][0],
            }
        else:
            copy = dict(val)
            slim["scenarios"][key] = copy
    return json.dumps(slim, indent=2, default=str)


if __name__ == "__main__":
    main()
