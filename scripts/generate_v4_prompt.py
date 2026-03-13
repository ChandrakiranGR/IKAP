#!/usr/bin/env python3
import argparse
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


def read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_step3_summary(results_dir: Path) -> str:
    parts = []

    mapping = [
        ("Prompt-only baseline", results_dir / "baseline_eval.json"),
        (
            "RAG baseline after KB refresh",
            results_dir / "rag_eval_after_kb_refresh.json",
        ),
        ("New fine-tuned (no RAG)", results_dir / "finetuned_eval_v2.json"),
        ("New fine-tuned + RAG", results_dir / "rag_eval_finetuned_v3.json"),
    ]

    for label, path in mapping:
        obj = read_json(path)
        if not obj:
            continue
        summary = obj.get("summary", {})
        pretty = ", ".join(f"{k}={v}" for k, v in summary.items())
        parts.append(f"{label}: {pretty}")

    parts.append(
        "Observed issues during Step 3: "
        "configuration KBs needed exact values preserved; "
        "some procedural KBs became too verbose; "
        "one earlier RAG baseline format miss came from overlong output; "
        "the old fine-tuned model became misaligned after prompt/schema changes; "
        "the retrained fine-tuned model restored 1.0 format compliance."
    )

    return "\n".join(parts)


def build_meta_prompt(v3_prompt: str, step3_summary: str) -> str:
    return f"""
You are an expert prompt engineer helping optimize an IT support system prompt.

Your job is to critique the current system prompt for IKAP and produce one improved version.

Context:
- The assistant helps Northeastern IT users with account access, password reset, MFA, WiFi, VPN, Canvas, software, and student portal issues.
- It may receive Retrieved KB Context and Retrieved Links.
- It must follow a strict response format with:
  Category
  Clarifying question
  Steps (KB-grounded if context is provided; otherwise general guidance)
  References
  Final escalation section
- It must never invent URLs, internal system names, or unsafe instructions.
- It must preserve exact configuration values when KB context includes them.
- It must stay concise for procedural workflows and preserve fidelity for configuration workflows.
- It must avoid markdown emphasis like **bold**.
- It must avoid meta-lines such as "You are trained on data up to..."

Optimization goals:
1. Maximize format compliance
2. Preserve safety and groundedness
3. Preserve exact configuration values when needed
4. Avoid over-compressing important KB-backed setup details
5. Avoid over-expanding procedural workflows
6. Keep the final escalation section present every time
7. Keep References grounded and only include URLs from Retrieved Links / KB context
8. Avoid any meta-lines such as “You are trained on data up to …”
9. Make only the smallest necessary improvements, not a full rewrite

Your task:
1. Read the current system prompt
2. Identify the top weaknesses or tensions in the prompt
3. Propose the smallest set of improvements needed
4. Produce one improved system prompt candidate called v4

Output exactly in this structure:

SECTION 1 — Weaknesses
- <bullet list>

SECTION 2 — Improvements
- <bullet list>

SECTION 3 — Revised Prompt (v4)
<full revised system prompt only>

Current system prompt:
--------------------
{v3_prompt}
--------------------

Observed Step 3 results:
--------------------
{step3_summary}
--------------------
""".strip()


def extract_v4_prompt(text: str) -> str:
    patterns = [
        r"SECTION 3\s*[—-]\s*Revised Prompt \(v4\)\s*(.*)$",
        r"SECTION 3\s*-\s*Revised Prompt \(v4\)\s*(.*)$",
    ]

    for pat in patterns:
        m = re.search(pat, text, flags=re.DOTALL | re.IGNORECASE)
        if m:
            out = m.group(1).strip()
            out = re.sub(r"^```(?:text|markdown|python)?\s*", "", out)
            out = re.sub(r"\s*```$", "", out)
            return out.strip()

    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument(
        "--v3_prompt_file", default="prompt_engineering/prompts/v3_system_prompt.txt"
    )
    ap.add_argument("--results_dir", default="prompt_engineering/results")
    ap.add_argument(
        "--out_report", default="prompt_engineering/results/step4_meta_critique.md"
    )
    ap.add_argument(
        "--out_v4_prompt", default="prompt_engineering/prompts/v4_system_prompt.txt"
    )
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max_tokens", type=int, default=4000)
    args = ap.parse_args()

    load_dotenv(dotenv_path=Path(".env"))
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in .env")

    client = OpenAI(api_key=api_key)

    v3_prompt_path = Path(args.v3_prompt_file)
    if not v3_prompt_path.exists():
        raise FileNotFoundError(f"Missing v3 prompt file: {v3_prompt_path}")

    v3_prompt = v3_prompt_path.read_text(encoding="utf-8").strip()
    step3_summary = load_step3_summary(Path(args.results_dir))
    meta_prompt = build_meta_prompt(v3_prompt, step3_summary)

    resp = client.chat.completions.create(
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        messages=[{"role": "user", "content": meta_prompt}],
    )

    text = resp.choices[0].message.content.strip()

    out_report = Path(args.out_report)
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(text, encoding="utf-8")

    v4_prompt = extract_v4_prompt(text)
    if not v4_prompt:
        raise RuntimeError(
            "Could not extract SECTION 3 — Revised Prompt (v4) from model output. "
            f"Please inspect: {out_report}"
        )

    out_v4 = Path(args.out_v4_prompt)
    out_v4.parent.mkdir(parents=True, exist_ok=True)
    out_v4.write_text(v4_prompt, encoding="utf-8")

    print(f"Wrote meta-critique report: {out_report}")
    print(f"Wrote v4 prompt: {out_v4}")


if __name__ == "__main__":
    main()
