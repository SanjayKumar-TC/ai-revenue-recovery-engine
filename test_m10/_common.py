"""
M10 shared helpers: isolated M8 server, payloads, stats.
Never points at ml/audit/audit_trail.db.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Empty, Queue
from typing import Any, Callable, Dict, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
REAL_AUDIT_DB = (REPO_ROOT / "ml" / "audit" / "audit_trail.db").resolve()

DECIDE_200_FIELDS = [
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
]
COMM_FIELDS = ["sendable", "channel", "message_body", "fallback_used"]
AUDIT_RECORD_FIELDS = [
    "trace_id",
    "timestamp",
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
    "selected_ev",
    "selected_probability",
    "m6_sendable",
    "m6_channel",
    "m6_fallback_used",
]


def assert_isolated_db(db_path: str) -> str:
    resolved = Path(db_path).resolve()
    if resolved == REAL_AUDIT_DB:
        raise RuntimeError("Refusing to use the real M7 audit database.")
    return str(resolved)


def scoring_payload(**overrides) -> Dict[str, Any]:
    body = {
        "transaction_id": f"m10-{uuid.uuid4()}",
        "failure_type": "temporary_bank_decline",
        "amount": 2000.0,
        "attempt_number": 1,
        "risk_score": 0.15,
        "contact_fatigue": 0.1,
        "hours_since_failure": 6.0,
        "current_discount_percent": 10.0,
        "customer_segment": "b2c_new",
        "already_recovered": False,
        "customer_name": "M10 Load",
        "communication_channel": "email",
        "payment_link_url": "https://checkout.example.com/pay/m10",
    }
    body.update(overrides)
    return body


def percentiles(values: List[float]) -> Dict[str, Optional[float]]:
    if not values:
        return {"p50": None, "p95": None, "p99": None}
    ordered = sorted(values)
    def pct(p: float) -> float:
        if len(ordered) == 1:
            return ordered[0]
        idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
        return ordered[idx]
    return {"p50": pct(50), "p95": pct(95), "p99": pct(99)}


def status_breakdown(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    errors = 0
    for row in rows:
        if row.get("error") and row.get("status") is None:
            errors += 1
            key = "transport_error"
        else:
            key = str(row.get("status"))
        counts[key] = counts.get(key, 0) + 1
    four = {k: v for k, v in counts.items() if k.startswith("4")}
    five = sum(v for k, v in counts.items() if k.startswith("5"))
    return {
        "by_status": counts,
        "4xx": four,
        "5xx": five,
        "transport_errors": errors,
        "success_200": counts.get("200", 0),
    }


def validate_decide_200(request_txn: str, body: Any) -> List[str]:
    problems = []
    if not isinstance(body, dict):
        return ["body_not_object"]
    for field in DECIDE_200_FIELDS:
        if field not in body:
            problems.append(f"missing_{field}")
    comm = body.get("communication")
    if not isinstance(comm, dict):
        problems.append("communication_not_object")
    else:
        for field in COMM_FIELDS:
            if field not in comm:
                problems.append(f"missing_communication.{field}")
    if body.get("transaction_id") != request_txn:
        problems.append("transaction_id_mismatch")
    leak_keys = {
        "action_analysis",
        "blocked_actions",
        "allowed_actions",
        "latent_score",
        "true_prob_HIDDEN",
    }
    for key in leak_keys:
        if key in body:
            problems.append(f"leaked_{key}")
    text = json.dumps(body, default=str)
    if "Traceback" in text or "sqlite" in text.lower() or "File \"" in text:
        problems.append("possible_internal_leak")
    return problems


def validate_audit_shape(expected_txn: str, status: int, body: Any) -> List[str]:
    problems = []
    if status == 404:
        return problems
    if status != 200:
        return problems
    if not isinstance(body, dict):
        return ["body_not_object"]
    if set(body.keys()) != {"transaction_id", "records"}:
        problems.append(f"unexpected_top_keys:{sorted(body.keys())}")
    if body.get("transaction_id") != expected_txn:
        problems.append("transaction_id_mismatch")
    records = body.get("records")
    if not isinstance(records, list):
        problems.append("records_not_list")
        return problems
    for rec in records:
        if not isinstance(rec, dict):
            problems.append("record_not_object")
            continue
        missing = [f for f in AUDIT_RECORD_FIELDS if f not in rec]
        if missing:
            problems.append(f"record_missing:{missing}")
    return problems


def newest_first(records: List[dict]) -> bool:
    stamps = [r.get("timestamp") for r in records]
    return stamps == sorted(stamps, reverse=True)


def wait_health(base_url: str, timeout_s: float = 60.0) -> None:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/health", timeout=2) as resp:
                if resp.status == 200:
                    return
                last = resp.status
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.2)
    raise RuntimeError(f"Server at {base_url} did not become healthy: {last}")


def pick_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def start_isolated_server(
    db_path: str,
    port: Optional[int] = None,
    extra_env: Optional[Dict[str, str]] = None,
) -> dict:
    db_path = assert_isolated_db(db_path)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    port = port or pick_port()
    env = os.environ.copy()
    env["M10_AUDIT_DB"] = db_path
    env["M10_PORT"] = str(port)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--serve"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        wait_health(base, timeout_s=90)
    except Exception:
        proc.kill()
        out, err = proc.communicate(timeout=5)
        raise RuntimeError(
            f"Failed to start isolated M8.\nstdout={out[-2000:]!r}\nstderr={err[-4000:]!r}"
        )
    return {"proc": proc, "base_url": base, "db_path": db_path, "port": port}


def stop_isolated_server(handle: dict) -> None:
    proc = handle["proc"]
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def run_until(work_items: list, workers: int, deadline: float, fn: Callable) -> list:
    """Run fn(item) with a worker pool; stop taking new work after deadline."""
    q: Queue = Queue()
    for item in work_items:
        q.put(item)
    rows: list = []
    lock = threading.Lock()

    def worker() -> None:
        while time.time() < deadline:
            try:
                item = q.get_nowait()
            except Empty:
                return
            try:
                row = fn(item)
                with lock:
                    rows.append(row)
            finally:
                q.task_done()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(worker) for _ in range(workers)]
        for fut in as_completed(futs):
            fut.result()
    return rows


def write_json(name: str, payload: Any) -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / name
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def _serve() -> None:
    db_path = os.environ["M10_AUDIT_DB"]
    port = int(os.environ["M10_PORT"])
    assert_isolated_db(db_path)
    os.chdir(REPO_ROOT)
    from api.main import create_app
    from ml.decision.decision_engine import load_model
    import uvicorn

    model_pipeline = None
    if os.environ.get("M10_BROKEN_MODEL") == "1":

        class _BrokenModel:
            def predict_proba(self, X):
                raise RuntimeError("M10 injected model unavailable")

            def predict(self, X):
                raise RuntimeError("M10 injected model unavailable")

        model_pipeline = _BrokenModel()
    elif os.environ.get("M10_SLOW_SEC"):
        delay = float(os.environ["M10_SLOW_SEC"])
        inner, _err = load_model()

        class _SlowModel:
            def predict_proba(self, X):
                time.sleep(delay)
                return inner.predict_proba(X)

            def predict(self, X):
                time.sleep(delay)
                return inner.predict(X)

        model_pipeline = _SlowModel()

    app = create_app(audit_db_path=db_path, model_pipeline=model_pipeline)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if args.serve:
        _serve()
    else:
        parser.print_help()
