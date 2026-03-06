#!/usr/bin/env python3
import argparse, json, math, os, re
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

EMBED_MODEL = "text-embedding-3-small"
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-12)


def load_jsonl(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_index(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def retrieve(index, query, top_k):
    q_emb = client.embeddings.create(model=EMBED_MODEL, input=query).data[0].embedding
    scored = [(cosine(q_emb, r["embedding"]), r) for r in index]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:top_k]]


def call_model(model, system_prompt, user_query, kb_context, temperature, max_tokens):
    user_msg = f"Retrieved KB Context:\n{kb_context}\n\nUser question:\n{user_query}"
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_msg},
        ],
    )
    return resp.choices[0].message.content


def score_output(text: str):
    format_ok = all(
        k in text
        for k in [
            "Category:",
            "Clarifying question:",
            "Steps",
            "If this does not resolve your issue:",
        ]
    )
    url_ok = URL_RE.search(text) is None
    steps_count = len(re.findall(r"(?m)^\d+\.\s+", text))
    return {
        "format_ok": int(format_ok),
        "no_raw_url": int(url_ok),
        "steps_count": steps_count,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--system_prompt_file", required=True)
    ap.add_argument("--index", default="data/rag/kb_index.jsonl")
    ap.add_argument("--test_file", default="data/dataset/splits/test.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--top_k", type=int, default=4)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--max_tokens", type=int, default=500)
    args = ap.parse_args()

    system_prompt = Path(args.system_prompt_file).read_text(encoding="utf-8")
    index = load_index(Path(args.index))
    test_rows = load_jsonl(Path(args.test_file))

    results = []
    totals = {"format_ok": 0, "no_raw_url": 0, "steps_count": 0}

    for r in test_rows:
        q = r["user_query"]
        top = retrieve(index, q, args.top_k)

        # assemble KB context (already sanitized in index build)
        ctx_blocks = [
            f"[{x['kb_id']} | chunk {x['chunk_id']}]\n{x['text']}" for x in top
        ]
        ctx = "\n\n---\n\n".join(ctx_blocks)

        out_text = call_model(
            args.model, system_prompt, q, ctx, args.temperature, args.max_tokens
        )
        scores = score_output(out_text)

        totals["format_ok"] += scores["format_ok"]
        totals["no_raw_url"] += scores["no_raw_url"]
        totals["steps_count"] += scores["steps_count"]

        results.append(
            {
                "id": r["id"],
                "use_case": r.get("use_case"),
                "case_type": r.get("case_type"),
                "user_query": q,
                "retrieved": [
                    {
                        "kb_id": x["kb_id"],
                        "chunk_id": x["chunk_id"],
                        "title": x.get("title", ""),
                    }
                    for x in top
                ],
                "response": out_text,
                "scores": scores,
            }
        )

    n = len(results)
    summary = {
        "model": args.model,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "n": n,
        "top_k": args.top_k,
        "avg_steps": totals["steps_count"] / max(n, 1),
        "format_ok_rate": totals["format_ok"] / max(n, 1),
        "no_raw_url_rate": totals["no_raw_url"] / max(n, 1),
    }

    payload = {"summary": summary, "results": results}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("Wrote:", out_path)
    print("Summary:", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
