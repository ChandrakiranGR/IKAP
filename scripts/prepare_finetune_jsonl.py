#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urldefrag

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

DEFAULT_SYSTEM_PROMPT = """You are IKAP (Intelligent Knowledge Assistant Platform), an AI assistant for Northeastern IT Services.

Rules:
- Follow the output format exactly.
- Use this exact structure:
  Category:
  Clarifying question:
  Steps (KB-grounded if context is provided; otherwise general guidance):
  References (only if provided in KB context/links; otherwise "None"):
  If this does not resolve your issue: Contact Northeastern IT Support and include:
- If Retrieved KB Context is provided, treat it as authoritative.
- If Retrieved Links are provided, include only grounded URLs from those links, and only in the References section.
- If no KB context is provided, give general guidance only and set References to "None".
- Never invent URLs, phone numbers, or internal system names.
- Never ask for or repeat passwords, MFA codes, backup codes, or sensitive identifiers.
- Keep the output concise but preserve exact configuration values when KB context contains them.
- Do not use markdown emphasis such as **bold** or *italics*.
"""


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def tokenize(s: str):
    return [
        t for t in re.findall(r"[a-z0-9]+", normalize_text(s)) if t not in STOPWORDS
    ]


def normalize_url(url: str) -> str:
    if not url:
        return ""
    url = urldefrag(url.strip())[0]
    return url.rstrip(").,;]>")


def load_jsonl(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_required_terms(query: str):
    q = normalize_text(query)
    required = []
    for term in sorted(DOMAIN_TERMS | PLATFORM_TERMS, key=len, reverse=True):
        if term in q:
            required.append(term)
    return required


def load_kb(kb_dir: Path, kb_id: str):
    path = kb_dir / f"{kb_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def choose_priority_sections(kb: dict, query: str, max_sections: int = 2):
    sections = kb.get("sections", []) or []
    if not sections:
        return []

    required_terms = extract_required_terms(query)
    q_tokens = set(tokenize(query))

    scored = []
    for sec in sections:
        heading = sec.get("heading", "")
        text = sec.get("text", "")
        if not text.strip():
            continue

        score = 0.0
        heading_l = normalize_text(heading)
        body_l = normalize_text(text)

        if required_terms and all(term in heading_l for term in required_terms):
            score += 1.5
        elif required_terms and all(term in body_l for term in required_terms):
            score += 1.0

        h_tokens = set(tokenize(heading))
        b_tokens = set(tokenize(text))

        score += min(len(q_tokens & h_tokens) * 0.20, 1.0)
        score += min(len(q_tokens & b_tokens) * 0.05, 0.5)

        if any(
            word in heading_l
            for word in ["connect", "setup", "configure", "install", "enroll", "reset"]
        ):
            score += 0.4

        scored.append((score, sec))

    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [sec for _, sec in scored[:max_sections]]

    if not picked:
        picked = [s for s in sections if (s.get("text") or "").strip()][:max_sections]

    return picked


def build_kb_context(kb: dict, query: str):
    picked = choose_priority_sections(kb, query, max_sections=2)
    if not picked:
        return ""

    lines = [f"[{kb.get('article_id')} | {kb.get('title', '')}]"]
    for sec in picked:
        lines.append(f"[Section] {sec.get('heading', '')}")
        lines.append((sec.get("text") or "").strip())
    return "\n\n".join(lines).strip()


def synthesize_article_url(kb_id: str):
    return f"https://service.northeastern.edu/tech?id=kb_article_view&sysparm_article={kb_id}"


def build_retrieved_links(kb: dict, limit: int = 5):
    seen = set()
    out = []

    kb_id = kb.get("article_id") or ""
    title = kb.get("title") or kb_id

    self_url = normalize_url(kb.get("url") or "") or synthesize_article_url(kb_id)
    if self_url:
        key = (title, self_url)
        if key not in seen:
            seen.add(key)
            out.append({"text": title, "url": self_url})

    for link in kb.get("links", []):
        text = (link.get("text") or "").strip() or title
        url = normalize_url(link.get("url") or "")
        if not url:
            continue
        key = (text, url)
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": text, "url": url})
        if len(out) >= limit:
            break

    return out[:limit]


def format_references(refs):
    if not refs:
        return (
            'References (only if provided in KB context/links; otherwise "None"):\nNone'
        )

    lines = ['References (only if provided in KB context/links; otherwise "None"):']
    for r in refs:
        lines.append(f"- {r['text']}: {r['url']}")
    return "\n".join(lines)


def format_assistant_output(example: dict, refs=None):
    exp = example.get("expected_output", {}) or {}
    category = exp.get("category", "General IT Support")
    steps = exp.get("steps", []) or []

    lines = [
        f"Category: {category}",
        "Clarifying question: None",
        "Steps (KB-grounded if context is provided; otherwise general guidance):",
    ]

    if not steps:
        lines.append("1. I can help with that if you share more details.")
    else:
        for i, step in enumerate(steps, start=1):
            clean = re.sub(r"\s+", " ", step).strip()
            lines.append(f"{i}. {clean}")

    lines.append(format_references(refs))
    lines.append(
        "If this does not resolve your issue: Contact Northeastern IT Support and include:"
    )
    lines.append("- Your device/OS")
    lines.append("- The step where the issue occurred")
    lines.append("- Any error message shown")

    return "\n".join(lines)


def make_prompt_only_example(example: dict, system_prompt: str):
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": example["user_query"]},
            {
                "role": "assistant",
                "content": format_assistant_output(example, refs=None),
            },
        ]
    }


def make_rag_conditioned_example(example: dict, kb_dir: Path, system_prompt: str):
    kb_ids = (example.get("source") or {}).get("kb_ids") or []
    if not kb_ids:
        return None

    kb = load_kb(kb_dir, kb_ids[0])
    if not kb:
        return None

    kb_context = build_kb_context(kb, example["user_query"])
    if not kb_context:
        return None

    links = build_retrieved_links(kb, limit=5)
    links_block = "Retrieved Links:\n"
    if links:
        for l in links:
            links_block += f"- {l['text']}: {l['url']}\n"
    else:
        links_block += "None\n"

    user_content = f"""User question:
{example["user_query"]}

Retrieved KB Context:
{kb_context}

{links_block}
"""

    refs = [links[0]] if links else None

    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content.strip()},
            {
                "role": "assistant",
                "content": format_assistant_output(example, refs=refs),
            },
        ]
    }


def build_finetune_rows(
    split_rows, kb_dir: Path, system_prompt: str, include_rag_context: bool
):
    out = []
    prompt_only_count = 0
    rag_count = 0

    for ex in split_rows:
        out.append(make_prompt_only_example(ex, system_prompt))
        prompt_only_count += 1

        if include_rag_context:
            rag_ex = make_rag_conditioned_example(ex, kb_dir, system_prompt)
            if rag_ex:
                out.append(rag_ex)
                rag_count += 1

    return out, prompt_only_count, rag_count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train_in", default="data/dataset/splits/train.jsonl")
    ap.add_argument("--valid_in", default="data/dataset/splits/dev.jsonl")
    ap.add_argument("--kb_dir", default="data/processed/kb_json")
    ap.add_argument(
        "--system_prompt_file",
        default="prompt_engineering/prompts/v3_system_prompt.txt",
    )
    ap.add_argument("--train_out", default="data/finetune/train_ft.jsonl")
    ap.add_argument("--valid_out", default="data/finetune/valid_ft.jsonl")
    ap.add_argument("--include_rag_context", action="store_true")
    args = ap.parse_args()

    train_rows = load_jsonl(Path(args.train_in))
    valid_rows = load_jsonl(Path(args.valid_in))
    kb_dir = Path(args.kb_dir)

    system_prompt_path = Path(args.system_prompt_file)
    if system_prompt_path.exists():
        system_prompt = system_prompt_path.read_text(encoding="utf-8").strip()
    else:
        system_prompt = DEFAULT_SYSTEM_PROMPT

    train_ft, train_prompt_only, train_rag = build_finetune_rows(
        train_rows, kb_dir, system_prompt, include_rag_context=args.include_rag_context
    )
    valid_ft, valid_prompt_only, valid_rag = build_finetune_rows(
        valid_rows, kb_dir, system_prompt, include_rag_context=args.include_rag_context
    )

    write_jsonl(Path(args.train_out), train_ft)
    write_jsonl(Path(args.valid_out), valid_ft)

    print(f"Wrote train fine-tune file: {args.train_out}")
    print(f"  prompt-only examples: {train_prompt_only}")
    print(f"  rag-conditioned examples: {train_rag}")
    print(f"  total rows: {len(train_ft)}")

    print(f"Wrote valid fine-tune file: {args.valid_out}")
    print(f"  prompt-only examples: {valid_prompt_only}")
    print(f"  rag-conditioned examples: {valid_rag}")
    print(f"  total rows: {len(valid_ft)}")


if __name__ == "__main__":
    main()
