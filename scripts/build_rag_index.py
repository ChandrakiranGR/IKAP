#!/usr/bin/env python3
import argparse
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Default embedding model for a lightweight local RAG index
DEFAULT_EMBED_MODEL = "text-embedding-3-small"

# Replace any URL-like strings with [URL]
URL_RE = re.compile(
    r"https?://\S+|www\.\S+|[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/\S+)?", re.IGNORECASE
)


def sanitize(text: str) -> str:
    """Normalize whitespace + redact URLs."""
    if not text:
        return ""
    text = URL_RE.sub("[URL]", text)
    text = " ".join(text.split())
    return text.strip()


def extract_body_from_kb(kb: dict) -> str:
    """
    Your KB JSON stores article content under:
      kb['sections'] = [{ 'heading': ..., 'text': ... }, ...]
    This converts that structure to a single body string.
    """
    secs = kb.get("sections")
    if isinstance(secs, list) and secs:
        parts = []
        for sec in secs:
            heading = sanitize((sec.get("heading") or "").strip())
            txt = sanitize((sec.get("text") or "").strip())
            if not txt:
                continue
            if heading:
                parts.append(f"{heading}\n{txt}")
            else:
                parts.append(txt)
        return "\n\n".join(parts).strip()

    # Fallback for other potential KB JSON shapes (future-proofing)
    for k in ["content_text", "body_text", "content", "body", "text"]:
        v = kb.get(k)
        if isinstance(v, str) and v.strip():
            return sanitize(v)

    return ""


def chunk_text(text: str, max_chars: int = 1400, overlap: int = 200) -> list[str]:
    """
    Simple character-based chunker with overlap.
    Works well for MVP RAG and keeps cost/complexity low.
    """
    text = text.strip()
    if not text:
        return []

    chunks = []
    i = 0
    step = max(1, max_chars - overlap)

    while i < len(text):
        chunk = text[i : i + max_chars].strip()
        if chunk:
            chunks.append(chunk)
        i += step

    return chunks


def batched(items: list[dict], batch_size: int) -> list[list[dict]]:
    if batch_size <= 0:
        batch_size = 1
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--kb_dir", default="data/processed/kb_json", help="Folder with KB JSON files"
    )
    ap.add_argument(
        "--out", default="data/rag/kb_index.jsonl", help="Output JSONL index"
    )
    ap.add_argument(
        "--limit", type=int, default=0, help="Limit KB files processed (0 = all)"
    )
    ap.add_argument(
        "--max_chars", type=int, default=1400, help="Chunk size in characters"
    )
    ap.add_argument(
        "--overlap", type=int, default=200, help="Chunk overlap in characters"
    )
    ap.add_argument(
        "--embed_model", default=DEFAULT_EMBED_MODEL, help="Embedding model name"
    )
    ap.add_argument(
        "--batch_size",
        type=int,
        default=64,
        help="Number of chunks to embed per API request",
    )
    args = ap.parse_args()

    # Avoid dotenv auto-discovery issues; explicitly load .env from repo root
    load_dotenv(dotenv_path=Path(".env"))
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not found. Make sure .env exists in repo root or export OPENAI_API_KEY."
        )

    client = OpenAI(api_key=api_key)

    kb_dir = Path(args.kb_dir)
    if not kb_dir.exists():
        raise FileNotFoundError(f"KB dir not found: {kb_dir}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(kb_dir.glob("*.json"))
    if args.limit and args.limit > 0:
        files = files[: args.limit]

    chunk_records = []
    doc_chunk_counts = []

    for fp in files:
        kb = json.loads(fp.read_text(encoding="utf-8"))

        kb_id = kb.get("article_id") or kb.get("kb_id") or fp.stem
        title = sanitize(kb.get("title") or kb.get("short_description") or "")
        article_url = kb.get("url") or kb.get("article_url") or ""

        body = extract_body_from_kb(kb)
        doc = f"Title: {title}\n\n{body}".strip()
        doc = sanitize(doc)

        if not body:
            continue

        chunks = chunk_text(doc, max_chars=args.max_chars, overlap=args.overlap)
        if not chunks:
            continue

        for idx, ch in enumerate(chunks):
            chunk_records.append(
                {
                    "kb_id": kb_id,
                    "title": title,
                    "article_url": article_url,
                    "chunk_id": idx,
                    "text": ch,
                }
            )

        doc_chunk_counts.append((kb_id, len(chunks)))

    total_docs = len(doc_chunk_counts)
    total_chunks = len(chunk_records)

    with out_path.open("w", encoding="utf-8") as f_out:
        for batch in batched(chunk_records, args.batch_size):
            embeddings = client.embeddings.create(
                model=args.embed_model,
                input=[item["text"] for item in batch],
            ).data

            for item, emb in zip(batch, embeddings):
                rec = {
                    "kb_id": item["kb_id"],
                    "title": item["title"],
                    "article_url": item["article_url"],
                    "chunk_id": item["chunk_id"],
                    "text": item["text"],
                    "embedding": emb.embedding,
                }
                f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    for kb_id, chunk_count in doc_chunk_counts:
        print(f"Indexed {kb_id} -> {chunk_count} chunks")

    print(f"\n Indexed docs: {total_docs}")
    print(f" Wrote {total_chunks} chunk embeddings to {out_path}")


if __name__ == "__main__":
    main()
