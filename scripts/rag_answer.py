#!/usr/bin/env python3
import argparse, json, math, os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

EMBED_MODEL = "text-embedding-3-small"


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-12)


def load_index(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="data/rag/kb_index.jsonl")
    ap.add_argument("--system_prompt_file", required=True)
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--query", required=True)
    ap.add_argument("--top_k", type=int, default=4)
    ap.add_argument("--max_tokens", type=int, default=500)
    ap.add_argument("--temperature", type=float, default=0.3)
    args = ap.parse_args()

    system_prompt = Path(args.system_prompt_file).read_text(encoding="utf-8")
    index = load_index(Path(args.index))

    q_emb = (
        client.embeddings.create(model=EMBED_MODEL, input=args.query).data[0].embedding
    )

    scored = []
    for r in index:
        scored.append((cosine(q_emb, r["embedding"]), r))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [r for _, r in scored[: args.top_k]]

    context_blocks = []
    for r in top:
        context_blocks.append(f"[{r['kb_id']} | chunk {r['chunk_id']}]\n{r['text']}")
    context_text = "\n\n---\n\n".join(context_blocks)

    user_msg = f"Retrieved KB Context:\n{context_text}\n\nUser question:\n{args.query}"

    resp = client.chat.completions.create(
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_msg},
        ],
    )

    print(resp.choices[0].message.content)


if __name__ == "__main__":
    main()
