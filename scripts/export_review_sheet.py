#!/usr/bin/env python3
import argparse
import csv
import json
import re
from pathlib import Path


VALID_REVIEW_STATUSES = {
    "todo",
    "approved",
    "approved_with_edits",
    "edited",
    "rejected",
}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_processed_doc(kb_dir: Path, article_id: str) -> dict:
    path = kb_dir / f"{article_id}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def extract_reference_url(messages: list[dict]) -> str:
    assistant = ""
    for msg in messages:
        if msg.get("role") == "assistant":
            assistant = msg.get("content", "")
            break
    match = re.search(r"https?://[^\s)>\]]+", assistant)
    if not match:
        return ""
    return re.sub(r"[),.;>\]]+$", "", match.group(0))


def load_existing_rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return {row["id"]: row for row in rows if row.get("id")}


def normalize_review_status(value: str) -> str:
    status = (value or "").strip().lower()
    if status in VALID_REVIEW_STATUSES:
        return status
    return "todo"


def priority_tuple(row: dict) -> tuple:
    split_order = {"train": 0, "dev": 1, "holdout": 2}
    quality_order = {"high": 0, "medium": 1, "low": 2}
    return (
        split_order.get(row["split"], 9),
        quality_order.get(row["draft_quality"], 9),
        row["title"].lower(),
        row["article_id"],
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset_dir", default="data/dataset")
    ap.add_argument("--kb_dir", default="data/processed/kb_json")
    ap.add_argument("--out", default="data/dataset/review_sheet.csv")
    args = ap.parse_args()

    dataset_dir = Path(args.dataset_dir)
    kb_dir = Path(args.kb_dir)
    out_path = Path(args.out)

    existing = load_existing_rows(out_path)

    draft_rows = []
    for name in ["draft_train.jsonl", "draft_dev.jsonl", "draft_holdout.jsonl"]:
        draft_rows.extend(load_jsonl(dataset_dir / name))

    rows = []
    for draft in draft_rows:
        messages = draft.get("messages", [])
        user_question = next(
            (msg.get("content", "") for msg in messages if msg.get("role") == "user"),
            "",
        )
        assistant_answer = next(
            (msg.get("content", "") for msg in messages if msg.get("role") == "assistant"),
            "",
        )
        article_id = draft.get("article_id", "")
        processed = load_processed_doc(kb_dir, article_id)

        prior = existing.get(draft["id"], {})
        row = {
            "priority_rank": "",
            "id": draft["id"],
            "article_id": article_id,
            "split": draft.get("split", ""),
            "draft_quality": draft.get("draft_quality", ""),
            "source_export": processed.get("source_export", ""),
            "title": draft.get("title", ""),
            "question": user_question,
            "draft_answer": assistant_answer,
            "reference_url": processed.get("article_url")
            or processed.get("url")
            or extract_reference_url(messages),
            "review_status": normalize_review_status(prior.get("review_status", "todo")),
            "suggested_status": prior.get("suggested_status", ""),
            "auto_flags": prior.get("auto_flags", ""),
            "edited_question": prior.get("edited_question", ""),
            "edited_answer": prior.get("edited_answer", ""),
            "notes": prior.get("notes", ""),
        }
        rows.append(row)

    rows.sort(key=priority_tuple)
    for idx, row in enumerate(rows, start=1):
        row["priority_rank"] = str(idx)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "priority_rank",
                "id",
                "article_id",
                "split",
                "draft_quality",
                "source_export",
                "title",
                "question",
                "draft_answer",
                "reference_url",
                "review_status",
                "suggested_status",
                "auto_flags",
                "edited_question",
                "edited_answer",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} review rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
