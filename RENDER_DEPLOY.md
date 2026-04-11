# Render Deployment

IKAP can be deployed on Render as:

1. a Python web service for the FastAPI backend
2. a static site for the React frontend

The repo includes:

- `render.yaml` for a Render blueprint
- `deploy_data/` for the tracked KB corpus and RAG index used in deployment
- `.python-version` to keep the backend on Python 3.11.11

## Before You Deploy

You need:

- a Render account
- an OpenAI API key

## Option 1: Blueprint Deploy

1. Push this branch to GitHub.
2. In Render, choose **New +** -> **Blueprint**.
3. Connect this repository.
4. When Render reads `render.yaml`, create both services:
   - `ikap-api`
   - `ikap-web`
5. Set `OPENAI_API_KEY` for the backend service.
6. After the backend is created, copy its public URL.
7. Open the frontend static site settings and set:

```text
VITE_API_BASE_URL=https://your-backend-name.onrender.com
```

8. Redeploy the frontend static site.

## Option 2: Manual Deploy

### Backend

Create a new **Web Service** with:

- Runtime: `Python`
- Build command:

```bash
pip install -r requirements.txt
```

- Start command:

```bash
uvicorn backend.api.app:app --host 0.0.0.0 --port $PORT
```

- Environment variables:

```text
OPENAI_API_KEY=your_key_here
IKAP_CORS_ORIGINS=*
```

### Frontend

Create a new **Static Site** with:

- Build command:

```bash
cd frontend && npm install && npm run build
```

- Publish directory:

```text
frontend/dist
```

- Environment variables:

```text
VITE_API_BASE_URL=https://your-backend-name.onrender.com
```

Also configure a rewrite for SPA routing:

- Source: `/*`
- Destination: `/index.html`
- Action: `Rewrite`

## Notes

- The deployed backend reads KB data from `deploy_data/` automatically if local `data/processed` and `data/rag` are not present.
- Render free services may sleep after inactivity, so the first request can be slow.
- If you refresh the `/chat` page directly, the frontend needs the SPA rewrite above to avoid a 404.
