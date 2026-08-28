# M9 Dashboard Under Load — Observation Notes (Category 7)

## Status: BLOCKED / NOT EXECUTED (Real browser observation unavailable in agent environment)

> **Category 7 Status**: Unexecuted due to environment constraints. As required by the M10 specification and review guidelines, expected UI behavior is **not** substituted for actual observation.

---

## 1. Execution Context & Environmental Limitation

- **Environment Barrier**: The automated agent environment on Windows encounters a platform-level binary resolution issue (`exec: C:\Users\ADMIN\Desktop\recovery\powershell: executable file not found in %PATH%`). Because long-running background daemon processes cannot be spawned or kept alive by the agent, neither the isolated M8 backend (`uvicorn` on port 8000) nor the M9 React frontend (`npm run dev` on port 5173/3000) could be hosted simultaneously for headless browser driving.
- **Attempted Browser Actions**: Probing localhost HTTP endpoints (ports 8000, 3000, 8080) via the browser subagent confirmed `ERR_CONNECTION_REFUSED` because no backend/frontend servers could be kept running in the background.
- **Result**: Real-browser visual inspection, health polling observation under live load, UI form submission, and browser console inspection **were not executed**.

---

## 2. Manual Execution Protocol (For External Verification)

To execute Category 7 in a standard interactive terminal environment with a real browser:

```bash
# Terminal 1 — Start isolated M8 backend
cd C:\Users\ADMIN\Desktop\recovery
python -c "from test_m10._common import start_isolated_server; handle = start_isolated_server('test_m10/artifacts/m9_manual_obs.db', port=8000); print('M8 running at', handle['base_url']); import time; time.sleep(600)"

# Terminal 2 — Start M9 React dashboard (Vite proxies to localhost:8000)
cd C:\Users\ADMIN\Desktop\recovery\frontend
npm run dev

# Terminal 3 — Launch moderate load scenario against M8 (50 workers, 2,000 requests, 120s limit)
cd C:\Users\ADMIN\Desktop\recovery
python test_m10/load_decide.py
```

---

## 3. Observation Checklist (Unexecuted Template)

| Observation Item | Execution Status | Actual Result Recorded |
|---|---|---|
| Health indicator shows "ok" before load | Not Executed | *(Requires live browser observation)* |
| Health indicator reflects latency variance during load | Not Executed | *(Requires live browser observation)* |
| Health indicator recovers after load stops | Not Executed | *(Requires live browser observation)* |
| Form submission displays loading state | Not Executed | *(Requires live browser observation)* |
| Form submission resolves to rendered EV decision | Not Executed | *(Requires live browser observation)* |
| Error states (422/400/500) render error banners without blank screen | Not Executed | *(Requires live browser observation)* |
| Browser developer console for unhandled JS errors | Not Executed | *(Requires live browser observation)* |

---

## 4. Code Integrity

- **No M9 frontend code was modified** (`frontend/src/`, `frontend/package.json`, `frontend/vite.config.js` all 100% frozen and untouched).
