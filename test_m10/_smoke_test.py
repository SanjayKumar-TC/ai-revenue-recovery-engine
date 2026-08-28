"""
M10 smoke test — Task 4 only.
Starts isolated M8, calls GET /health, asserts 200, shuts down.
Does NOT run any load/boundary/fault scenarios.
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import start_isolated_server, stop_isolated_server, ARTIFACTS  # noqa: E402

import urllib.request

ARTIFACTS.mkdir(parents=True, exist_ok=True)
tmp = tempfile.mkdtemp(prefix="m10_smoke_", dir=str(ARTIFACTS))
db_path = str(Path(tmp) / "smoke.db")

print(f"Starting isolated server with db={db_path} ...")
handle = start_isolated_server(db_path)
base = handle["base_url"]
print(f"Server up at {base}")

try:
    with urllib.request.urlopen(base + "/health", timeout=5) as resp:
        status = resp.status
        body = resp.read().decode()
    print(f"GET /health -> HTTP {status}  body={body}")
    assert status == 200, f"Expected 200, got {status}"
    print("SMOKE TEST PASSED")
finally:
    stop_isolated_server(handle)
    print("Server stopped.")
