from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.orchestration.langchain_pipeline import IKAPLangChainPipeline
from backend.orchestration.retrieval_adapter import retrieve_kb_chunks


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class SourcePayload(BaseModel):
    chunk_id: str
    article_title: str
    article_id: str | None = None
    section: str | None = None
    source_url: str | None = None
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourcePayload]
    confidence: str


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _cors_origins() -> list[str]:
    configured = os.getenv(
        "IKAP_CORS_ORIGINS",
        "http://127.0.0.1:8080,http://localhost:8080,http://127.0.0.1:5173,http://localhost:5173",
    )
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


load_dotenv(_project_root() / ".env")

app = FastAPI(title="IKAP API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_pipeline() -> IKAPLangChainPipeline:
    return IKAPLangChainPipeline(top_k=4)


def build_sources(question: str) -> list[SourcePayload]:
    chunks = retrieve_kb_chunks(question, top_k=4)
    sources = []
    for idx, chunk in enumerate(chunks, start=1):
        snippet = (chunk.get("text") or "").strip()
        snippet = " ".join(snippet.split())
        if len(snippet) > 320:
            snippet = snippet[:317].rstrip() + "..."

        sources.append(
            SourcePayload(
                chunk_id=chunk.get("chunk_id") or f"{chunk.get('kb_id', 'kb')}-{idx}",
                article_title=chunk.get("title") or "Untitled article",
                article_id=chunk.get("kb_id") or None,
                section=chunk.get("section") or None,
                source_url=chunk.get("url") or None,
                snippet=snippet,
            )
        )
    return sources


def infer_confidence(source_count: int) -> str:
    if source_count >= 3:
        return "high"
    if source_count >= 1:
        return "medium"
    return "low"


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    pipeline = get_pipeline()
    answer = pipeline.invoke(question)
    sources = build_sources(question)

    return ChatResponse(
        answer=answer,
        sources=sources,
        confidence=infer_confidence(len(sources)),
    )
