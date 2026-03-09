#!/usr/bin/env python3
import argparse
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import urldefrag

from dotenv import load_dotenv
from openai import OpenAI

EMBED_MODEL = "text-embedding-3-small"
URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)

PLATFORM_TERMS = {
    "android",
    "iphone",
    "ios",
    "windows",
    "mac",
    "macos",
    "chromebook",
    "ipad",
    "linux",
}

DOMAIN_TERMS = {
    "nuwave",
    "eduroam",
    "duo",
    "mfa",
    "vpn",
    "canvas",
    "student hub",
    "password",
    "account",
    "guest",
    "touch id",
    "new phone",
    "trusted devices",
}

STOPWORDS = {
    "how",
    "do",
    "i",
    "to",
    "on",
    "an",
    "a",
    "the",
    "is",
    "my",
    "and",
    "for",
    "of",
    "in",
    "with",
    "phone",
    "device",
    "connect",
    "use",
}


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def tokenize(s: str):
    return [
        t for t in re.findall(r"[a-z0-9]+", normalize_text(s)) if t not in STOPWORDS
    ]


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


def normalize_url(url: str) -> str:
    if not url:
        return ""
    url = urldefrag(url.strip())[0]
    return url.rstrip(").,;]>")


def extract_urls(text: str):
    return [normalize_url(u) for u in URL_RE.findall(text)]


def load_retrieved_links(kb_dir: Path, kb_ids: list[str], limit: int = 10):
    seen = set()
    out = []

    for kb_id in kb_ids:
        kb_path = kb_dir / f"{kb_id}.json"
        if not kb_path.exists():
            continue

        kb = json.loads(kb_path.read_text(encoding="utf-8"))
        title = kb.get("title") or kb_id

        for link in kb.get("links", []):
            text = (link.get("text") or "").strip() or title
            url = normalize_url(link.get("url") or "")
            if not url:
                continue
            key = (text, url)
            if key in seen:
                continue
            seen.add(key)
            out.append({"kb_id": kb_id, "text": text, "url": url})
            if len(out) >= limit:
                return out

    return out


def extract_required_terms(query: str):
    q = normalize_text(query)
    required = []

    for term in sorted(DOMAIN_TERMS | PLATFORM_TERMS, key=len, reverse=True):
        if term in q:
            required.append(term)

    return required


def title_contains_all(title: str, terms: list[str]) -> bool:
    t = normalize_text(title)
    return all(term in t for term in terms)


def text_contains_all(text: str, terms: list[str]) -> bool:
    t = normalize_text(text)
    return all(term in t for term in terms)


def wrong_platform_penalty(query_terms: list[str], title: str) -> float:
    requested_platforms = [t for t in query_terms if t in PLATFORM_TERMS]
    if not requested_platforms:
        return 0.0

    requested = set(requested_platforms)
    title_l = normalize_text(title)

    present_other = [p for p in PLATFORM_TERMS if p in title_l and p not in requested]
    if present_other:
        return -0.30

    return 0.0


def keyword_overlap_bonus(query: str, title: str, text: str) -> float:
    q_tokens = set(tokenize(query))
    title_tokens = set(tokenize(title))
    text_tokens = set(tokenize(text))

    title_overlap = len(q_tokens & title_tokens)
    text_overlap = len(q_tokens & text_tokens)

    bonus = 0.0
    bonus += min(title_overlap * 0.06, 0.24)
    bonus += min(text_overlap * 0.02, 0.12)
    return bonus


def hybrid_score(query: str, query_emb, row: dict, required_terms: list[str]) -> float:
    base = cosine(query_emb, row["embedding"])
    title = row.get("title", "")
    text = row.get("text", "")

    bonus = 0.0
    if required_terms and title_contains_all(title, required_terms):
        bonus += 0.45
    elif required_terms and text_contains_all(f"{title} {text}", required_terms):
        bonus += 0.18

    bonus += keyword_overlap_bonus(query, title, text)
    bonus += wrong_platform_penalty(required_terms, title)

    return base + bonus


def retrieve(client: OpenAI, index, query: str, top_k: int):
    q_emb = client.embeddings.create(model=EMBED_MODEL, input=query).data[0].embedding
    required_terms = extract_required_terms(query)

    scored = []
    for r in index:
        score = hybrid_score(query, q_emb, r, required_terms)
        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    top = []
    for score, row in scored[:top_k]:
        item = dict(row)
        item["_score"] = round(score, 4)
        top.append(item)
    return top


def build_context(top_chunks):
    blocks = []
    for r in top_chunks:
        title = r.get("title", "")
        kb_id = r["kb_id"]
        chunk_id = r["chunk_id"]
        text = r["text"]
        blocks.append(f"[{kb_id} | {title} | chunk {chunk_id}]\n{text}")
    return "\n\n---\n\n".join(blocks)


def build_links_block(retrieved_links):
    if not retrieved_links:
        return "Retrieved Links:\nNone"

    lines = ["Retrieved Links:"]
    for l in retrieved_links:
        lines.append(f"- {l['kb_id']} | {l['text']}: {l['url']}")
    return "\n".join(lines)


def call_model(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_query: str,
    kb_context: str,
    links_block: str,
    temperature: float,
    max_tokens: int,
):
    user_msg = f"""User question:
{user_query}

Retrieved KB Context:
{kb_context}

{links_block}
"""
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


def score_output(text: str, allowed_urls: set[str]):
    format_ok = (
        "Category:" in text
        and "Clarifying question:" in text
        and "Steps (KB-grounded if context is provided; otherwise general guidance):"
        in text
        and "References" in text
        and "If this does not resolve your issue:" in text
    )

    steps_count = len(re.findall(r"(?m)^\d+\.\s+", text))
    response_urls = set(extract_urls(text))
    grounded_url_ok = int(all(u in allowed_urls for u in response_urls))

    return {
        "format_ok": int(format_ok),
        "grounded_url_ok": grounded_url_ok,
        "steps_count": steps_count,
        "response_urls": sorted(response_urls),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--system_prompt_file", required=True)
    ap.add_argument("--index", default="data/rag/kb_index.jsonl")
    ap.add_argument("--kb_dir", default="data/processed/kb_json")
    ap.add_argument("--test_file", default="data/dataset/splits/test.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--top_k", type=int, default=4)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--max_tokens", type=int, default=500)
    args = ap.parse_args()

    load_dotenv(dotenv_path=Path(".env"))
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found. Put it in .env or export it.")

    client = OpenAI(api_key=api_key)

    system_prompt = Path(args.system_prompt_file).read_text(encoding="utf-8")
    index = load_index(Path(args.index))
    test_rows = load_jsonl(Path(args.test_file))

    results = []
    totals = {"format_ok": 0, "grounded_url_ok": 0, "steps_count": 0}

    for r in test_rows:
        q = r["user_query"]
        top = retrieve(client, index, q, args.top_k)

        kb_ids = []
        for x in top:
            if x["kb_id"] not in kb_ids:
                kb_ids.append(x["kb_id"])

        retrieved_links = load_retrieved_links(Path(args.kb_dir), kb_ids, limit=10)
        allowed_urls = {
            normalize_url(x["url"]) for x in retrieved_links if x.get("url")
        }

        kb_context = build_context(top)
        links_block = build_links_block(retrieved_links)

        out_text = call_model(
            client=client,
            model=args.model,
            system_prompt=system_prompt,
            user_query=q,
            kb_context=kb_context,
            links_block=links_block,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )

        scores = score_output(out_text, allowed_urls)

        totals["format_ok"] += scores["format_ok"]
        totals["grounded_url_ok"] += scores["grounded_url_ok"]
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
                        "score": x.get("_score"),
                    }
                    for x in top
                ],
                "retrieved_links": retrieved_links,
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
        "grounded_url_rate": totals["grounded_url_ok"] / max(n, 1),
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
