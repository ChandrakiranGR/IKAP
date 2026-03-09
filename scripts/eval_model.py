#!/usr/bin/env python3
import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import urldefrag

from dotenv import load_dotenv
from openai import OpenAI

URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)


def load_jsonl(path: Path):
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


def call(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_query: str,
    temperature: float,
    max_tokens: int,
):
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_query.strip()},
        ],
    )
    return resp.choices[0].message.content


def score_output(text: str):
    format_ok = (
        "Category:" in text
        and "Clarifying question:" in text
        and "Steps (KB-grounded if context is provided; otherwise general guidance):"
        in text
        and "References" in text
        and "If this does not resolve your issue:" in text
    )
    response_urls = extract_urls(text)
    steps_count = len(re.findall(r"(?m)^\d+\.\s+", text))

    # Prompt-only path: any URL is ungrounded
    grounded_url_ok = int(len(response_urls) == 0)

    return {
        "format_ok": int(format_ok),
        "grounded_url_ok": grounded_url_ok,
        "steps_count": steps_count,
        "response_urls": response_urls,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--system_prompt_file", required=True)
    ap.add_argument("--test_file", default="data/dataset/splits/test.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--max_tokens", type=int, default=500)
    args = ap.parse_args()

    load_dotenv(dotenv_path=Path(".env"))
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found. Put it in .env or export it.")

    client = OpenAI(api_key=api_key)

    system_prompt = Path(args.system_prompt_file).read_text(encoding="utf-8")
    test_rows = load_jsonl(Path(args.test_file))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    totals = {"format_ok": 0, "grounded_url_ok": 0, "steps_count": 0}

    for r in test_rows:
        user_query = r["user_query"]
        text = call(
            client,
            args.model,
            system_prompt,
            user_query,
            args.temperature,
            args.max_tokens,
        )
        scores = score_output(text)

        totals["format_ok"] += scores["format_ok"]
        totals["grounded_url_ok"] += scores["grounded_url_ok"]
        totals["steps_count"] += scores["steps_count"]

        results.append(
            {
                "id": r["id"],
                "use_case": r.get("use_case"),
                "case_type": r.get("case_type"),
                "user_query": user_query,
                "response": text,
                "scores": scores,
            }
        )

    n = len(results)
    summary = {
        "model": args.model,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "n": n,
        "avg_steps": totals["steps_count"] / max(n, 1),
        "format_ok_rate": totals["format_ok"] / max(n, 1),
        "grounded_url_rate": totals["grounded_url_ok"] / max(n, 1),
    }

    payload = {"summary": summary, "results": results}
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("Wrote:", out_path)
    print("Summary:", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
