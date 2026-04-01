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

SETUP_TERMS = {
    "connect",
    "setup",
    "set up",
    "configure",
    "install",
    "enroll",
    "register",
    "update",
    "reset",
    "manage",
}

NOTE_HEADING_TERMS = {
    "introduction",
    "requirements",
    "requirement",
    "benefits",
    "limitations",
    "important",
    "notes",
    "note",
    "resource",
    "prerequisite",
    "prerequisites",
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


def retrieve(index, query: str, query_emb, top_k: int):
    required_terms = extract_required_terms(query)

    scored = []
    for r in index:
        score = hybrid_score(query, query_emb, r, required_terms)
        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    top = []
    for score, row in scored[:top_k]:
        item = dict(row)
        item["_score"] = round(score, 4)
        top.append(item)
    return top


def load_kb_json(kb_dir: Path, kb_id: str):
    kb_path = kb_dir / f"{kb_id}.json"
    if not kb_path.exists():
        return None
    return json.loads(kb_path.read_text(encoding="utf-8"))


def choose_priority_sections(kb: dict, query: str, max_sections: int = 2):
    sections = kb.get("sections", []) or []
    if not sections:
        return []

    required_terms = extract_required_terms(query)
    q_tokens = set(tokenize(query))
    query_l = normalize_text(query)
    setup_query = any(term in query_l for term in SETUP_TERMS)
    platform_query = any(term in query_l for term in PLATFORM_TERMS)
    timing_query = any(
        term in query_l
        for term in [
            "before",
            "after",
            "publish",
            "published",
            "unpublished",
        ]
    )

    scored_sections = []
    for sec in sections:
        heading = sec.get("heading", "")
        text = sec.get("text", "")
        steps = [step for step in (sec.get("steps") or []) if (step or "").strip()]
        steps_text = " ".join(steps)
        if not text.strip() and not steps_text.strip():
            continue

        score = 0.0
        heading_l = normalize_text(heading)
        body_l = normalize_text(text)
        steps_l = normalize_text(steps_text)
        combined_l = normalize_text(" ".join(part for part in [heading, text, steps_text] if part))
        note_heading = any(term in heading_l for term in NOTE_HEADING_TERMS)
        limitation_heading = "limitation" in heading_l

        if required_terms and all(term in heading_l for term in required_terms):
            score += 1.5
        elif required_terms and all(term in body_l for term in required_terms):
            score += 1.0
        elif required_terms and all(term in steps_l for term in required_terms):
            score += 1.2
        elif required_terms and all(term in combined_l for term in required_terms):
            score += 0.9

        h_tokens = set(tokenize(heading))
        b_tokens = set(tokenize(text))
        s_tokens = set(tokenize(steps_text))

        score += min(len(q_tokens & h_tokens) * 0.20, 1.0)
        score += min(len(q_tokens & b_tokens) * 0.05, 0.5)
        score += min(len(q_tokens & s_tokens) * 0.08, 0.7)

        if any(
            word in heading_l
            for word in ["connect", "setup", "configure", "install", "enroll", "reset"]
        ):
            score += 0.4

        if steps:
            score += 0.15

        if setup_query and steps:
            score += min(len(steps) * 0.05, 0.45)

        if setup_query and any(
            marker in combined_l
            for marker in [
                "eap method",
                "mschapv2",
                "certificate",
                "domain field",
                "identity field",
                "portal address",
                "globalprotect",
                "wireless.northeastern.edu",
            ]
        ):
            score += 0.6

        if platform_query and any(term in combined_l for term in PLATFORM_TERMS):
            score += 0.35

        if platform_query and "requirement" in heading_l:
            score += 0.35

        if timing_query and (
            "introduction" in heading_l
            or "benefit" in heading_l
            or "unpublished" in combined_l
            or "published" in combined_l
            or "only work after" in combined_l
        ):
            score += 0.6

        if note_heading and any(term in combined_l for term in required_terms):
            score += 0.25

        if setup_query and limitation_heading and "limitation" not in query_l:
            score -= 0.15

        scored_sections.append((score, sec))

    scored_sections.sort(key=lambda x: x[0], reverse=True)
    picked = [sec for _, sec in scored_sections[:max_sections]]

    if not picked:
        picked = [s for s in sections if (s.get("text") or "").strip()][:max_sections]

    return picked


def build_priority_block(kb: dict, query: str):
    picked = choose_priority_sections(kb, query, max_sections=2)
    if not picked:
        return ""

    lines = [f"Priority KB Article: {kb.get('article_id')} | {kb.get('title', '')}"]
    lines.append(
        "Priority KB Sections (preserve exact settings, field names, values, domain names, and version-specific branches):"
    )

    for sec in picked:
        lines.append(f"[Section] {sec.get('heading', '')}")
        body = sec.get("text", "").strip()
        if body:
            lines.append(body)
        steps = [step.strip() for step in (sec.get("steps") or []) if step.strip()]
        if steps:
            lines.append("Steps:")
            lines.extend(f"{idx}. {step}" for idx, step in enumerate(steps, start=1))

    return "\n\n".join(lines)


def synthesize_article_url(kb_id: str):
    return f"https://service.northeastern.edu/tech?id=kb_article_view&sysparm_article={kb_id}"


def load_retrieved_links(kb_dir: Path, kb_ids: list[str], limit: int = 10):
    out = []
    loaded = []
    for kb_id in kb_ids:
        kb = load_kb_json(kb_dir, kb_id)
        if not kb:
            continue

        loaded.append((kb_id, kb))
        seen_for_kb = set()
        title = kb.get("title") or kb_id

        self_url = normalize_url(kb.get("url") or "") or synthesize_article_url(kb_id)
        self_label = title
        self_key = (self_label, self_url)
        if self_url and self_key not in seen_for_kb:
            seen_for_kb.add(self_key)
            out.append({"kb_id": kb_id, "text": self_label, "url": self_url})
            if len(out) >= limit:
                return out

        kb["_seen_for_retrieved_links"] = seen_for_kb

    for kb_id, kb in loaded:
        seen_for_kb = kb.get("_seen_for_retrieved_links", set())
        title = kb.get("title") or kb_id

        for link in kb.get("links", []):
            text = (link.get("text") or "").strip() or title
            url = normalize_url(link.get("url") or "")
            if not url:
                continue
            key = (text, url)
            if key in seen_for_kb:
                continue
            seen_for_kb.add(key)
            out.append({"kb_id": kb_id, "text": text, "url": url})
            if len(out) >= limit:
                return out

    return out


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


def strip_markdown_formatting(text: str) -> str:
    # Remove bold/italic markdown markers while preserving the content
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.*?) (?<!\*)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_(?!_)(.*?) (?<!_)_(?!_)", r"\1", text)
    return text


def clean_spacing(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def postprocess_response(text: str) -> str:
    cleaned = []
    for line in text.splitlines():
        low = line.strip().lower()
        if "trained on data up to" in low:
            continue
        if "knowledge cutoff" in low:
            continue
        cleaned.append(line)

    text = "\n".join(cleaned).strip()
    text = strip_markdown_formatting(text)
    text = clean_spacing(text)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="data/rag/kb_index.jsonl")
    ap.add_argument("--kb_dir", default="data/processed/kb_json")
    ap.add_argument("--system_prompt_file", required=True)
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--query", required=True)
    ap.add_argument("--top_k", type=int, default=4)
    ap.add_argument("--max_tokens", type=int, default=800)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    load_dotenv(dotenv_path=Path(".env"))
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found. Put it in .env or export it.")

    client = OpenAI(api_key=api_key)

    system_prompt = Path(args.system_prompt_file).read_text(encoding="utf-8")
    index = load_index(Path(args.index))

    q_emb = (
        client.embeddings.create(model=EMBED_MODEL, input=args.query).data[0].embedding
    )
    top = retrieve(index, args.query, q_emb, args.top_k)

    kb_ids = []
    for r in top:
        if r["kb_id"] not in kb_ids:
            kb_ids.append(r["kb_id"])

    primary_kb = load_kb_json(Path(args.kb_dir), kb_ids[0]) if kb_ids else None
    priority_block = build_priority_block(primary_kb, args.query) if primary_kb else ""

    retrieved_links = load_retrieved_links(Path(args.kb_dir), kb_ids, limit=10)
    kb_context = build_context(top)
    links_block = build_links_block(retrieved_links)

    user_msg = f"""User question:
{args.query}

{priority_block}

Retrieved KB Context:
{kb_context}

{links_block}

Important generation rule:
When Priority KB Sections are provided, preserve every exact configuration value, field name, version-specific branch, and required setting from those sections. Do not compress away domain names, certificate options, identity field instructions, or OS-version-specific differences.
Do not use markdown formatting such as bold (**), italics (*), or underscores for emphasis.
"""

    if args.debug:
        print("=== Retrieved Chunks ===")
        for r in top:
            print(
                f"{r['kb_id']} | score={r['_score']} | chunk {r['chunk_id']} | {r.get('title', '')}"
            )
        print("\n=== Priority KB ===")
        if primary_kb:
            print(primary_kb.get("article_id"), "|", primary_kb.get("title"))
            print(priority_block[:1500])
        else:
            print("None")
        print("\n=== Retrieved Links ===")
        if retrieved_links:
            for l in retrieved_links:
                print(f"{l['kb_id']} | {l['text']} | {l['url']}")
        else:
            print("None")
        print("\n=== Model Response ===")

    resp = client.chat.completions.create(
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_msg},
        ],
    )

    final_text = postprocess_response(resp.choices[0].message.content)
    print(final_text)


if __name__ == "__main__":
    main()
