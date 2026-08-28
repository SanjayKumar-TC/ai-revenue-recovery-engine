# M10: Stress Testing & Hardening

Measurement and reporting milestone for the AI Revenue Recovery Engine.
M10 exercises the existing M1–M9 system under load, abuse, and fault
conditions and reports what it finds. It does **not** fix what it finds.

## Prerequisites

```bash
pip install httpx
```

All other dependencies (fastapi, uvicorn, joblib, numpy, pandas, scikit-learn)
must already be installed from the M1–M9 development cycle.

## Test Categories

| # | Script | Category | Description |
|---|---|---|---|
| 1 | `load_decide.py` | Concurrency/Load | POST /decide under baseline (10w/500r), moderate (50w/2000r), peak (200w/5000r) load + same-transaction race |
| 2 | `load_audit.py` | Concurrent Audit | GET /audit concurrent with moderate /decide load on same DB |
| 3 | `sqlite_contention.py` | SQLite Contention | Focused read/write contention against shared temp DB |
| 4 | `boundary_input.py` | Boundary/Abuse | Malformed, edge-case, and abuse inputs for all fields |
| 5 | `fault_injection.py` | Fault Injection | Model unavailable, M7 write failure, M6 fallback triggers |
| 6 | `dependency_audit_report.md` | Dependency Security | npm audit results + Python audit status |
| 7 | `m9_under_load_notes.md` | M9 Observation | Manual observation template for dashboard under load |

## Running Tests

Each test script is self-contained and creates its own isolated M8 server
instance with a temporary SQLite database. The real `ml/audit/audit_trail.db`
is **never** touched.

```bash
# Category 1: /decide load testing
python test_m10/load_decide.py

# Category 2: Concurrent audit reads + /decide writes
python test_m10/load_audit.py

# Category 3: SQLite contention
python test_m10/sqlite_contention.py

# Category 4: Boundary/abuse input
python test_m10/boundary_input.py

# Category 5: Fault injection
python test_m10/fault_injection.py

# Category 6: npm audit (run from frontend/)
cd frontend && npm audit --json
```

## Output

All JSON result files are written to `test_m10/artifacts/`. Each script
prints a summary to stdout and writes detailed results to JSON.

## Shared Helpers

`_common.py` provides:
- Isolated server management (`start_isolated_server`, `stop_isolated_server`)
- Audit DB safety guard (`assert_isolated_db`)
- Payload generation (`scoring_payload`)
- Response validation (`validate_decide_200`, `validate_audit_shape`)
- Worker pool with deadline-stops-submission (`run_until`)
- Statistics (`percentiles`, `status_breakdown`)

## Safety Guarantees

- **Real audit DB** (`ml/audit/audit_trail.db`) is never targeted
- All tests use freshly created temporary SQLite databases
- M1–M9 source code is never modified
- No dependencies are installed or upgraded
- No git staging or committing
