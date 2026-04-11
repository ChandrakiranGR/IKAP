from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from typing import Literal

from backend.orchestration.langchain_pipeline import IKAPLangChainPipeline


class HistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[HistoryItem] = Field(default_factory=list)


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
    mode: str
    structured: dict


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


def build_sources(chunks: list[dict]) -> list[SourcePayload]:
    sources = []
    for idx, chunk in enumerate(chunks or [], start=1):
        snippet = (chunk.get("text") or "").strip()
        snippet = " ".join(snippet.split())
        if len(snippet) > 320:
            snippet = snippet[:317].rstrip() + "..."

        sources.append(
            SourcePayload(
                chunk_id=str(chunk.get("chunk_id") or f"{chunk.get('kb_id', 'kb')}-{idx}"),
                article_title=str(chunk.get("title") or "Untitled article"),
                article_id=str(chunk.get("kb_id")) if chunk.get("kb_id") else None,
                section=str(chunk.get("section")) if chunk.get("section") else None,
                source_url=str(chunk.get("url")) if chunk.get("url") else None,
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
    result = pipeline.invoke_response(
        question,
        history=[item.model_dump() for item in payload.history],
    )
    answer = result["answer"]
    mode = result.get("mode") or "grounded"
    structured = result.get("structured") or {}
    sources = build_sources(result.get("chunks") or []) if mode == "grounded" else []

    return ChatResponse(
        answer=answer,
        sources=sources,
        confidence=result.get("confidence") or infer_confidence(len(sources)),
        mode=mode,
        structured=structured,
    )
