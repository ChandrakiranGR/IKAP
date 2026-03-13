#!/usr/bin/env python3
import argparse
import json
import math
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


def load_jsonl(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def extract_text_and_logprobs(resp):
    choice = resp.choices[0]
    text = choice.message.content or ""

    logprobs_obj = getattr(choice, "logprobs", None)
    if logprobs_obj is None:
        raise RuntimeError("No logprobs returned by model response.")

    content = getattr(logprobs_obj, "content", None)
    if not content:
        raise RuntimeError("No token-level logprobs found in response.")

    token_logprobs = []
    for item in content:
        lp = getattr(item, "logprob", None)
        if lp is None and isinstance(item, dict):
            lp = item.get("logprob")
        if lp is not None:
            token_logprobs.append(float(lp))

    if not token_logprobs:
        raise RuntimeError("Could not parse token logprobs from response.")

    avg_logprob = sum(token_logprobs) / len(token_logprobs)
    ppl = math.exp(-avg_logprob)

    return text, avg_logprob, ppl, len(token_logprobs)


def score_prompt(
    client, model: str, system_prompt: str, user_query: str, max_tokens: int
):
    resp = client.chat.completions.create(
        model=model,
        temperature=0.0,
        max_tokens=max_tokens,
        logprobs=True,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_query.strip()},
        ],
    )
    return extract_text_and_logprobs(resp)


def summarize(rows, key_prefix: str):
    avg_ppl = sum(r[f"{key_prefix}_ppl"] for r in rows) / max(len(rows), 1)
    avg_lp = sum(r[f"{key_prefix}_avg_logprob"] for r in rows) / max(len(rows), 1)
    avg_tokens = sum(r[f"{key_prefix}_tokens"] for r in rows) / max(len(rows), 1)
    return {
        f"{key_prefix}_avg_perplexity": avg_ppl,
        f"{key_prefix}_avg_logprob": avg_lp,
        f"{key_prefix}_avg_output_tokens": avg_tokens,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--prompt_a_file", required=True)
    ap.add_argument("--prompt_b_file", required=True)
    ap.add_argument("--split_file", default="data/dataset/splits/dev.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max_tokens", type=int, default=500)
    args = ap.parse_args()

    load_dotenv(dotenv_path=Path(".env"))
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in .env")

    client = OpenAI(api_key=api_key)

    prompt_a_path = Path(args.prompt_a_file)
    prompt_b_path = Path(args.prompt_b_file)
    split_path = Path(args.split_file)

    prompt_a = prompt_a_path.read_text(encoding="utf-8")
    prompt_b = prompt_b_path.read_text(encoding="utf-8")
    rows = load_jsonl(split_path)

    results = []
    better_b_count = 0
    equal_count = 0

    for r in rows:
        user_query = r["user_query"]

        text_a, avg_lp_a, ppl_a, toks_a = score_prompt(
            client, args.model, prompt_a, user_query, args.max_tokens
        )
        text_b, avg_lp_b, ppl_b, toks_b = score_prompt(
            client, args.model, prompt_b, user_query, args.max_tokens
        )

        if ppl_b < ppl_a:
            better_b_count += 1
        elif abs(ppl_b - ppl_a) < 1e-9:
            equal_count += 1

        results.append(
            {
                "id": r["id"],
                "user_query": user_query,
                "prompt_a_avg_logprob": avg_lp_a,
                "prompt_a_ppl": ppl_a,
                "prompt_a_tokens": toks_a,
                "prompt_a_response": text_a,
                "prompt_b_avg_logprob": avg_lp_b,
                "prompt_b_ppl": ppl_b,
                "prompt_b_tokens": toks_b,
                "prompt_b_response": text_b,
            }
        )

    summary = {
        "model": args.model,
        "n": len(results),
        "prompt_a_file": str(prompt_a_path),
        "prompt_b_file": str(prompt_b_path),
        **summarize(results, "prompt_a"),
        **summarize(results, "prompt_b"),
        "prompt_b_better_count": better_b_count,
        "equal_count": equal_count,
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
