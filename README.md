# IKAP

IKAP is a KB-grounded AI assistant for Northeastern IT support workflows. It uses a cleaned knowledge-base corpus, a local RAG index, and an API-backed chat frontend to answer questions with step-by-step guidance and source links.

## Current Architecture

The active app flow is:

1. React frontend in `frontend/`
2. FastAPI backend in `backend/api/app.py`
3. Retrieval orchestration in `backend/orchestration/langchain_pipeline.py` and `backend/orchestration/retrieval_adapter.py`
4. Processed KB corpus in `data/processed/kb_json/`
5. RAG index in `data/rag/kb_index.jsonl`
6. Prompt loading from `prompt_engineering/prompts/v4_system_prompt.txt`

The current production default model is `gpt-4o-mini`, with retrieval grounded in the processed KB corpus.

## Repository Structure

```text
IKAP/
├── backend/
│   ├── api/                    # FastAPI chat API
│   └── orchestration/          # Prompt + retrieval runtime
├── data/
│   ├── raw/                    # Raw KB exports (gitignored)
│   ├── processed/kb_json/      # One JSON file per KB article (gitignored)
│   ├── rag/                    # Retrieval index artifacts (gitignored)
│   └── manifests/              # Lightweight tracked manifests
├── frontend/                   # React/Vite chat UI
├── prompt_engineering/         # Prompt assets and experiment history
├── scripts/                    # Data prep, RAG build, eval, and fine-tune tooling
├── requirements.txt
└── README.md
```

## What Is Included

- KB-only RAG pipeline for Northeastern IT articles
- Processed KB corpus and index build scripts
- FastAPI chat endpoint with source cards
- React chat frontend
- Retrieval and answer evaluation tooling
- Fine-tune preparation and launch tooling

## What Is Not In The Active Path

- Incident data for MVP answers
- Supabase-backed frontend flows
- Database-backed article management
- Legacy HTML KB ingestion

## Local Setup

### 1. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/pip install -r requirements.txt
```

### 2. Frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 3. Environment variables

Copy `.env.example` to `.env` and set your OpenAI key:

```bash
cp .env.example .env
```

Minimum required variable:

```bash
OPENAI_API_KEY=your_api_key_here
```

## Running The App

### Backend

```bash
.venv/bin/python -m uvicorn backend.api.app:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd frontend
npm run dev
```

If you want the frontend to call a non-default backend URL, set:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Render Deployment

This repo includes a Render blueprint at [`render.yaml`](/Users/chandrakirangr/Documents/IKAP/render.yaml) and deployment notes in [`RENDER_DEPLOY.md`](/Users/chandrakirangr/Documents/IKAP/RENDER_DEPLOY.md).

Important:

- the deployed backend uses the tracked KB/index bundle in `deploy_data/`
- you must set `OPENAI_API_KEY` on the backend service
- you must set `VITE_API_BASE_URL` on the frontend static site to your backend Render URL

## API Endpoints

- `GET /api/health`
- `POST /api/chat`

Example request:

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"How do I connect to VPN on my Mac?"}'
```

## Rebuilding KB Data And Retrieval

The active KB pipeline is:

```text
data/raw -> scripts/raw_kb_to_processed.py -> data/processed/kb_json -> scripts/build_rag_index.py -> data/rag/kb_index.jsonl
```

Typical rebuild flow:

```bash
python3 scripts/rebuild_kb_corpus.py
python3 scripts/build_rag_index.py --kb_dir data/processed/kb_json --out data/rag/kb_index.jsonl --batch_size 64
```

## Evaluation

Retrieval benchmark:

```bash
python3 scripts/run_retrieval_benchmark.py
```

Answer evaluation:

```bash
.venv/bin/python scripts/run_answer_eval.py --cases data/benchmarks/answer_eval_cases_extended.json --top_k 4 --out data/benchmarks/results/answer_eval_results_extended.json
```

## Notes

- Most generated data artifacts are gitignored by design.
- The app is currently file-based, not database-backed.
- The frontend no longer depends on Supabase in the active app path.
