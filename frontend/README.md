# IKAP Frontend

## What is included

- Landing page
- Chat UI
- Source cards for retrieved KB evidence
- Vite proxy for local `/api/*` calls to the IKAP backend

## Local development

Start the backend API from the repo root:

```bash
.venv/bin/python -m uvicorn backend.api.app:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, start the frontend:

```bash
cd frontend
npm install
npm run dev
```

By default, the Vite dev server runs on `http://127.0.0.1:8080` and proxies `/api/*` requests to `http://127.0.0.1:8000`.

## Optional environment override

If you want the frontend to call a different backend host or use a different local dev port, create `frontend/.env` with:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
VITE_DEV_PORT=8080
```
