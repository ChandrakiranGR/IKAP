#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path


URL_RE = re.compile(r"https?://[^\s)>\]]+")
STEP_HEADER_RE = re.compile(r"(?m)^Steps:\n(?P<body>.*?)(?:\nReferences:|\Z)", re.S)
STEP_LINE_RE = re.compile(r"(?m)^\d+\.\s+(.*)$")
ACTION_WORDS = {
    "access",
    "activate",
    "add",
    "choose",
    "click",
    "complete",
    "configure",
    "connect",
    "contact",
    "create",
    "download",
    "email",
    "enable",
    "enter",
    "fill",
    "find",
    "go",
    "install",
    "launch",
    "log",
    "navigate",
    "open",
    "power",
    "press",
    "provide",
    "reconnect",
    "register",
    "request",
    "restart",
    "review",
    "save",
    "scroll",
    "search",
    "select",
    "set",
    "sign",
    "submit",
    "turn",
    "type",
    "update",
    "use",
    "verify",
    "visit",
    "wait",
}


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_rows(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def extract_steps(answer: str) -> list[str]:
    match = STEP_HEADER_RE.search(answer or "")
    body = match.group("body") if match else ""
    return [line.strip() for line in STEP_LINE_RE.findall(body)]


def looks_like_action_step(step: str) -> bool:
    lowered = (step or "").strip().lower()
    if not lowered:
        return False
    first = re.split(r"[\s:/()'-]+", lowered, maxsplit=1)[0]
    return first in ACTION_WORDS


def find_flags(row: dict) -> list[str]:
    flags: list[str] = []
    title = row.get("title", "")
    question = row.get("question", "")
    answer = row.get("draft_answer", "")
    steps = extract_steps(answer)

    if question.lower().startswith("faq:"):
        flags.append("faq_question")

    if "to the to the" in answer.lower() or "the the" in answer.lower():
        flags.append("duplicate_words")

    if any(step.endswith(":") for step in steps[:2]):
        flags.append("heading_as_numbered_step")

    if any(
        marker in answer
        for marker in [
            "How do I connect to VPN?:",
            "Request Northeastern username change:",
            "Troubleshooting:",
            "Update network settings and wpa_supplicant:",
            "Duo Mobile verified push:",
        ]
    ):
        flags.append("multi_section_blend")

    if len(steps) <= 2 and row.get("draft_quality") == "high":
        flags.append("unexpected_short_high_quality")

    if len(steps) >= 2 and all(
        len(step.split()) <= 3 and not looks_like_action_step(step) for step in steps[:3]
    ):
        flags.append("list_fragment_steps")

    if any(len(step) > 320 for step in steps):
        flags.append("long_step")

    step_block_match = STEP_HEADER_RE.search(answer or "")
    step_block = step_block_match.group("body") if step_block_match else ""
    if URL_RE.search(step_block):
        flags.append("url_inside_steps")

    if "References: None" in answer and row.get("reference_url"):
        flags.append("missing_reference")

    if row.get("split") == "holdout":
        flags.append("holdout_reserved")

    return flags


def suggest_status(flags: list[str]) -> str:
    review_flags = {
        "faq_question",
        "duplicate_words",
        "heading_as_numbered_step",
        "list_fragment_steps",
        "multi_section_blend",
        "unexpected_short_high_quality",
        "long_step",
        "url_inside_steps",
        "missing_reference",
    }
    if any(flag in review_flags for flag in flags):
        return "needs_edit"
    return "candidate_approve"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review_sheet", default="data/dataset/review_sheet.csv")
    ap.add_argument("--out", default="data/dataset/review_sheet.csv")
    args = ap.parse_args()

    in_path = Path(args.review_sheet)
    out_path = Path(args.out)

    rows = load_rows(in_path)
    if not rows:
        print(f"No rows found in {in_path}")
        return 0

    fieldnames = list(rows[0].keys())
    if "suggested_status" not in fieldnames:
        fieldnames.insert(fieldnames.index("review_status") + 1, "suggested_status")
    if "auto_flags" not in fieldnames:
        fieldnames.insert(fieldnames.index("suggested_status") + 1, "auto_flags")

    candidate_approve = 0
    needs_edit = 0
    for row in rows:
        flags = find_flags(row)
        suggestion = suggest_status(flags)
        row["suggested_status"] = suggestion
        row["auto_flags"] = ",".join(flags)
        if suggestion == "candidate_approve":
            candidate_approve += 1
        else:
            needs_edit += 1

    write_rows(out_path, rows, fieldnames)

    print(f"Annotated {len(rows)} rows in {out_path}")
    print(f"candidate_approve: {candidate_approve}")
    print(f"needs_edit: {needs_edit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
