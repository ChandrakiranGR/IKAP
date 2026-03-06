import argparse
import json
from pathlib import Path

DEFAULT_SYSTEM = """You are IKAP, an AI assistant for Northeastern IT Services.

Rules:
- Follow the output format exactly.
- Do not invent URLs, phone numbers, or internal system names.
- If specific institutional steps are not available, provide general guidance only.
"""


def format_assistant(expected_output: dict, no_kb_label: bool = True) -> str:
    """
    Converts your structured expected_output into a single assistant message string.
    """
    category = expected_output.get("category", "General")
    steps = expected_output.get("steps", [])
    escalation = expected_output.get(
        "escalation",
        "Contact Northeastern IT Support with your device/OS and error message.",
    )

    lines = []
    lines.append(f"Category: {category}")
    lines.append("Clarifying question: None")

    if no_kb_label:
        lines.append(
            "Steps (general guidance, not official Northeastern instructions):"
        )
    else:
        lines.append("Steps:")

    for i, s in enumerate(steps, start=1):
        # ensure clean single-line steps
        s_clean = " ".join(str(s).split())
        lines.append(f"{i}. {s_clean}")

    lines.append(f"If this does not resolve your issue: {escalation}")
    return "\n".join(lines)


def row_to_ft_example(row: dict, system_prompt: str) -> dict:
    user_query = row.get("user_query", "").strip()
    expected = row.get("expected_output", {})

    assistant_text = format_assistant(expected_output=expected, no_kb_label=True)

    return {
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_query},
            {"role": "assistant", "content": assistant_text},
        ]
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", required=True, help="Input split jsonl (train/dev)")
    ap.add_argument("--outfile", required=True, help="Output fine-tune jsonl")
    ap.add_argument(
        "--system", default=DEFAULT_SYSTEM, help="System prompt for training examples"
    )
    args = ap.parse_args()

    inp = Path(args.infile)
    outp = Path(args.outfile)
    outp.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with (
        inp.open("r", encoding="utf-8") as f_in,
        outp.open("w", encoding="utf-8") as f_out,
    ):
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            ft_ex = row_to_ft_example(row, args.system)
            f_out.write(json.dumps(ft_ex, ensure_ascii=False) + "\n")
            count += 1

    print(f"[OK] Wrote {count} examples to {outp}")


if __name__ == "__main__":
    main()
