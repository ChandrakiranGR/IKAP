import argparse
import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def load_jsonl(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def call(
    model: str, system_prompt: str, user_query: str, temperature: float, max_tokens: int
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
    # Very lightweight checks (you already did similar in Step 1)
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
    ap.add_argument("--model", required=True)
    ap.add_argument("--system_prompt_file", required=True)
    ap.add_argument("--test_file", default="data/dataset/splits/test.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--max_tokens", type=int, default=500)
    args = ap.parse_args()

    system_prompt = Path(args.system_prompt_file).read_text(encoding="utf-8")
    test_rows = load_jsonl(Path(args.test_file))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    totals = {"format_ok": 0, "no_raw_url": 0, "steps_count": 0}

    for r in test_rows:
        user_query = r["user_query"]
        expected_use_case = r.get("use_case")
        case_type = r.get("case_type")

        text = call(
            args.model, system_prompt, user_query, args.temperature, args.max_tokens
        )
        scores = score_output(text)

        totals["format_ok"] += scores["format_ok"]
        totals["no_raw_url"] += scores["no_raw_url"]
        totals["steps_count"] += scores["steps_count"]

        results.append(
            {
                "id": r["id"],
                "use_case": expected_use_case,
                "case_type": case_type,
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
        "no_raw_url_rate": totals["no_raw_url"] / max(n, 1),
    }

    payload = {"summary": summary, "results": results}
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("Wrote:", out_path)
    print("Summary:", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
