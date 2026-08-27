# M9 — React Dashboard

Operator UI for the frozen M8 FastAPI backend. Talks only to `GET /health`, `POST /decide`, and `GET /audit/{transaction_id}` via the Vite same-origin proxy (no CORS change to M8).

## Run

From the repository root, start M8 on port 8000:

```text
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Then, from `frontend/`:

```text
npm install
npm run dev
```

Open the URL Vite prints (typically `http://127.0.0.1:5173`). Browser requests to `/health`, `/decide`, and `/audit` are proxied to M8.

## Tests

```text
npm test
```

Tests use mocked `fetch` only; M8 does not need to be running.
